"""download/verify.py —— 必需文件清单 + 校验函数。

单一来源：doctor §4.4 第 4 项 + characters §4.6 add 校验都从此导入。
清单定义在 core/registry.py（BASELINE_REQUIRED_FILES + V2PROPLUS_REQUIRED_FILES）。
"""

from __future__ import annotations

from pathlib import Path

# 从 registry 导入（单一来源）
from ..core.registry import (
    BASELINE_REQUIRED_FILES,
    GENIE_DATA_REQUIRED,
    V2PROPLUS_REQUIRED_FILES,
)


def verify_genie_data(genie_data_dir: str | Path) -> list[str]:
    """校验 GenieData 必需目录/文件。返回缺失列表（空 = 通过）。"""
    d = Path(genie_data_dir)
    missing = []
    for req in GENIE_DATA_REQUIRED:
        if not (d / req).exists():
            missing.append(req)
    return missing


def verify_model_files(model_dir: str | Path, version: str = "v2") -> list[str]:
    """校验角色模型目录的必需文件。返回缺失列表（空 = 通过）。"""
    d = Path(model_dir)
    if not d.exists():
        return ["目录不存在"]

    required = list(BASELINE_REQUIRED_FILES)
    if version == "v2ProPlus":
        required.extend(V2PROPLUS_REQUIRED_FILES)

    return [f for f in required if not (d / f).exists()]
