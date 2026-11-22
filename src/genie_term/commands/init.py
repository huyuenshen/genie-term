"""commands/init.py —— 首次初始化（5 步）。

PRD §4.3 顺序（每步失败立即停止并给下一步）：
  1 解析数据目录（--data-dir > GENIE_TERM_DATA_DIR > 平台默认）
  2 检查 Python 版本与关键依赖可导入（不 import genie_tts）
  3 磁盘剩余 ≥2GB 否则警告（不阻塞）
  4 下载 GenieData 391MB（进度/断点续传/可重试）
  5 校验必需清单（缺一项即列文件名）
  6 写 config.toml（已存在不覆盖，除非 --force）
  7 打印下一步提示

幂等：重复只校验；--force 才重下。
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

import typer

from genie_term.errors import (
    EnvError,
    NetworkError,
    UsageError,
)

app = typer.Typer(
    name="init",
    help="First-time setup: download resources and create config",
    add_completion=False,
    invoke_without_command=True,
)


# 必需文件清单（与 doctor.py / verify.py 同源）
GENIE_DATA_REQUIRED = [
    "chinese-hubert-base",
    "speaker_encoder.onnx",
    "G2P/ChineseG2P",
    "G2P/EnglishG2P",
    "v2/Models",
    "v2ProPlus/Models",
]

GENIE_DATA_SIZE_MB = 391  # 标称大小，仅供提示


# ========== 步骤实现 ==========

def _step1_resolve_data_dir(cli_data_dir: str | None) -> tuple[Path, Path]:
    """步骤 1：解析数据目录。返回 (data_dir, genie_data_subdir)。"""
    from genie_term.core.paths import resolve_data_dir

    data_dir = resolve_data_dir(cli_data_dir)
    genie_data = data_dir / "GenieData"

    typer.echo(f"[1/7] 数据目录: {data_dir}")
    return data_dir, genie_data


def _step2_check_env() -> None:
    """步骤 2：检查 Python 版本 + 关键依赖（不 import genie_tts）。"""
    typer.echo("[2/7] 检查环境...")

    # Python 版本
    ver = sys.version_info
    if not (ver.major == 3 and 10 <= ver.minor <= 12):
        raise EnvError(
            f"Python {ver.major}.{ver.minor} 不支持",
            fix="安装 Python 3.10–3.12",
        )

    # 关键依赖（不 import genie_tts！）
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
    typer.echo("  ✓ Python 和关键依赖就绪")


def _step3_check_disk(data_dir: Path) -> None:
    """步骤 3：磁盘剩余 ≥2GB，否则警告不阻塞。"""
    typer.echo("[3/7] 检查磁盘...")
    try:
        stat = shutil.disk_usage(str(data_dir))
        free_gb = stat.free / (1024 ** 3)
        if free_gb < 2:
            typer.echo(f"  ⚠ 磁盘仅剩余 {free_gb:.1f} GB（需要 ~2GB）")
        else:
            typer.echo(f"  ✓ 磁盘剩余 {free_gb:.1f} GB")
    except Exception as exc:
        typer.echo(f"  ⚠ 磁盘检查跳过: {exc}")


def _step4_download(genie_data: Path, mirror: str | None, yes: bool, force: bool) -> None:
    """步骤 4：下载 GenieData（391MB）。"""
    typer.echo(f"[4/7] 下载 GenieData（约 {GENIE_DATA_SIZE_MB} MB）...")

    if genie_data.exists() and not force:
        typer.echo("  已存在，跳过下载（用 --force 重下）")
        return

    if not yes and not sys.stdin.isatty():
        raise UsageError(
            "非交互式环境下下载需要 --yes",
            fix="genie-term init --yes",
        )
    if not yes and sys.stdin.isatty():
        confirm = typer.confirm(f"确认下载约 {GENIE_DATA_SIZE_MB} MB 到 {genie_data}？")
        if not confirm:
            raise typer.Exit(code=0)

    # 确保父目录存在
    genie_data.parent.mkdir(parents=True, exist_ok=True)

    # 设置 HF_ENDPOINT
    endpoint = mirror or "https://huggingface.co"
    os.environ.setdefault("HF_ENDPOINT", endpoint)

    try:
        from huggingface_hub import snapshot_download
        typer.echo(f"  HF 端点: {endpoint}")
        typer.echo("  下载中（进度在下方）...")
        snapshot_download(
            repo_id="High-Logic/Genie",
            repo_type="model",
            allow_patterns="GenieData/**",
            local_dir=str(genie_data.parent),
            local_dir_use_symlinks=False,
        )
        typer.echo("  ✓ 下载完成")
    except Exception as exc:
        raise NetworkError(
            f"下载失败: {exc}",
            location=str(genie_data),
            fix="genie-term config set network.hf_endpoint https://hf-mirror.com",
        ) from exc


def _step5_verify(genie_data: Path) -> None:
    """步骤 5：校验必需文件清单。"""
    typer.echo("[5/7] 校验必需文件...")
    missing = [req for req in GENIE_DATA_REQUIRED if not (genie_data / req).exists()]
    if missing:
        raise EnvError(
            f"GenieData 缺少必需文件: {', '.join(missing)}",
            location=str(genie_data),
            fix="genie-term init --force",
        )
    typer.echo(f"  ✓ {len(GENIE_DATA_REQUIRED)} 项必需文件齐全")


def _step6_write_config(data_dir: Path, force: bool) -> None:
    """步骤 6：写 config.toml（已存在不覆盖，除非 --force）。"""
    from genie_term.core.config import Config, config_path

    path = config_path()
    typer.echo(f"[6/7] 配置文件: {path}")

    if path.exists() and not force:
        typer.echo("  已存在，跳过写入（用 --force 重置）")
        return

    path.parent.mkdir(parents=True, exist_ok=True)
    cfg = Config(path)
    cfg.load()  # 加载默认值
    if str(data_dir) != str(cfg.get("engine.data_dir", "")):
        cfg.set("engine.data_dir", str(data_dir))
    cfg.save()
    typer.echo("  ✓ 配置已写入")


def _step7_print_next() -> None:
    """步骤 7：打印下一步。"""
    typer.echo("")
    typer.echo("=" * 50)
    typer.echo("✅ genie-term 初始化完成！")
    typer.echo("")
    typer.echo("下一步：")
    typer.echo("  genie-term characters list          # 查看可用角色")
    typer.echo("  genie-term download character feibi  # 下载预置角色")
    typer.echo("  genie-term say -c feibi '你好'       # 合成测试")
    typer.echo("=" * 50)


# ========== Typer 命令 ==========

@app.callback(invoke_without_command=True)
def _callback(
    ctx: typer.Context,
    data_dir: str | None = typer.Option(None, "--data-dir", help="Override data directory"),
    mirror: str | None = typer.Option(None, "--mirror", help="HF mirror endpoint"),
    yes: bool = typer.Option(False, "--yes", help="Skip interactive confirmation"),
    force: bool = typer.Option(False, "--force", help="Redownload even if exists"),
) -> None:
    """First-time setup: download GenieData and create config."""
    if ctx.invoked_subcommand is not None:
        return

    typer.echo("genie-term init —— 首次初始化")
    typer.echo("=" * 50)

    # 步骤 1
    data_dir, genie_data = _step1_resolve_data_dir(data_dir)
    # 步骤 2
    _step2_check_env()
    # 步骤 3
    _step3_check_disk(data_dir)
    # 步骤 4
    _step4_download(genie_data, mirror, yes, force)
    # 步骤 5
    _step5_verify(genie_data)
    # 步骤 6
    _step6_write_config(data_dir, force)
    # 步骤 7
    _step7_print_next()

    raise typer.Exit(code=0)
