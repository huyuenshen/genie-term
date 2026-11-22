"""commands/characters.py —— 角色管理命令组。

PRD §4.6：list/show/add/use/remove
"""

from __future__ import annotations

import json as _json
from pathlib import Path

import typer

from genie_term.core.audio import check_prompt_audio
from genie_term.core.registry import load_registry
from genie_term.errors import UsageError

app = typer.Typer(
    name="characters",
    help="角色管理 (list|show|add|use|remove)",
    add_completion=False,
    invoke_without_command=True,
)


# ========== list ==========

@app.command("list")
def list_chars(
    json_flag: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """列出所有注册角色。"""
    reg = load_registry()
    chars = reg.list_characters()

    if json_flag:
        typer.echo(_json.dumps(chars, ensure_ascii=False, indent=2))
        return

    if not chars:
        typer.echo("（无已注册角色）")
        typer.echo("  genie-term download character feibi   # 下载预置角色")
        typer.echo("  genie-term characters add ...         # 注册本地角色")
        return

    # 表格输出
    header = f"{'NAME':<16} {'LANG':<4} {'VER':<10} {'KIND':<10}"
    typer.echo(header)
    typer.echo("-" * len(header))
    for name, data in sorted(chars.items()):
        typer.echo(
            f"{name:<16} {data.get('language', '?'):<4} "
            f"{data.get('model_version', '?'):<10} "
            f"{data.get('kind', '?'):<10}"
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
        typer.echo(_json.dumps({"name": name, **data}, ensure_ascii=False, indent=2))
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
    prompt_wav: str = typer.Option(None, "--prompt-wav", help="参考音频文件 (.wav/.flac/.ogg/.aiff/.aif)"),
    prompt_text: str = typer.Option(None, "--prompt-text", help="参考音频里说的那句话"),
    model_version: str | None = typer.Option(None, "--version", help="v2|v2ProPlus（通常自动推断）"),
    force: bool = typer.Option(False, "--force", help="覆盖已存在的角色"),
) -> None:
    """注册本地/转换角色。"""
    from genie_term.core.registry import load_registry as _load
    reg = _load()

    # 必填：model_dir 存在
    md = Path(model_dir).expanduser().resolve()
    if not md.exists():
        raise UsageError(f"model_dir 不存在: {md}")

    # 必填：prompt_wav + prompt_text
    if not prompt_wav or not prompt_text:
        raise UsageError(
            "--prompt-wav 和 --prompt-text 必填",
            fix=f"genie-term characters add {name} --model-dir {model_dir} --lang {language} --prompt-wav ref.wav --prompt-text '参考文本'",
        )

    # prompt 音频校验
    ok, problems = check_prompt_audio(prompt_wav)
    if not ok:
        raise UsageError(
            "参考音频不合格:\n  " + "\n  ".join(problems),
        )
    if problems:
        typer.echo(f"⚠ 参考音频有警告: {'; '.join(problems)}", err=True)

    # model_version 自动推断
    if not model_version:
        if (md / "prompt_encoder_fp32.onnx").exists():
            model_version = "v2ProPlus"
            typer.echo("自动推断 model_version = v2ProPlus", err=True)
        else:
            model_version = "v2"
            typer.echo("自动推断 model_version = v2", err=True)

    # 组装 + 注册
    char_data = {
        "kind": "local",
        "language": language,
        "model_version": model_version,
        "model_dir": str(md),
        "prompt_wav": str(Path(prompt_wav).expanduser().resolve()),
        "prompt_text": prompt_text,
    }

    try:
        reg.add(name, char_data, force=force)
        reg.save()
    except UsageError:
        raise

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
    data = reg.remove(name)
    if not data:
        raise UsageError(
            f"角色 '{name}' 不存在",
            fix="genie-term characters list",
        )

    model_dir = data.get("model_dir", "")
    if purge and model_dir:
        if not yes:
            confirm = typer.confirm(
                f"确认删除模型目录 {model_dir}？此操作不可恢复。"
            )
            if not confirm:
                raise typer.Exit(code=0)
        import shutil
        if Path(model_dir).exists():
            shutil.rmtree(model_dir)
            typer.echo(f"已删除模型目录: {model_dir}")

    reg.save()
    typer.echo(f"✅ 角色 '{name}' 已移除")
