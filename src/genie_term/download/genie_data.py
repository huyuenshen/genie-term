"""download/genie_data.py —— GenieData 下载。

红线（project_rules.md §4）：
  - 禁止调用上游 download_genie_data()（它 local_dir="." 污染 CWD）
  - 用 huggingface_hub.snapshot_download 指定绝对目录
  - pattern 用 GenieData/** 匹配多层级

陷阱 3 对策：绝对目录 snapshot_download。
"""

from __future__ import annotations

import os
from pathlib import Path

from ..errors import NetworkError

REPO_ID = "High-Logic/Genie"
REPO_TYPE = "model"


def download_genie_data(
    target_dir: str | Path,
    mirror: str | None = None,
    *,
    force: bool = False,
) -> Path:
    """下载 GenieData 到绝对目录。

    Args:
        target_dir: 绝对目录（下载后 target_dir/GenieData 存在）
        mirror: HF 镜像端点，None 用默认
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

    # 设置 HF_ENDPOINT（在 import huggingface_hub 之前）
    if mirror:
        os.environ["HF_ENDPOINT"] = mirror

    try:
        from huggingface_hub import snapshot_download

        snapshot_download(
            repo_id=REPO_ID,
            repo_type=REPO_TYPE,
            allow_patterns="GenieData/**",
            local_dir=str(target),
            local_dir_use_symlinks=False,
            resume_download=True,
            max_workers=4,
        )
    except Exception as exc:
        raise NetworkError(
            f"下载 GenieData 失败: {exc}",
            location=str(target),
            fix="genie-term config set network.hf_endpoint https://hf-mirror.com",
        ) from exc

    return genie_data


def download_character(
    target_dir: str | Path,
    character_name: str,
    mirror: str | None = None,
) -> Path:
    """下载预置角色（模型 + prompt_wav.json）。

    Args:
        target_dir: 数据根目录（下载后 target_dir/CharacterModels/... 存在）
        character_name: 角色名（feibi/mika/thirtyseven）
        mirror: HF 镜像端点

    Returns:
        角色模型目录路径
    """
    target = Path(target_dir).resolve()
    if mirror:
        os.environ["HF_ENDPOINT"] = mirror

    try:
        from huggingface_hub import snapshot_download

        # 下载整个仓库的 CharacterModels 部分
        snapshot_download(
            repo_id=REPO_ID,
            repo_type=REPO_TYPE,
            allow_patterns=f"CharacterModels/**/{character_name}/**",
            local_dir=str(target),
            local_dir_use_symlinks=False,
            resume_download=True,
            max_workers=4,
        )
    except Exception as exc:
        raise NetworkError(
            f"下载角色 {character_name} 失败: {exc}",
            location=str(target),
            fix="genie-term config set network.hf_endpoint https://hf-mirror.com",
        ) from exc

    # 找到实际下载的目录
    models_dir = target / "CharacterModels"
    for sub in ["v2ProPlus", "v2"]:
        candidate = models_dir / sub / character_name
        if candidate.exists():
            return candidate

    raise NetworkError(
        f"角色 {character_name} 下载后未找到目录",
        location=str(target),
    )


def download_roberta(
    target_dir: str | Path,
    mirror: str | None = None,
) -> Path:
    """自实现 RoBERTa 下载（陷阱 6：上游未导出 download_roberta_data）。

    如果仓库无 GenieData/RoBERTa 路径 → V1 下线（返回路径不存在，不报错）。
    """
    target = Path(target_dir).resolve()
    genie_data = target / "GenieData"
    roberta_dir = genie_data / "RoBERTa"

    if roberta_dir.exists():
        return roberta_dir

    genie_data.mkdir(parents=True, exist_ok=True)
    if mirror:
        os.environ["HF_ENDPOINT"] = mirror

    try:
        from huggingface_hub import snapshot_download

        snapshot_download(
            repo_id=REPO_ID,
            repo_type=REPO_TYPE,
            allow_patterns="GenieData/RoBERTa/**",
            local_dir=str(genie_data),
            local_dir_use_symlinks=False,
            resume_download=True,
            max_workers=4,
        )
    except Exception:
        # RoBERTa 是可选的，仓库没这个路径不算致命
        return roberta_dir

    return roberta_dir
