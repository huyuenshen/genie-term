"""engine/bootstrap.py —— 引擎前置环境注入。

红线（project_rules.md §4）：
  - GENIE_DATA_DIR / HF_ENDPOINT 必须在 import genie_tts 之前设置
  - 进程内只允许一次（上游在模块导入时固化这些变量，事后设无效）

本模块只做：env 注入、离线检查、版本探测。
不 import genie_tts（adapter.py 才 import）。
"""

from __future__ import annotations

import os

# 是否已注入（进程内只做一次）
_env_injected = False


def ensure_env(
    data_dir: str | None = None,
    hf_endpoint: str | None = None,
    offline: bool = False,
) -> None:
    """在 import genie_tts 前注入必需的环境变量。

    调用幂等：第二次调用只 warn，不覆盖已有值。
    """
    global _env_injected
    if _env_injected:
        return

    # GENIE_DATA_DIR
    if data_dir:
        os.environ["GENIE_DATA_DIR"] = data_dir
    # 注意：如果调用方已经在之前设过，我们保留已有值

    # HF_ENDPOINT
    if hf_endpoint:
        os.environ["HF_ENDPOINT"] = hf_endpoint

    # 离线模式
    if offline:
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"

    _env_injected = True


def is_env_injected() -> bool:
    return _env_injected
