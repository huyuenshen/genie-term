"""core/registry.py —— characters 注册表。

完整 Schema（PRD §6.7）：
    # ~/.local/share/genie-term/registry.toml
    schema_version = 1
    [characters.feibi]
    kind = "preset"                   # preset|local|converted
    language = "zh"
    model_version = "v2ProPlus"
    model_dir = "/path/to/tts_models"
    prompt_wav  = "/path/to/prompt.wav"
    prompt_text = "参考音频文本"
    created_at = "2026-11-18T20:12:33+08:00"
    genie_term_version = "0.1.0"

红线（project_rules.md §4）：
  - 写入流程：校验 → 备份 .bak → 临时文件 → os.replace（原子写）
  - 读到更高 schema_version 时拒绝写入并提示升级
  - prompt_wav/prompt_text 对所有 kind 均必填
"""

from __future__ import annotations

import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:
    import tomli as tomllib  # type: ignore[no-redef]

import tomli_w

from .paths import registry_path

CURRENT_SCHEMA_VERSION = 1

VALID_KINDS = {"preset", "local", "converted"}
VALID_LANGUAGES = {"zh", "en", "jp"}
VALID_MODEL_VERSIONS = {"v2", "v2ProPlus"}

# GenieData 必需目录/文件清单（doctor §4.4 第 4 项单一来源）
GENIE_DATA_REQUIRED = [
    "chinese-hubert-base",      # 目录
    "speaker_encoder.onnx",     # 文件（在 GENIE_DATA_DIR 根）
    "G2P/ChineseG2P",           # 目录
    "G2P/EnglishG2P",           # 目录
    "v2/Models",                # 目录
    "v2ProPlus/Models",         # 目录
]

# 所有 kind 均必填的字段
REQUIRED_FIELDS = {
    "kind", "language", "model_version", "model_dir",
    "prompt_wav", "prompt_text", "created_at", "genie_term_version",
}

# 基线 7 个必需文件（v2 和 v2ProPlus 都必须有）
BASELINE_REQUIRED_FILES = [
    "t2s_encoder_fp32.bin",
    "t2s_encoder_fp32.onnx",
    "t2s_first_stage_decoder_fp32.onnx",
    "t2s_shared_fp16.bin",
    "t2s_stage_decoder_fp32.onnx",
    "vits_fp16.bin",
    "vits_fp32.onnx",
]

# v2ProPlus 追加 2 个文件
V2PROPLUS_REQUIRED_FILES = [
    "prompt_encoder_fp16.bin",
    "prompt_encoder_fp32.onnx",
]


