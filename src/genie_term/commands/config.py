"""commands/config.py —— config show|get|set|reset|path。

完整 Schema 见 core/config.py / PRD §6.7。
写入经 core/config.py 的原子写：校验 → .bak → 临时文件 → os.replace。
"""

from __future__ import annotations

import sys

import typer

from genie_term.core.config import load_config
from genie_term.errors import UsageError

app = typer.Typer(
    name="config",
    help="Manage configuration (show|get|set|reset|path)",
    add_completion=False,
    invoke_without_command=True,
)


# ========== config show ==========

@app.command("show")
def config_show() -> None:
    """Print full config (TOML format)."""
    cfg = load_config()
    import io

    import tomli_w

    buf = io.BytesIO()
    tomli_w.dump(cfg._data, buf)
    typer.echo(buf.getvalue().decode("utf-8"))


# ========== config get ==========

@app.command("get")
def config_get(
    key: str = typer.Argument(..., help="Dot-separated key, e.g. general.default_character"),
) -> None:
    """Get a single config value."""
    cfg = load_config()
    value = cfg.get(key)
    if value is None:
        raise UsageError(
            f"Key not found: {key}",
            fix="genie-term config show  # 查看所有配置",
        )
    typer.echo(value)


# ========== config set ==========

@app.command("set")
def config_set(
    key: str = typer.Argument(..., help="Dot-separated key, e.g. network.hf_endpoint"),
    value: str = typer.Argument(..., help="New value"),
) -> None:
    """Set a config value and persist atomically."""
    cfg = load_config()

    # 类型转换：数字和布尔
    converted = _coerce(value)
    cfg.set(key, converted)
    cfg.save()
    typer.echo(f"Set {key} = {converted!r}")


# ========== config reset ==========

@app.command("reset")
def config_reset(
    yes: bool = typer.Option(False, "--yes", help="Skip confirmation"),
) -> None:
    """Reset config to defaults (requires --yes in non-TTY)."""
    if not yes and not sys.stdin.isatty():
        raise UsageError(
            "非交互式环境下重置配置需要 --yes",
            fix="genie-term config reset --yes",
        )
    if not yes and sys.stdin.isatty():
        confirm = typer.confirm("确认重置配置到默认值？")
        if not confirm:
            raise typer.Exit(code=0)

    cfg = load_config()
    cfg.reset()
    cfg.save()
    typer.echo("Configuration reset to defaults.")


# ========== config path ==========

@app.command("path")
def config_path_cmd() -> None:
    """Print config file path."""
    from genie_term.core.paths import config_path
    typer.echo(str(config_path()))


# ========== 辅助 ==========

def _coerce(value: str) -> object:
    """把命令行字符串值转为合适的 Python 类型。"""
    # 布尔
    if value.lower() in {"true", "yes", "on"}:
        return True
    if value.lower() in {"false", "no", "off"}:
        return False
    # 整数
    try:
        return int(value)
    except ValueError:
        pass
    # 浮点数
    try:
        return float(value)
    except ValueError:
        pass
    # 原样返回字符串
    return value
