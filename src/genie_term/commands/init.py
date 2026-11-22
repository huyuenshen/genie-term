"""commands/init.py —— 首次初始化（7 步）。

PRD §4.3 顺序（每步失败立即停止并给下一步）：
  1 解析数据目录（--data-dir > GENIE_TERM_DATA_DIR > 平台默认）
  2 检查 Python 版本与关键依赖可导入（不 import genie_tts）
  3 磁盘剩余 ≥2GB 否则警告（不阻塞）
  4 下载 GenieData 391MB（进度/断点续传/可重试）
  5 校验必需清单（缺一项即列文件名）
  6 写 config.toml（已存在不覆盖，除非 --force）
  7 打印下一步提示

幂等：重复只校验；--force 才重下。
离线：使用 --offline 时只校验并打印手动放置路径（PRD §5.4）。
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import typer

from genie_term import context
from genie_term.core.registry import GENIE_DATA_REQUIRED
from genie_term.errors import EnvError, UsageError

app = typer.Typer(
    name="init",
    help="First-time setup: download resources and create config",
    add_completion=False,
    invoke_without_command=True,
)

GENIE_DATA_SIZE_MB = 391  # 标称大小，仅供提示


# ========== 步骤实现 ==========

def _step1_resolve_data_dir(cli_data_dir: str | None) -> Path:
    from genie_term.core.paths import resolve_data_dir

    data_dir = resolve_data_dir(cli_data_dir)
    context.info(f"[1/7] 数据目录: {data_dir}")
    return data_dir


def _step2_check_env() -> None:
    """检查 Python 版本 + 关键依赖（不 import genie_tts）。"""
    context.info("[2/7] 检查环境...")

    ver = sys.version_info
    if not (ver.major == 3 and 10 <= ver.minor <= 12):
        raise EnvError(
            f"Python {ver.major}.{ver.minor} 不支持",
            fix="安装 Python 3.10–3.12（或 pipx install --python python3.12 genie-term）",
        )

    critical = ["onnxruntime", "typer", "rich", "platformdirs"]
    missing = []
    for pkg in critical:
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)

    if missing:
        raise EnvError(
            f"缺少关键依赖: {', '.join(missing)}",
            fix="pipx reinstall genie-term",
        )
    context.info("  ✓ Python 和关键依赖就绪")


def _step3_check_disk(data_dir: Path) -> None:
    context.info("[3/7] 检查磁盘...")
    try:
        data_dir.mkdir(parents=True, exist_ok=True)
        free_gb = shutil.disk_usage(str(data_dir)).free / (1024 ** 3)
        if free_gb < 2:
            context.info(f"  ⚠ 磁盘仅剩余 {free_gb:.1f} GB（需要 ~2GB）")
        else:
            context.info(f"  ✓ 磁盘剩余 {free_gb:.1f} GB")
    except Exception as exc:  # noqa: BLE001 - 磁盘检查失败不阻塞
        context.info(f"  ⚠ 磁盘检查跳过: {exc}")


def _verify(genie_data: Path) -> list[str]:
    return [req for req in GENIE_DATA_REQUIRED if not (genie_data / req).exists()]


def _step4_download(
    data_dir: Path,
    *,
    mirror: str | None,
    yes: bool,
    force: bool,
    offline: bool,
) -> None:
    context.info(f"[4/7] 下载 GenieData（约 {GENIE_DATA_SIZE_MB} MB）...")
    genie_data = data_dir / "GenieData"

    if context.is_offline(offline):
        missing = _verify(genie_data)
        if missing:
            raise EnvError(
                f"离线模式下缺少 GenieData 资源: {', '.join(missing)}",
                location=str(genie_data),
                fix=f"在有网机器运行 genie-term init，再把 GenieData 整个目录放到 {genie_data}",
            )
        context.info("  ✓ 离线模式：资源已齐全，跳过下载")
        return

    if genie_data.exists() and not force and not _verify(genie_data):
        context.info("  已存在且完整，跳过下载（用 --force 重下）")
        return

    if not yes and not sys.stdin.isatty():
        raise UsageError(
            "非交互式环境下下载需要 --yes",
            fix="genie-term init --yes",
        )
    if not yes and sys.stdin.isatty() and not typer.confirm(
        f"确认下载约 {GENIE_DATA_SIZE_MB} MB 到 {genie_data}？"
    ):
        raise typer.Exit(code=0)

    from genie_term.download.genie_data import download_genie_data

    endpoint = mirror
    if endpoint is None:
        from genie_term.core.config import load_config

        endpoint = load_config().get("network.hf_endpoint") or None

    context.info(f"  HF 端点: {endpoint or '环境变量/默认'}")
    context.info("  下载中（进度在下方）...")
    download_genie_data(data_dir, mirror=endpoint, force=force)
    context.info("  ✓ 下载完成")


def _step5_verify(data_dir: Path) -> None:
    context.info("[5/7] 校验必需文件...")
    genie_data = data_dir / "GenieData"
    missing = _verify(genie_data)
    if missing:
        raise EnvError(
            f"GenieData 缺少必需文件: {', '.join(missing)}",
            location=str(genie_data),
            fix=f"genie-term init --force  # 或手动放到 {genie_data}",
        )
    context.info(f"  ✓ {len(GENIE_DATA_REQUIRED)} 项必需资源齐全")


def _step6_write_config(data_dir: Path, force: bool) -> None:
    from genie_term.core.config import Config, config_path

    path = config_path()
    context.info(f"[6/7] 配置文件: {path}")

    if path.exists() and not force:
        context.info("  已存在，跳过写入（用 --force 覆盖）")
        return

    path.parent.mkdir(parents=True, exist_ok=True)
    cfg = Config(path)
    cfg.load()
    cfg.set("engine.data_dir", str(data_dir))
    cfg.save()
    context.info("  ✓ 配置已写入")


def _step7_print_next() -> None:
    context.info("")
    context.info("=" * 50)
    context.info("✅ genie-term 初始化完成！")
    context.info("")
    context.info("下一步：")
    context.info("  genie-term say -c feibi '你好，世界'   # 首次会自动下载约 230MB 角色")
    context.info("  genie-term doctor                     # 环境自检")
    context.info("=" * 50)


# ========== Typer 命令 ==========

@app.callback(invoke_without_command=True)
def _callback(
    ctx: typer.Context,
    data_dir: str | None = typer.Option(None, "--data-dir", help="Override data directory"),
    mirror: str | None = typer.Option(None, "--mirror", help="HF mirror endpoint"),
    yes: bool = typer.Option(False, "--yes", help="Skip interactive confirmation"),
    force: bool = typer.Option(False, "--force", help="Redownload even if exists"),
    offline: bool = typer.Option(False, "--offline", help="只校验，不联网"),
) -> None:
    """First-time setup: download GenieData and create config."""
    if ctx.invoked_subcommand is not None:
        return

    context.info("genie-term init —— 首次初始化")
    context.info("=" * 50)

    resolved = _step1_resolve_data_dir(data_dir)
    _step2_check_env()
    _step3_check_disk(resolved)
    _step4_download(
        resolved, mirror=mirror, yes=yes, force=force, offline=offline
    )
    _step5_verify(resolved)
    _step6_write_config(resolved, force)
    _step7_print_next()

    raise typer.Exit(code=0)
