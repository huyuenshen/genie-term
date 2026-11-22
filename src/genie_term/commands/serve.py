"""commands/serve.py —— 启动本地 HTTP API 服务。

PRD §4.9：
  genie-term serve [--host 127.0.0.1] [--port 8000] [--workers 1]
                   [--preload NAME] [--allow-public] [--json]

关键约束：
  - 默认只监听 127.0.0.1
  - --host 0.0.0.0 必须 --allow-public + TTY 二次确认，否则码 2
  - --workers 上限 1（上游进程内全局单例，多 worker 只增内存）
  - 上游 API 无鉴权，README 明示「不要裸奔公网」
  - 启动后 stdout 打印一行 JSON（--json）或人类可读提示
"""

from __future__ import annotations

import json
import sys

import typer

from genie_term import context
from genie_term.errors import UsageError

app = typer.Typer(
    name="serve",
    help="启动本地 HTTP API 服务（上游 FastAPI，无鉴权）",
    add_completion=False,
    invoke_without_command=True,
)

MAX_WORKERS = 1  # 上游进程内全局单例，多 worker 无意义


@app.callback(invoke_without_command=True)
def _callback(
    ctx: typer.Context,
    host: str = typer.Option("127.0.0.1", "--host", help="监听地址（默认 127.0.0.1）"),
    port: int = typer.Option(8000, "--port", help="监听端口"),
    workers: int = typer.Option(1, "--workers", help=f"Worker 数（上限 {MAX_WORKERS}）"),
    preload: str | None = typer.Option(None, "--preload", help="启动时预加载的角色名"),
    allow_public: bool = typer.Option(False, "--allow-public", help="允许 0.0.0.0 监听（危险！）"),
    json_flag: bool = typer.Option(False, "--json", help="输出启动信息 JSON"),
) -> None:
    if ctx.invoked_subcommand is not None:
        return

    if workers > MAX_WORKERS:
        raise UsageError(
            f"--workers 不能超过 {MAX_WORKERS}（上游进程内全局单例，多 worker 只增内存不增吞吐）",
            fix=f"genie-term serve --workers {MAX_WORKERS}",
        )

    if host in ("0.0.0.0", "::"):
        if not allow_public:
            raise UsageError(
                f"监听 {host} 需要显式 --allow-public",
                fix=f"genie-term serve --host {host} --allow-public",
            )
        if not sys.stdin.isatty():
            raise UsageError(
                f"非交互式环境拒绝公开监听 {host}（需要 TTY 二次确认）",
                fix=f"在交互式终端运行: genie-term serve --host {host} --allow-public",
            )
        context.error("⚠ 安全警告: 即将监听所有网络接口 (0.0.0.0)")
        context.error("  上游 API **无鉴权**，网络上任何人都能访问你的 TTS 服务！")
        if not typer.confirm("确认继续？"):
            raise typer.Exit(code=0)

    from genie_term.core.config import effective_data_dir
    from genie_term.engine.bootstrap import ensure_env

    data_dir = effective_data_dir()
    ensure_env(data_dir=str(data_dir))

    if preload:
        context.info(f"预加载角色: {preload}", )
        from genie_term.core.registry import load_registry
        from genie_term.engine import adapter

        char = load_registry().get(preload)
        if not char:
            context.info(f"⚠ 角色 '{preload}' 未注册，跳过预加载")
        elif char.get("kind") == "preset":
            adapter.load_predefined_character(preload, data_dir)
        else:
            adapter.load_character(
                preload, char["model_dir"], char.get("language", "zh")
            )

    docs = f"http://{host}:{port}/docs"
    if json_flag:
        typer.echo(json.dumps(
            {"host": host, "port": port, "docs": docs}, ensure_ascii=False
        ))
    else:
        context.info(f"启动 genie-term API 服务 → http://{host}:{port}")
        context.info(f"接口文档: {docs}")
    if host in ("0.0.0.0", "::"):
        context.info("⚠ 公开监听中，注意防火墙！")

    from genie_term.engine import adapter as engine

    try:
        engine.serve(host=host, port=port, workers=workers)
    except Exception as exc:  # noqa: BLE001 - 统一转 EngineError
        from genie_term.errors import EngineError

        raise EngineError(
            f"服务启动失败: {exc}",
            fix="运行 genie-term doctor 检查环境",
        ) from exc
