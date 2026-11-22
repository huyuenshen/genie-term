"""cli.py —— genie-term 主入口。

红线（project_rules.md §5）：
  - 顶层禁止 import onnxruntime/genie_tts（否则 --help 超 400ms）
  - 只做 typer 装配、全局选项解析、命令分发、异常→退出码映射

退出码严格按 PRD §4.1。
"""

from __future__ import annotations

import contextlib
import os
import sys

import typer

try:  # typer >= 0.16 vendors click；用同一份异常类型做退出码映射
    from typer import _click as _tclick
except ImportError:  # pragma: no cover - 旧版 typer
    import click as _tclick  # type: ignore[no-redef]

from genie_term import context
from genie_term.errors import (
    EXIT_INTERRUPT,
    EXIT_OK,
    EXIT_USAGE,
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

@app.callback(invoke_without_command=True)
def _main_callback(
    ctx: typer.Context,
    version_flag: bool | None = typer.Option(
        None, "--version", "-V", help="Print version info and exit.",
        is_eager=True,
    ),
    quiet: bool = typer.Option(
        False, "--quiet", "-q", help="抑制进度与提示，仅保留错误（PRD §4.1）",
    ),
    no_color: bool = typer.Option(
        False, "--no-color", help="禁用颜色，同时尊重 NO_COLOR / TERM=dumb",
    ),
    offline: bool = typer.Option(
        False, "--offline", help="禁止任何网络请求（PRD §4.1）",
    ),
) -> None:
    """genie-term CLI —— Unix-like GenieTTS 封装。"""
    if quiet:
        context.set_quiet(True)
    if no_color:
        context.set_no_color(True)
    if offline:
        context.set_offline(True)

    if version_flag:
        from genie_term.commands.version import run_version
        run_version(json=False)
        raise typer.Exit(code=EXIT_OK)


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

def _print_usage_error(exc: _tclick.exceptions.UsageError) -> None:
    message = exc.format_message()
    context.error(f"[错误] {message}")
    context.error("  下一步: genie-term --help  # 查看可用命令与参数")


def main() -> None:
    """genie-term CLI 主入口。

    异常处理策略（PRD §4.1 / §7）：
    - GenieTermError 子类：打印格式化错误 + 使用其 code 属性
    - click 用法错误（未知命令/未知参数）：退出码 2
    - KeyboardInterrupt / Abort：退出码 130
    - BrokenPipeError（| head -1）：安静退出，不打印 traceback
    - 未知异常：退出码 20（仅 debug 模式打印堆栈）
    """
    try:
        app(standalone_mode=False)
        with contextlib.suppress(BrokenPipeError):
            sys.stdout.flush()
    except typer.Exit as e:
        sys.exit(e.exit_code)
    except typer.Abort:
        sys.exit(EXIT_INTERRUPT)
    except _tclick.exceptions.UsageError as e:
        _print_usage_error(e)
        sys.exit(EXIT_USAGE)
    except _tclick.exceptions.ClickException as e:
        e.show()
        sys.exit(EXIT_USAGE)
    except KeyboardInterrupt:
        sys.exit(EXIT_INTERRUPT)
    except BrokenPipeError:
        # 管道被提前关闭（如 | head -1）：静默退出，不产生 traceback
        with contextlib.suppress(Exception):
            sys.stdout.close()
        sys.exit(EXIT_OK)
    except GenieTermError as e:
        context.error(str(e))
        sys.exit(e.code)
    except Exception as e:
        context.error(f"[错误] 未预期的内部错误: {e}")
        context.error("  下一步: GENIE_TERM_DEBUG=1 genie-term ...（可复制）")
        if os.environ.get("GENIE_TERM_DEBUG") == "1":
            import traceback
            traceback.print_exc(file=sys.stderr)
        sys.exit(exception_to_exit_code(e))


if __name__ == "__main__":
    main()
