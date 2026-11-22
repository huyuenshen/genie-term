"""commands/download.py —— genie-data / character / roberta 下载命令组。

PRD §4.7：
  genie-term download genie-data [--mirror URL] [--yes]    # 391MB
  genie-term download character NAME [--yes]               # 预置角色约 230MB + 自动注册
  genie-term download roberta [--yes]                     # 可选，自实现（上游未导出）

红线：
  - 禁止调用上游 download_genie_data()（它 local_dir="." 污染 CWD）
  - 用 huggingface_hub.snapshot_download 指定绝对目录，pattern 用 GenieData/**
  - HF_ENDPOINT 必须在 import huggingface_hub 之前设
  - 失败统一退出码 11 + hf-mirror 提示
  - --offline 只校验并打印手动放置路径
"""

from __future__ import annotations

import sys

import typer

from genie_term import context
from genie_term.errors import EnvError, UsageError

app = typer.Typer(
    name="download",
    help="下载资源 (genie-data|character|roberta)",
    add_completion=False,
    invoke_without_command=True,
)

_PRESET_NAMES = {"feibi", "mika", "thirtyseven"}


def _endpoint(mirror: str | None) -> str | None:
    if mirror:
        return mirror
    try:
        from genie_term.core.config import load_config

        return load_config().get("network.hf_endpoint") or None
    except Exception:
        return None


def _confirm(message: str, yes: bool, fix: str) -> None:
    """统一确认逻辑：非 TTY 无 --yes → 退出码 2（PRD §4.1）。"""
    if yes:
        return
    if not sys.stdin.isatty():
        raise UsageError("非交互式环境下载需要 --yes", fix=fix)
    if not typer.confirm(message):
        raise typer.Exit(code=0)


# ========== genie-data ==========

@app.command("genie-data")
def download_genie_data_cmd(
    mirror: str | None = typer.Option(None, "--mirror", help="HF mirror endpoint"),
    yes: bool = typer.Option(False, "--yes", help="跳过确认"),
    force: bool = typer.Option(False, "--force", help="已存在时重下"),
    offline: bool = typer.Option(False, "--offline", help="只校验，不联网"),
) -> None:
    """下载 GenieData（约 391MB，必需资源）。"""
    from genie_term.core.config import effective_data_dir

    data_dir = effective_data_dir()

    if context.is_offline(offline):
        from genie_term.download.verify import verify_genie_data

        genie_data = data_dir / "GenieData"
        missing = verify_genie_data(genie_data)
        if missing:
            raise EnvError(
                f"离线模式下缺少 GenieData 资源: {', '.join(missing)}",
                location=str(genie_data),
                fix=f"在有网机器下载后，把 GenieData 整个目录手动放到 {genie_data}",
            )
        typer.echo(f"✅ 离线校验通过: {genie_data}")
        return

    context.info(f"下载 GenieData → {data_dir}")
    _confirm(
        "确认下载约 391MB？",
        yes,
        "genie-term download genie-data --yes",
    )

    from genie_term.download.genie_data import download_genie_data

    result = download_genie_data(data_dir, mirror=_endpoint(mirror), force=force)
    typer.echo(f"✅ GenieData 就绪: {result}")


# ========== character ==========

@app.command("character")
def download_character_cmd(
    name: str = typer.Argument(..., help="角色名 (feibi|mika|thirtyseven)"),
    mirror: str | None = typer.Option(None, "--mirror", help="HF mirror endpoint"),
    yes: bool = typer.Option(False, "--yes", help="跳过确认"),
    offline: bool = typer.Option(False, "--offline", help="只校验，不联网"),
) -> None:
    """下载预置角色并自动注册（约 230MB）。"""
    from genie_term.core.config import effective_data_dir
    from genie_term.download.presets import normalize_name

    normalized = normalize_name(name)
    if normalized not in _PRESET_NAMES:
        raise UsageError(
            f"未知预置角色 '{name}'",
            fix=f"可用预置角色: {', '.join(sorted(_PRESET_NAMES))}",
        )

    data_dir = effective_data_dir()

    if context.is_offline(offline):
        from genie_term.download.genie_data import find_character_dir
        from genie_term.download.presets import auto_register_preset

        char_dir = find_character_dir(data_dir, normalized)
        if char_dir is None:
            raise EnvError(
                f"离线模式下角色 '{normalized}' 未下载",
                location=str(data_dir / "CharacterModels"),
                fix=f"在有网机器运行 genie-term download character {normalized} --yes",
            )
        auto_register_preset(normalized, char_dir)
        typer.echo(f"✅ 离线角色就绪: {char_dir}")
        return

    context.info(f"下载角色 '{normalized}' → {data_dir}")
    _confirm(
        "确认下载约 230MB？",
        yes,
        f"genie-term download character {normalized} --yes",
    )

    from genie_term.download.genie_data import download_character
    from genie_term.download.presets import auto_register_preset

    char_dir = download_character(data_dir, normalized, mirror=_endpoint(mirror))
    typer.echo(f"✅ 模型下载完成: {char_dir}")
    auto_register_preset(normalized, char_dir)


# ========== roberta ==========

@app.command("roberta")
def download_roberta_cmd(
    mirror: str | None = typer.Option(None, "--mirror", help="HF mirror endpoint"),
    yes: bool = typer.Option(False, "--yes", help="跳过确认"),
    offline: bool = typer.Option(False, "--offline", help="只校验，不联网"),
) -> None:
    """下载中文 RoBERTa 韵律模型（可选）。"""
    from genie_term.core.config import effective_data_dir

    data_dir = effective_data_dir()
    roberta_dir = data_dir / "GenieData" / "RoBERTa"

    if context.is_offline(offline):
        if roberta_dir.exists():
            typer.echo(f"✅ RoBERTa 已存在: {roberta_dir}")
        else:
            context.info(
                f"⚠ RoBERTa 未安装（可选组件）；手动放置路径: {roberta_dir}"
            )
        return

    context.info(f"下载 RoBERTa → {data_dir}")
    _confirm(
        "确认下载可选的 RoBERTa 模型？",
        yes,
        "genie-term download roberta --yes",
    )

    from genie_term.download.genie_data import download_roberta

    result = download_roberta(data_dir, mirror=_endpoint(mirror))
    if result.exists():
        typer.echo(f"✅ RoBERTa 就绪: {result}")
    else:
        context.info(
            f"⚠ RoBERTa 在仓库中未找到（可选组件，V1 可能已下线）；"
            f"手动放置路径: {roberta_dir}"
        )
