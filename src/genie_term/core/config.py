"""core/config.py —— config.toml 读写/校验/迁移。

写入流程（红线 §4）：校验 → 备份 .bak → 临时文件 → os.replace（原子写）。
读到更高 schema_version 时拒绝写入并提示升级。

完整 Schema（PRD §6.7）：
    schema_version = 1
    [general]
    default_character = "feibi"
    default_language  = "zh"          # zh|en|jp
    output_dir        = "~/Music/genie-term"
    play              = "auto"        # auto|always|never
    if_exists         = "overwrite"   # overwrite|skip|timestamp|fail
    [engine]
    data_dir = ""                     # 空=XDG 默认
    threads  = 0                      # 0=自动
    [network]
    hf_endpoint = "https://huggingface.co"
    offline     = false
    [server]
    host = "127.0.0.1"
    port = 8000
"""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:
    import tomli as tomllib  # type: ignore[no-redef]

import tomli_w

from .paths import config_path, resolve_data_dir

# 当前支持的 schema 版本
CURRENT_SCHEMA_VERSION = 1

# 默认值（PRD §6.7）
DEFAULTS: dict[str, Any] = {
    "schema_version": CURRENT_SCHEMA_VERSION,
    "general": {
        "default_character": "feibi",
        "default_language": "zh",
        "output_dir": "~/Music/genie-term",
        "play": "auto",
        "if_exists": "overwrite",
    },
    "engine": {
        "data_dir": "",
        "threads": 0,
    },
    "network": {
        "hf_endpoint": "https://huggingface.co",
        "offline": False,
    },
    "server": {
        "host": "127.0.0.1",
        "port": 8000,
    },
}

# 允许的值
VALID_LANGUAGES = {"zh", "en", "jp"}
VALID_PLAY_MODES = {"auto", "always", "never"}
VALID_IF_EXISTS = {"overwrite", "skip", "timestamp", "fail"}


class Config:
    """配置对象，封装读写/校验/原子写。"""

    def __init__(self, path: Path | None = None):
        self.path = path or config_path()
        self._data: dict[str, Any] = {}

    # ---------- 读取 ----------

    def load(self) -> dict[str, Any]:
        """加载配置。文件不存在则返回 DEFAULTS。"""
        if not self.path.exists():
            self._data = self._deep_copy(DEFAULTS)
            return self._data
        try:
            with open(self.path, "rb") as f:
                self._data = tomllib.load(f)
        except Exception as exc:
            from ..errors import EnvError
            raise EnvError(
                f"配置文件损坏: {exc}",
                location=str(self.path),
                fix="genie-term config reset --yes",
            ) from exc

        # schema 版本检查
        file_version = self._data.get("schema_version", 0)
        if file_version > CURRENT_SCHEMA_VERSION:
            from ..errors import EnvError
            raise EnvError(
                f"配置 schema_version={file_version} 高于当前支持的 {CURRENT_SCHEMA_VERSION}",
                location=str(self.path),
                fix="请升级 genie-term 到最新版本",
            )

        # 合并默认值（缺项补全）
        self._merge_defaults()
        return self._data

    # ---------- 校验 ----------

    def validate(self) -> list[str]:
        """校验配置值，返回错误列表（空 = 通过）。"""
        errors: list[str] = []
        general = self._data.get("general", {})

        lang = general.get("default_language", "zh")
        if lang not in VALID_LANGUAGES:
            errors.append(
                f"default_language={lang!r} 非法，允许: {sorted(VALID_LANGUAGES)}"
            )

        play = general.get("play", "auto")
        if play not in VALID_PLAY_MODES:
            errors.append(
                f"play={play!r} 非法，允许: {sorted(VALID_PLAY_MODES)}"
            )

        if_exists = general.get("if_exists", "overwrite")
        if if_exists not in VALID_IF_EXISTS:
            errors.append(
                f"if_exists={if_exists!r} 非法，允许: {sorted(VALID_IF_EXISTS)}"
            )

        server = self._data.get("server", {})
        port = server.get("port", 8000)
        if not (1 <= port <= 65535):
            errors.append(f"server.port={port} 非法，应在 1-65535")

        return errors

    # ---------- 写入（原子写） ----------

    def save(self) -> None:
        """原子写 config.toml：校验 → 备份 .bak → 临时文件 → os.replace。"""
        errors = self.validate()
        if errors:
            from ..errors import UsageError
            raise UsageError(
                "配置校验失败:\n  " + "\n  ".join(errors),
                location=str(self.path),
            )

        self._ensure_parent_dir()

        # 备份
        if self.path.exists():
            bak = self.path.with_suffix(self.path.suffix + ".bak")
            shutil.copy2(self.path, bak)

        # 原子写：临时文件 → os.replace
        fd, tmp_path = tempfile.mkstemp(
            dir=str(self.path.parent), suffix=".toml.tmp"
        )
        try:
            with os.fdopen(fd, "wb") as f:
                tomli_w.dump(self._data, f)
            os.replace(tmp_path, self.path)
        except Exception:
            # 清理临时文件
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise

    # ---------- 便捷方法 ----------

    def get(self, key_path: str, default: Any = None) -> Any:
        """点号分隔的 key 路径获取值，如 'general.output_dir'。"""
        keys = key_path.split(".")
        node: Any = self._data
        for k in keys:
            if not isinstance(node, dict) or k not in node:
                return default
            node = node[k]
        return node

    def set(self, key_path: str, value: Any) -> None:
        """点号分隔的 key 路径设值（save() 才持久化）。"""
        keys = key_path.split(".")
        node = self._data
        for k in keys[:-1]:
            node = node.setdefault(k, {})
        node[keys[-1]] = value

    def reset(self) -> None:
        """重置为默认值（save() 才持久化）。"""
        self._data = self._deep_copy(DEFAULTS)

    # ---------- 内部 ----------

    def _ensure_parent_dir(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _merge_defaults(self) -> None:
        """递归合并 DEFAULTS，缺项补全。"""
        for key, default_val in DEFAULTS.items():
            if key not in self._data:
                self._data[key] = self._deep_copy(default_val)
            elif isinstance(default_val, dict) and isinstance(
                self._data[key], dict
            ):
                for sub_key, sub_default in default_val.items():
                    if sub_key not in self._data[key]:
                        self._data[key][sub_key] = self._deep_copy(sub_default)

    @staticmethod
    def _deep_copy(obj: Any) -> Any:
        """简单深拷贝（处理嵌套 dict）。"""
        if isinstance(obj, dict):
            return {k: Config._deep_copy(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [Config._deep_copy(v) for v in obj]
        return obj


# ========== 便捷导出 ==========

def load_config() -> Config:
    """便捷函数：加载并返回 Config 对象。"""
    cfg = Config()
    cfg.load()
    return cfg


def effective_data_dir() -> Path:
    """解析最终生效的数据目录（config engine.data_dir 或平台默认）。"""
    cfg = load_config()
    engine_dir = cfg.get("engine.data_dir", "")
    if engine_dir:
        return Path(engine_dir).expanduser().resolve()
    return resolve_data_dir()
