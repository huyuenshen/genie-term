"""commands/convert.py —— GPT-SoVITS 模型转换为 ONNX。

PRD §4.8 / §5.2：
  genie-term convert --pth a.pth --ckpt a.ckpt [--version v2|v2ProPlus] \\
                    --name NAME [--out DIR] [--register/--no-register] [--json]

关键约束：
  - 缺 torch → 退出码 21，**只给一条**正确命令
  - 流程：校验 → 临时目录 → convert_to_onnx → 校验产物 → 原子改名 → 注册
  - convert --register 时同样强制校验参考音频（--prompt-wav/--prompt-text）
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

from genie_term import context
from genie_term.core.registry import BASELINE_REQUIRED_FILES, V2PROPLUS_REQUIRED_FILES
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

TORCH_INSTALL_CMD = (
    "pipx inject genie-term torch --index-url "
    "https://download.pytorch.org/whl/cpu"
)

_VALID_VERSIONS = {"v2", "v2ProPlus"}
_VALID_LANGUAGES = {"zh", "en", "jp"}


def _required_files(version: str) -> list[str]:
    files = list(BASELINE_REQUIRED_FILES)
    if version == "v2ProPlus":
        files.extend(V2PROPLUS_REQUIRED_FILES)
    return files


def _check_torch() -> None:
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
    json_flag: bool = False,
) -> Path:
    """执行转换，返回最终模型目录。"""
    _check_torch()

    pth_path = Path(pth).expanduser().resolve()
    ckpt_path = Path(ckpt).expanduser().resolve()

    if not pth_path.exists():
        raise UsageError(f"pth 文件不存在: {pth_path}")
    if not ckpt_path.exists():
        raise UsageError(f"ckpt 文件不存在: {ckpt_path}")
    if version not in _VALID_VERSIONS:
        raise UsageError(
            f"--version 必须是 v2 或 v2ProPlus，当前: {version}",
            fix="genie-term convert --version v2|v2ProPlus ...",
        )

    from genie_term.core.paths import effective_data_dir

    data_dir = effective_data_dir()
    if out_dir:
        target = Path(out_dir).expanduser().resolve()
    else:
        target = data_dir / "CharacterModels" / version / name / "tts_models"

    tmp_dir = Path(tempfile.mkdtemp(prefix="genie_convert_"))
    try:
        from genie_term.engine.adapter import ensure_env

        ensure_env(data_dir=str(data_dir))

        from genie_term.engine import adapter

        context.info(f"转换中: {pth_path.name} + {ckpt_path.name} → {tmp_dir}")
        adapter.convert(str(pth_path), str(ckpt_path), str(tmp_dir))
        context.info("  ✓ 转换完成")

        missing = [f for f in _required_files(version) if not (tmp_dir / f).exists()]
        if missing:
            raise EngineError(
                f"转换产物缺少必需文件: {', '.join(missing)}",
                location=str(tmp_dir),
                fix="检查 .pth/.ckpt 是否匹配所选 --version 格式",
            )

        if target.exists():
            shutil.rmtree(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        os.replace(str(tmp_dir), str(target))
        context.info(f"✅ 模型已就位: {target}")
        return target

    except EngineError:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise
    except KeyboardInterrupt:
        # PRD §4.1：Ctrl-C 清理临时文件，退出码 130（由 cli.main 映射）
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise
    except Exception as exc:  # noqa: BLE001 - 统一转 EngineError
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise EngineError(
            f"转换失败: {exc}",
            location=str(tmp_dir),
            fix="运行 genie-term doctor 检查环境；确认 .pth 和 .ckpt 格式正确",
        ) from exc


def _register_converted(
    *,
    name: str,
    target: Path,
    version: str,
    language: str,
    prompt_wav: str | None,
    prompt_text: str | None,
) -> None:
    """PRD §4.8/§5.2：注册转换后的角色，参考音频必填成对。"""
    from genie_term.core.audio import inspect_prompt_audio
    from genie_term.core.registry import load_registry

    if not prompt_wav or not prompt_text:
        raise UsageError(
            "convert --register 需要 --prompt-wav 与 --prompt-text",
            fix=f"genie-term convert --pth a.pth --ckpt a.ckpt --name {name} "
                f"--register --prompt-wav ref.wav --prompt-text '参考音频内容'",
        )

    errors, warnings = inspect_prompt_audio(prompt_wav)
    if errors:
        raise UsageError(
            "参考音频不合格:\n  " + "\n  ".join(errors),
            fix="使用 3–15 秒的 .wav/.flac/.ogg/.aiff/.aif 音频",
        )
    for warning in warnings:
        context.info(f"⚠ 参考音频: {warning}")

    reg = load_registry()
    reg.add(
        name,
        {
            "kind": "converted",
            "language": language,
            "model_version": version,
            "model_dir": str(target),
            "prompt_wav": str(Path(prompt_wav).expanduser().resolve()),
            "prompt_text": prompt_text,
        },
        force=True,
    )
    reg.save()


# ========== Typer 命令 ==========

@app.callback(invoke_without_command=True)
def _callback(
    ctx: typer.Context,
    pth: str = typer.Option(..., "--pth", help="GPT-SoVITS .pth 文件路径"),
    ckpt: str = typer.Option(..., "--ckpt", help="GPT-SoVITS .ckpt 文件路径"),
    name: str = typer.Option(..., "--name", help="角色名称（用于注册）"),
    version: str = typer.Option("v2ProPlus", "--version", help="v2|v2ProPlus"),
    out_dir: str | None = typer.Option(None, "--out", help="输出模型目录（默认 <data_dir>/CharacterModels/<version>/<name>/tts_models）"),
    register: bool | None = typer.Option(None, "--register/--no-register", help="转换后自动注册"),
    language: str = typer.Option("zh", "--lang", help="注册语言 zh|en|jp"),
    prompt_wav: str | None = typer.Option(None, "--prompt-wav", help="参考音频（注册时必填）"),
    prompt_text: str | None = typer.Option(None, "--prompt-text", help="参考音频文本（注册时必填）"),
    json_flag: bool = typer.Option(False, "--json", help="输出 JSON"),
) -> None:
    if ctx.invoked_subcommand is not None:
        return

    if language not in _VALID_LANGUAGES:
        raise UsageError(
            f"--lang 取值非法: {language}",
            fix="允许: zh|en|jp",
        )

    target = run_convert(
        pth=pth,
        ckpt=ckpt,
        name=name,
        version=version,
        out_dir=out_dir,
        json_flag=json_flag,
    )

    if register is None:
        if sys.stdin.isatty():
            do_register = typer.confirm("转换成功！是否现在注册此角色？")
        else:
            do_register = False
    else:
        do_register = register

    registered = False
    if do_register:
        _register_converted(
            name=name,
            target=target,
            version=version,
            language=language,
            prompt_wav=prompt_wav,
            prompt_text=prompt_text,
        )
        registered = True

    if json_flag:
        typer.echo(_json.dumps(
            {
                "ok": True,
                "name": name,
                "model_dir": str(target),
                "registered": registered,
            },
            ensure_ascii=False,
        ))
    else:
        typer.echo(f"✅ 转换完成: {target}")
        if registered:
            typer.echo(f"✅ 角色 '{name}' 已注册")
        elif not do_register:
            typer.echo(
                f"未注册。注册命令: genie-term characters add {name} "
                f"--model-dir {target} --lang {language} "
                f"--prompt-wav ref.wav --prompt-text '参考音频内容'"
            )

    raise typer.Exit(code=EXIT_OK)
