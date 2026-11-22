"""commands/characters.py —— 角色管理命令组。

PRD §4.6：list/show/add/use/remove
"""

from __future__ import annotations

import json as _json
import shutil
import sys
from pathlib import Path

import typer

from genie_term import context
from genie_term.core.audio import inspect_prompt_audio
from genie_term.core.registry import load_registry
from genie_term.errors import UsageError

app = typer.Typer(
    name="characters",
    help="角色管理 (list|show|add|use|remove)",
    add_completion=False,
    invoke_without_command=True,
)

_VALID_LANGUAGES = {"zh", "en", "jp"}
_VALID_VERSIONS = {"v2", "v2ProPlus"}


def _dir_size(path: str | Path) -> int:
    total = 0
    p = Path(path)
    if not p.is_dir():
        return 0
    for child in p.rglob("*"):
        try:
            if child.is_file():
                total += child.stat().st_size
        except OSError:
            continue
    return total


def _human_size(num: int) -> str:
    value = float(num)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.1f}{unit}"
        value /= 1024
    return f"{value:.1f}TB"


# ========== list ==========

@app.command("list")
def list_chars(
    json_flag: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """列出所有注册角色。"""
    reg = load_registry()
    chars = reg.list_characters()

    if json_flag:
        typer.echo(_json.dumps(chars, ensure_ascii=False))
        return

    if not chars:
        typer.echo("（无已注册角色）")
        typer.echo("  genie-term download character feibi   # 下载预置角色")
        typer.echo("  genie-term characters add ...         # 注册本地角色")
        return

    # PRD §4.6：名称 / 语言 / 模型版本 / 来源 / 参考音频 / 磁盘占用
    header = f"{'NAME':<16} {'LANG':<4} {'VER':<10} {'KIND':<10} {'REF':<4} {'SIZE':>9}"
    typer.echo(header)
    typer.echo("-" * len(header))
    for name, data in sorted(chars.items()):
        ref_ok = "✔" if Path(data.get("prompt_wav", "")).exists() else "✘"
        size = _human_size(_dir_size(data.get("model_dir", "")))
        typer.echo(
            f"{name:<16} {data.get('language', '?'):<4} "
            f"{data.get('model_version', '?'):<10} "
            f"{data.get('kind', '?'):<10} {ref_ok:<4} {size:>9}"
        )


# ========== show ==========

@app.command("show")
def show_char(
    name: str = typer.Argument(..., help="角色名称"),
    json_flag: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """显示角色详情。"""
    reg = load_registry()
    data = reg.get(name)
    if not data:
        raise UsageError(
            f"角色 '{name}' 不存在",
            fix="genie-term characters list",
        )

    if json_flag:
        typer.echo(_json.dumps({"name": name, **data}, ensure_ascii=False))
        return

    typer.echo(f"[{name}]")
    for key, val in data.items():
        typer.echo(f"  {key}: {val}")


# ========== add ==========

@app.command("add")
def add_char(
    name: str = typer.Argument(..., help="角色名称"),
    model_dir: str = typer.Option(..., "--model-dir", help="模型目录路径"),
    language: str = typer.Option(..., "--lang", help="zh|en|jp"),
    prompt_wav: str | None = typer.Option(None, "--prompt-wav", help="参考音频文件 (.wav/.flac/.ogg/.aiff/.aif)"),
    prompt_text: str | None = typer.Option(None, "--prompt-text", help="参考音频里说的那句话"),
    model_version: str | None = typer.Option(None, "--version", help="v2|v2ProPlus（通常自动推断）"),
    force: bool = typer.Option(False, "--force", help="覆盖已存在的角色"),
) -> None:
    """注册本地/转换角色。"""
    reg = load_registry()

    if language not in _VALID_LANGUAGES:
        raise UsageError(
            f"--lang 取值非法: {language}",
            fix="允许: zh|en|jp",
        )
    if model_version and model_version not in _VALID_VERSIONS:
        raise UsageError(
            f"--version 取值非法: {model_version}",
            fix="允许: v2|v2ProPlus",
        )

    md = Path(model_dir).expanduser().resolve()
    if not md.is_dir():
        raise UsageError(
            f"--model-dir 不存在或不是目录: {md}",
            fix=f"genie-term characters add {name} --model-dir /path/to/tts_models ...",
        )

    # PRD §4.6：参考音频必须成对
    if not prompt_wav or not prompt_text:
        raise UsageError(
            "--prompt-wav 和 --prompt-text 必须成对提供",
            fix=f"genie-term characters add {name} --model-dir {md} "
                f"--lang {language} --prompt-wav ref.wav --prompt-text '参考文本'",
        )

    errors, warnings = inspect_prompt_audio(prompt_wav)
    if errors:
        raise UsageError(
            "参考音频不合格:\n  " + "\n  ".join(errors),
            fix="使用 3–15 秒的 .wav/.flac/.ogg/.aiff/.aif 音频",
        )
    for warning in warnings:
        context.info(f"⚠ 参考音频: {warning}")

    # model_version 推断：文件为准，与 --version 冲突时告警（PRD §4.6 规则 3）
    inferred = "v2ProPlus" if (md / "prompt_encoder_fp32.onnx").exists() else "v2"
    if model_version and model_version != inferred:
        context.info(
            f"⚠ --version={model_version} 与文件推断 {inferred} 冲突，以文件为准"
        )
    model_version = inferred

    char_data = {
        "kind": "local",
        "language": language,
        "model_version": model_version,
        "model_dir": str(md),
        "prompt_wav": str(Path(prompt_wav).expanduser().resolve()),
        "prompt_text": prompt_text,
    }

    reg.add(name, char_data, force=force)
    reg.save()
    typer.echo(f"✅ 角色 '{name}' 注册成功 ({model_version}, {language})")


# ========== use ==========

@app.command("use")
def use_char(
    name: str = typer.Argument(..., help="设为默认角色"),
) -> None:
    """设置默认角色。"""
    from genie_term.core.config import load_config

    reg = load_registry()
    if not reg.exists(name):
        raise UsageError(
            f"角色 '{name}' 不存在",
            fix="genie-term characters list",
        )

    cfg = load_config()
    cfg.set("general.default_character", name)
    cfg.save()
    typer.echo(f"✅ 默认角色已设为 '{name}'")


# ========== remove ==========

@app.command("remove")
def remove_char(
    name: str = typer.Argument(..., help="要移除的角色"),
    purge: bool = typer.Option(False, "--purge", help="同时删除模型目录"),
    yes: bool = typer.Option(False, "--yes", help="跳过确认"),
) -> None:
    """移除角色（默认只删注册表，--purge 才删模型目录）。"""
    reg = load_registry()
    data = reg.get(name)
    if not data:
        raise UsageError(
            f"角色 '{name}' 不存在",
            fix="genie-term characters list",
        )

    model_dir = data.get("model_dir", "")
    if purge and model_dir:
        if not yes:
            # PRD §4.1：非 TTY 绝不提问，缺 --yes → 退出码 2
            if not sys.stdin.isatty():
                raise UsageError(
                    "非交互式环境下删除模型目录需要 --yes",
                    fix=f"genie-term characters remove {name} --purge --yes",
                )
            if not typer.confirm(
                f"确认删除模型目录 {model_dir}？此操作不可恢复。"
            ):
                raise typer.Exit(code=0)
        if Path(model_dir).exists():
            shutil.rmtree(model_dir)
            typer.echo(f"已删除模型目录: {model_dir}")

    reg.remove(name)
    reg.save()
    typer.echo(f"✅ 角色 '{name}' 已移除")
