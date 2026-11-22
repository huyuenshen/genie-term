"""download/genie_data.py —— GenieData 下载。

红线（project_rules.md §4）：
  - 禁止调用上游 download_genie_data()（它 local_dir="." 污染 CWD）
  - 用 huggingface_hub.snapshot_download 指定绝对目录
  - pattern 用 GenieData/** 匹配多层级
  - HF_ENDPOINT 必须在 import huggingface_hub 之前设置

注意：huggingface_hub >= 1.0 已移除 `local_dir_use_symlinks` 与
`resume_download` 参数（断点续传为默认行为），这里只传受支持的参数。
"""

from __future__ import annotations

import os
from pathlib import Path

from ..errors import NetworkError

REPO_ID = "High-Logic/Genie"
REPO_TYPE = "model"


def _prepare_endpoint(endpoint: str | None) -> None:
    """在 import huggingface_hub 之前设置 HF_ENDPOINT。

    未显式传镜像时，读取 config network.hf_endpoint（PRD §4.7）。
    """
    if endpoint is None:
        try:
            from ..core.config import load_config

            endpoint = load_config().get("network.hf_endpoint") or None
        except Exception:
            endpoint = None
    if endpoint:
        os.environ["HF_ENDPOINT"] = endpoint


def _snapshot(target: Path, pattern: str, endpoint: str | None) -> None:
    _prepare_endpoint(endpoint)
    from huggingface_hub import snapshot_download

    snapshot_download(
        repo_id=REPO_ID,
        repo_type=REPO_TYPE,
        allow_patterns=pattern,
        local_dir=str(target),
        max_workers=4,
    )


def download_genie_data(
    target_dir: str | Path,
    mirror: str | None = None,
    *,
    force: bool = False,
) -> Path:
    """下载 GenieData 到绝对目录。

    Args:
        target_dir: 数据根目录（下载后 target_dir/GenieData 存在）
        mirror: HF 镜像端点，None 用环境变量/默认
        force: 已存在时是否重下

    Returns:
        GenieData 子目录路径

    Raises:
        NetworkError: 下载失败（DNS/403/超时/磁盘满）
    """
    target = Path(target_dir).resolve()
    genie_data = target / "GenieData"

    if genie_data.exists() and not force:
        return genie_data

    target.mkdir(parents=True, exist_ok=True)
    try:
        _snapshot(target, "GenieData/**", mirror)
    except Exception as exc:
        raise NetworkError(
            f"下载 GenieData 失败: {exc}",
            location=str(target),
            fix="genie-term config set network.hf_endpoint https://hf-mirror.com",
        ) from exc

    return genie_data


def find_character_dir(target_dir: str | Path, character_name: str) -> Path | None:
    """在数据目录中定位已下载的角色根目录。"""
    models_dir = Path(target_dir).resolve() / "CharacterModels"
    for sub in ("v2ProPlus", "v2"):
        candidate = models_dir / sub / character_name
        if candidate.exists():
            return candidate
    return None


def download_character(
    target_dir: str | Path,
    character_name: str,
    mirror: str | None = None,
) -> Path:
    """下载预置角色（模型 + prompt_wav.json）到绝对目录。"""
    target = Path(target_dir).resolve()
    try:
        _snapshot(target, f"CharacterModels/**/{character_name}/**", mirror)
    except Exception as exc:
        raise NetworkError(
            f"下载角色 {character_name} 失败: {exc}",
            location=str(target),
            fix="genie-term config set network.hf_endpoint https://hf-mirror.com",
        ) from exc

    candidate = find_character_dir(target, character_name)
    if candidate is not None:
        return candidate

    raise NetworkError(
        f"角色 {character_name} 下载后未找到目录",
        location=str(target / "CharacterModels"),
        fix="检查仓库结构或运行 genie-term doctor",
    )


def download_roberta(
    target_dir: str | Path,
    mirror: str | None = None,
) -> Path:
    """自实现 RoBERTa 下载（陷阱 6：上游未导出 download_roberta_data）。

    仓库无 GenieData/RoBERTa 路径时视为可选组件缺失，返回不存在的路径。
    """
    target = Path(target_dir).resolve()
    genie_data = target / "GenieData"
    roberta_dir = genie_data / "RoBERTa"

    if roberta_dir.exists():
        return roberta_dir

    genie_data.mkdir(parents=True, exist_ok=True)
    try:
        # 与 GenieData 同构：local_dir 指向数据根目录，pattern 带 GenieData 前缀
        _snapshot(target, "GenieData/RoBERTa/**", mirror)
    except Exception:
        # RoBERTa 是可选的，仓库没这个路径不算致命
        return roberta_dir

    return roberta_dir
