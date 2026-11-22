"""commands/convert.py —— GPT-SoVITS 模型转换为 ONNX。

PRD §4.8：
  genie-term convert --pth a.pth --ckpt a.ckpt [--version v2|v2ProPlus] \\
                    --name NAME [--out DIR] [--register/--no-register] [--json]

关键约束：
  - 缺 torch → 退出码 21，**只给一条**正确命令
  - 流程：校验 → 临时目录 → convert_to_onnx → 校验 9 文件 → 原子改名 → 询问注册
  - 失败清临时 + 码 20
"""

from __future__ import annotations

import json as _json
import os
import shutil
import sys
import tempfile
from pathlib import Path

import typer

from genie_term.errors import (
    EXIT_OK,
    EngineError,
    MissingTorchError,
    UsageError,
)

app = typer.Typer(
    name="convert",
    help="把 GPT-SoVITS .pth/.ckpt 转换为 genie-term 可用的 ONNX 模型",
    add_completion=False,
    invoke_without_command=True,
)

# 转换后必需的 9 个文件
REQUIRED_CONVERT_FILES = [
    "t2s_encoder_fp32.bin",
    "t2s_encoder_fp32.onnx",
    "t2s_first_stage_decoder_fp32.onnx",
    "t2s_shared_fp16.bin",
    "t2s_stage_decoder_fp32.onnx",
    "vits_fp16.bin",
    "vits_fp32.onnx",
    # v2ProPlus 才有的两个（但我们先假设 v2ProPlus 格式，下游按文件推断）
    "prompt_encoder_fp16.bin",
    "prompt_encoder_fp32.onnx",
]

# 目录结构约束
# CharacterModels/<version>/<name>/tts_models + prompt_wav.json

TORCH_INSTALL_CMD = (
    "pipx inject genie-term torch --index-url "
    "https://download.pytorch.org/whl/cpu"
)


def _check_torch() -> None:
    """检查 torch 是否可导入，不可则抛 MissingTorchError（码 21）。"""
    try:
        import torch  # noqa: F401
    except ImportError:
        raise MissingTorchError(
            "缺少 torch（convert 功能必需）",
            location="genie-term convert",
            fix=TORCH_INSTALL_CMD,
        )


# ========== 核心实现 ==========

def run_convert(
    *,
    pth: str,
    ckpt: str,
    name: str,
    version: str = "v2ProPlus",
    out_dir: str | None = None,
    register: bool | None = None,
    json_flag: bool = False,
) -> Path:
    """执行转换，返回最终模型目录。"""
    # torch 前置检查
    _check_torch()

    # 输入校验
    pth_path = Path(pth).expanduser().resolve()
    ckpt_path = Path(ckpt).expanduser().resolve()

    if not pth_path.exists():
        raise UsageError(f"pth 文件不存在: {pth_path}")
    if not ckpt_path.exists():
        raise UsageError(f"ckpt 文件不存在: {ckpt_path}")

    if version not in {"v2", "v2ProPlus"}:
        raise UsageError(
            f"--version 必须是 v2 或 v2ProPlus，当前: {version}",
        )

    # 输出目录
    from genie_term.core.paths import resolve_data_dir

    data_dir = resolve_data_dir()
    base_out = Path(out_dir).expanduser().resolve() if out_dir else data_dir / "CharacterModels" / version / name
    base_out.mkdir(parents=True, exist_ok=True)

    # 临时目录（用于 convert，原子改名到最终位置）
    tmp_dir = Path(tempfile.mkdtemp(prefix="genie_convert_"))
    try:
        # 确保 env 注入 + 调用上游 convert_to_onnx
        from genie_term.core.paths import resolve_data_dir as _resolve
        from genie_term.engine.adapter import ensure_env
        ensure_env(data_dir=str(_resolve()))

        from genie_term.engine import adapter
        typer.echo(f"转换中: {pth_path.name} + {ckpt_path.name} → {tmp_dir}", err=True)
        adapter.convert(str(pth_path), str(ckpt_path), str(tmp_dir))
        typer.echo("  ✓ 转换完成", err=True)

        # 校验产物
        missing = [f for f in REQUIRED_CONVERT_FILES if not (tmp_dir / f).exists()]
        if missing:
            raise EngineError(
                f"转换产物缺少必需文件: {', '.join(missing)}",
                location=str(tmp_dir),
                fix="检查 .pth/.ckpt 是否匹配 v2ProPlus 格式",
            )

        # 原子移动到最终位置
        target = base_out / "tts_models"
        if target.exists():
            shutil.rmtree(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        os.replace(str(tmp_dir), str(target))
        typer.echo(f"✅ 模型已就位: {target}", err=True)

        return target

    except EngineError:
        if tmp_dir.exists():
            shutil.rmtree(tmp_dir, ignore_errors=True)
        raise
    except Exception as exc:
        if tmp_dir.exists():
            shutil.rmtree(tmp_dir, ignore_errors=True)
        raise EngineError(
            f"转换失败: {exc}",
            location=str(tmp_dir),
            fix="运行 genie-term doctor 检查环境；确认 .pth 和 .ckpt 格式正确",
        ) from exc


# ========== Typer 命令 ==========

@app.callback(invoke_without_command=True)
def _callback(
    ctx: typer.Context,
    pth: str = typer.Option(..., "--pth", help="GPT-SoVITS .pth 文件路径"),
    ckpt: str = typer.Option(..., "--ckpt", help="GPT-SoVITS .ckpt 文件路径"),
    name: str = typer.Option(..., "--name", help="角色名称（用于注册）"),
    version: str = typer.Option("v2ProPlus", "--version", help="v2|v2ProPlus"),
    out_dir: str | None = typer.Option(None, "--out", help="输出根目录（默认 ~/.local/share/genie-term/CharacterModels/<version>/<name>）"),
    register: bool | None = typer.Option(None, "--register/--no-register", help="转换后自动注册"),
    json_flag: bool = typer.Option(False, "--json", help="输出 JSON"),
) -> None:
    if ctx.invoked_subcommand is not None:
        return

    target = run_convert(
        pth=pth,
        ckpt=ckpt,
        name=name,
        version=version,
        out_dir=out_dir,
        register=register,
        json_flag=json_flag,
    )

    # 注册逻辑
    if register is None:
        if sys.stdin.isatty():
            do_register = typer.confirm("转换成功！是否现在注册此角色？")
        else:
            do_register = False
    else:
        do_register = register

    if do_register:
        # 提示用户需要提供 prompt-wav 和 prompt-text
        typer.echo(
            "注册需要额外信息，请运行:\n"
            f"  genie-term characters add {name} --model-dir {target} "
            f"--lang zh --prompt-wav ref.wav --prompt-text '参考音频内容'",
            err=True,
        )

    if json_flag:
        typer.echo(_json.dumps({"model_dir": str(target), "name": name}))
    else:
        typer.echo(f"✅ 转换完成: {target}")

    raise typer.Exit(code=EXIT_OK)