class Registry:
    """角色注册表，封装读写/校验/原子写。"""

    def __init__(self, path: Path | None = None):
        self.path = path or registry_path()
        self._data: dict[str, Any] = {}

    # ---------- 读写 ----------

    def load(self) -> dict[str, Any]:
        """加载注册表。不存在则返回空。"""
        if not self.path.exists():
            self._data = {"schema_version": CURRENT_SCHEMA_VERSION, "characters": {}}
            return self._data
        try:
            with open(self.path, "rb") as f:
                self._data = tomllib.load(f)
        except Exception as exc:
            from ..errors import EnvError
            raise EnvError(
                f"注册表损坏: {exc}",
                location=str(self.path),
                fix="删除注册表后重新添加角色",
            ) from exc

        # schema 版本检查
        ver = self._data.get("schema_version", 0)
        if ver > CURRENT_SCHEMA_VERSION:
            from ..errors import EnvError
            raise EnvError(
                f"注册表 schema_version={ver} 高于当前支持的 {CURRENT_SCHEMA_VERSION}",
                location=str(self.path),
                fix="请升级 genie-term",
            )

        # 缺项补全
        if "characters" not in self._data:
            self._data["characters"] = {}
        self._data.setdefault("schema_version", CURRENT_SCHEMA_VERSION)
        return self._data

    def save(self) -> None:
        """原子写：校验 → 备份 → 临时文件 → os.replace。"""
        # 校验每个角色
        for name, char in self._data.get("characters", {}).items():
            errors = self._validate_character(name, char)
            if errors:
                from ..errors import UsageError
                raise UsageError(
                    f"角色 {name} 校验失败:\n  " + "\n  ".join(errors),
                    location=str(self.path),
                )

        self.path.parent.mkdir(parents=True, exist_ok=True)

        # 备份
        if self.path.exists():
            bak = self.path.with_suffix(self.path.suffix + ".bak")
            shutil.copy2(self.path, bak)

        # 原子写
        fd, tmp_path = tempfile.mkstemp(
            dir=str(self.path.parent), suffix=".toml.tmp"
        )
        try:
            with os.fdopen(fd, "wb") as f:
                tomli_w.dump(self._data, f)
            os.replace(tmp_path, self.path)
        except Exception:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise

    # ---------- 查询 ----------

    def list_characters(self) -> dict[str, dict[str, Any]]:
        """返回所有注册角色。"""
        return dict(self._data.get("characters", {}))

    def get(self, name: str) -> dict[str, Any] | None:
        """按名称获取角色，不存在返回 None。"""
        return self._data.get("characters", {}).get(name)

    def exists(self, name: str) -> bool:
        return name in self._data.get("characters", {})

    # ---------- 操作 ----------

    def add(self, name: str, char_data: dict[str, Any], *, force: bool = False) -> None:
        """注册新角色。已存在且非 force → 报错。"""
        if self.exists(name) and not force:
            from ..errors import UsageError
            raise UsageError(
                f"角色 '{name}' 已存在",
                fix=f"genie-term characters remove {name}  # 先删除旧的",
            )

        # 自动推断 model_version（如果没指定）
        if "model_version" not in char_data:
            char_data["model_version"] = self._infer_model_version(
                char_data.get("model_dir", "")
            )

        # 必填字段补全
        char_data.setdefault("created_at", datetime.now(timezone.utc).isoformat())
        from genie_term import __version__
        char_data.setdefault("genie_term_version", __version__)

        # 校验
        errors = self._validate_character(name, char_data)
        if errors:
            from ..errors import UsageError
            raise UsageError(
                "角色校验失败:\n  " + "\n  ".join(errors),
            )

        self._data.setdefault("characters", {})[name] = char_data

    def remove(self, name: str) -> dict[str, Any] | None:
        """移除角色（从注册表删除）。返回被删除的数据，不存在返回 None。"""
        chars = self._data.get("characters", {})
        if name not in chars:
            return None
        return chars.pop(name)

    # ---------- 校验 ----------

    def _validate_character(self, name: str, char: dict[str, Any]) -> list[str]:
        """返回错误列表（空 = 通过）。"""
        errors: list[str] = []

        # 必填字段
        missing = REQUIRED_FIELDS - set(char.keys())
        if missing:
            errors.append(f"缺少必填字段: {', '.join(sorted(missing))}")

        # kind
        if char.get("kind") not in VALID_KINDS:
            errors.append(f"kind={char.get('kind')!r} 非法，允许: {sorted(VALID_KINDS)}")

        # language（上游只支持 zh/en/jp，注册阶段就拒绝）
        if char.get("language") not in VALID_LANGUAGES:
            errors.append(
                f"language={char.get('language')!r} 非法，允许: {sorted(VALID_LANGUAGES)}"
            )

        # model_version
        mv = char.get("model_version")
        if mv not in VALID_MODEL_VERSIONS:
            errors.append(
                f"model_version={mv!r} 非法，允许: {sorted(VALID_MODEL_VERSIONS)}"
            )

        # model_dir 存在
        model_dir = char.get("model_dir", "")
        if model_dir and not Path(model_dir).exists():
            errors.append(f"model_dir 不存在: {model_dir}")

        # prompt_wav 存在
        prompt_wav = char.get("prompt_wav", "")
        if prompt_wav and not Path(prompt_wav).exists():
            errors.append(f"prompt_wav 不存在: {prompt_wav}")

        # prompt_text 非空
        if not char.get("prompt_text"):
            errors.append("prompt_text 不能为空")

        # model_dir 必需文件
        if model_dir and Path(model_dir).exists() and not errors:
            missing_files = self._check_model_files(model_dir, mv or "v2")
            if missing_files:
                errors.append(f"model_dir 缺少必需文件: {', '.join(missing_files)}")

        return errors

    def _check_model_files(self, model_dir: str, version: str) -> list[str]:
        """检查模型目录的必需文件清单。"""
        d = Path(model_dir)
        required = list(BASELINE_REQUIRED_FILES)
        if version == "v2ProPlus":
            required.extend(V2PROPLUS_REQUIRED_FILES)
        return [f for f in required if not (d / f).exists()]

    def _infer_model_version(self, model_dir: str) -> str:
        """自动推断 model_version：有 prompt_encoder_fp32.onnx → v2ProPlus，否则 v2。"""
        d = Path(model_dir)
        if d.exists() and (d / "prompt_encoder_fp32.onnx").exists():
            return "v2ProPlus"
        return "v2"


# ========== 便捷导出 ==========

def load_registry() -> Registry:
    reg = Registry()
    reg.load()
    return reg
