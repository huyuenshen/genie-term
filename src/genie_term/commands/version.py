"""commands/version.py —— version 命令实现。

被 cli.py 直接调用（不作为独立 typer app）。
"""

from __future__ import annotations

import json as _json
import platform
from typing import Any

from genie_term import __version__


def run_version(json: bool = False) -> None:
    """Print genie-term version and dependency info.

    Args:
        json: True 则输出 JSON 对象到 stdout
    """
    # 延迟 import，避免顶层加载重依赖
    from genie_term.engine.adapter import get_engine_versions

    versions = get_engine_versions()
    info: dict[str, Any] = {
        "genie_term": __version__,
        "genie_tts": versions["genie_tts"],
        "onnxruntime": versions["onnxruntime"],
        "python": platform.python_version(),
        "platform": platform.platform(),
        "machine": platform.machine(),
    }

    import typer

    if json:
        typer.echo(_json.dumps(info, ensure_ascii=False))
    else:
        typer.echo(f"genie-term {info['genie_term']}")
        typer.echo(f"genie-tts  {info['genie_tts'] or 'not installed'}")
        typer.echo(f"onnxruntime {info['onnxruntime'] or 'not installed'}")
        typer.echo(f"Python {info['python']}")
        typer.echo(f"Platform {info['platform']} ({info['machine']})")
