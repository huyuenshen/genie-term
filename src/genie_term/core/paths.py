"""core/paths.py —— 经 platformdirs 做目录解析。

Linux 走 XDG 规范；macOS 走 ~/Library/Application Support|Logs|Caches。
红线：禁止硬编码 ~/.local/... 或 /home/...；一律经 platformdirs。
"""

from __future__ import annotations

import os
from pathlib import Path

import platformdirs

# ========== 环境变量优先级 ==========
# CLI 参数 > GENIE_TERM_DATA_DIR > 平台默认
ENV_DATA_DIR = "GENIE_TERM_DATA_DIR"
ENV_CONFIG_DIR = "GENIE_TERM_CONFIG_DIR"
ENV_LOG_DIR = "GENIE_TERM_LOG_DIR"
ENV_CACHE_DIR = "GENIE_TERM_CACHE_DIR"

APP_NAME = "genie-term"
APP_AUTHOR = "genie-term"


# ========== 目录解析函数 ==========

def resolve_data_dir(cli_override: str | None = None) -> Path:
    """解析数据目录（GenieData、CharacterModels、registry 等）。

    优先级：CLI --data-dir > GENIE_TERM_DATA_DIR > platformdirs.user_data_dir
    """
    if cli_override:
        return Path(cli_override).expanduser().resolve()
    env_val = os.environ.get(ENV_DATA_DIR)
    if env_val:
        return Path(env_val).expanduser().resolve()
    return Path(platformdirs.user_data_dir(APP_NAME, APP_AUTHOR))


def resolve_config_dir() -> Path:
    """解析配置目录（config.toml）。"""
    env_val = os.environ.get(ENV_CONFIG_DIR)
    if env_val:
        return Path(env_val).expanduser().resolve()
    return Path(platformdirs.user_config_dir(APP_NAME, APP_AUTHOR))


def resolve_log_dir() -> Path:
    """解析日志目录（genie-term.log）。"""
    env_val = os.environ.get(ENV_LOG_DIR)
    if env_val:
        return Path(env_val).expanduser().resolve()
    # platformdirs 对 macOS 返回 ~/Library/Logs，Linux 走 XDG_STATE_HOME
    return Path(platformdirs.user_state_dir(APP_NAME, APP_AUTHOR)) / "logs"


def resolve_cache_dir() -> Path:
    """解析缓存目录（临时文件、下载断点续传状态等）。"""
    env_val = os.environ.get(ENV_CACHE_DIR)
    if env_val:
        return Path(env_val).expanduser().resolve()
    return Path(platformdirs.user_cache_dir(APP_NAME, APP_AUTHOR))


# ========== 具体文件路径 ==========

def config_path() -> Path:
    return resolve_config_dir() / "config.toml"


def registry_path() -> Path:
    return resolve_data_dir() / "registry.toml"


def genie_data_dir(data_dir: Path | None = None) -> Path:
    base = data_dir or resolve_data_dir()
    return base / "GenieData"


def character_models_dir(data_dir: Path | None = None) -> Path:
    base = data_dir or resolve_data_dir()
    return base / "CharacterModels"


def log_file() -> Path:
    return resolve_log_dir() / "genie-term.log"


def tmp_dir() -> Path:
    return resolve_cache_dir() / "tmp"


# ========== 初始化 ==========

def ensure_dirs() -> None:
    """创建所有必需目录（幂等）。"""
    for d in [
        resolve_data_dir(),
        resolve_config_dir(),
        resolve_log_dir(),
        resolve_cache_dir(),
        tmp_dir(),
    ]:
        d.mkdir(parents=True, exist_ok=True)
