"""cli.py —— genie-term 主入口。

红线（project_rules.md §5）：
  - 顶层禁止 import onnxruntime/genie_tts（否则 --help 超 400ms）
  - 只做 typer 装配、全局选项解析、命令分发、异常→退出码映射
  - 业务逻辑一律在 commands/ 或 core/ 中

退出码严格按 PRD §4.1。
"""

from __future__ import annotations

import os
import sys

import typer

from genie_term.errors import (
    EXIT_INTERRUPT,
    GenieTermError,
    exception_to_exit_code,
)

app = typer.Typer(
    name="genie-term",
    help="Unix-like native GenieTTS CLI wrapper\n"
         "一条命令装好：pipx install genie-term",
    add_completion=False,
    no_args_is_help=False,
    rich_markup_mode="rich",
)


# ========== 顶级 version 命令 ==========

@app.command("version")
def version_cmd(
    json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Print genie-term version and dependency info."""
    from genie_term.commands.version import run_version
    run_version(json=json)


# ========== 子命令组 ==========

# 延迟 import，避免顶层加载重依赖
@app.callback(invoke_without_command=True)
def _main_callback(
    ctx: typer.Context,
    version_flag: bool | None = typer.Option(
        None, "--version", "-V", help="Print version info and exit.",
        is_eager=True,
    ),
) -> None:
    """genie-term CLI —— Unix-like GenieTTS 封装。"""
    if version_flag:
        from genie_term.commands.version import run_version
        run_version(json=False)
        raise typer.Exit(code=0)


# 注册子命令组（延迟 import）
def _register_subcommands() -> None:
    """注册所有子命令组。"""
    from genie_term.commands.characters import app as _char_app
    from genie_term.commands.completion import app as _comp_app
    from genie_term.commands.config import app as _config_app
    from genie_term.commands.convert import app as _conv_app
    from genie_term.commands.doctor import app as _doctor_app
    from genie_term.commands.download import app as _dl_app
    from genie_term.commands.init import app as _init_app
    from genie_term.commands.say import app as _say_app
    from genie_term.commands.serve import app as _serve_app

    app.add_typer(_config_app, name="config", help="配置管理 (show|get|set|reset|path)")
    app.add_typer(_doctor_app, name="doctor", help="环境诊断（12 项检查）")
    app.add_typer(_init_app, name="init", help="首次初始化（下载 GenieData）")
    app.add_typer(_dl_app, name="download", help="下载资源 (genie-data|character|roberta)")
    app.add_typer(_char_app, name="characters", help="角色管理 (list|show|add|use|remove)")
    app.add_typer(_say_app, name="say", help="合成语音")
    app.add_typer(_conv_app, name="convert", help="GPT-SoVITS → ONNX 转换")
    app.add_typer(_serve_app, name="serve", help="启动本地 HTTP API 服务")
    app.add_typer(_comp_app, name="completion", help="Shell completion 脚本")


# 立即注册（顶层无重依赖，OK）
_register_subcommands()


# ========== 主入口 ==========

def main() -> None:
    """genie-term CLI 主入口。

    异常处理策略（PRD §7）：
    - GenieTermError 子类：打印格式化错误 + 使用其 code 属性
    - KeyboardInterrupt：退出码 130
    - 未知异常：退出码 20（仅 debug 模式打印堆栈）
    """
    try:
        app(standalone_mode=False)
    except typer.Exit as e:
        sys.exit(e.exit_code)
    except KeyboardInterrupt:
        sys.exit(EXIT_INTERRUPT)
    except GenieTermError as e:
        typer.echo(str(e), err=True)
        sys.exit(e.code)
    except Exception as e:
        typer.echo(f"[错误] 未预期的内部错误: {e}", err=True)
        typer.echo(
            "  详细: GENIE_TERM_DEBUG=1 genie-term ...（可复制）", err=True
        )
        if os.environ.get("GENIE_TERM_DEBUG") == "1":
            import traceback
            traceback.print_exc(file=sys.stderr)
        sys.exit(exception_to_exit_code(e))


if __name__ == "__main__":
    main()
