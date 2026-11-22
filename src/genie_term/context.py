"""context.py —— 全局运行时选项（--quiet / --no-color / --offline）。

PRD §4.1 全局约定：
  - --quiet   抑制 stderr 的进度与提示，仅保留错误
  - --no-color 同时尊重 NO_COLOR 与 TERM=dumb
  - --offline 禁止任何网络请求；缺失资源直接报错并给手动放置路径

这些选项既可从顶级 `genie-term --quiet ...` 设置，也可由子命令覆盖。
"""

from __future__ import annotations

import os
import sys

import typer

_quiet = False
_offline = False


def set_quiet(value: bool) -> None:
    global _quiet
    _quiet = bool(value)


def is_quiet() -> bool:
    return _quiet


def set_no_color(value: bool = True) -> None:
    """尊重 NO_COLOR / TERM=dumb（当前输出链路本身不带颜色）。"""
    if value or os.environ.get("TERM") == "dumb":
        os.environ["NO_COLOR"] = "1"


def set_offline(value: bool) -> None:
    global _offline
    _offline = bool(value)


def is_offline(cli_flag: bool = False) -> bool:
    """是否处于离线模式：CLI 显式开关 > 全局开关 > config network.offline。"""
    if cli_flag or _offline:
        return True
    try:
        from .core.config import load_config

        return bool(load_config().get("network.offline", False))
    except Exception:
        return False


def info(message: str = "", *, err: bool = True) -> None:
    """进度/提示输出；--quiet 时只保留错误（err 且调用方明确为错误时直接用 error）。"""
    if _quiet and err:
        return
    typer.echo(message, err=err)


def error(message: str) -> None:
    """错误输出，--quiet 下也保留。"""
    typer.echo(message, err=True)


def debug_mode() -> bool:
    return os.environ.get("GENIE_TERM_DEBUG") == "1"


def is_tty() -> bool:
    return sys.stdin.isatty()
