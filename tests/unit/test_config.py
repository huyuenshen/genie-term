"""tests/unit/test_config.py —— config.toml 读写/校验/原子写。"""

from __future__ import annotations

import pytest

from genie_term.core.config import (
    DEFAULTS,
    VALID_IF_EXISTS,
    VALID_LANGUAGES,
    VALID_PLAY_MODES,
    Config,
)


class TestConfigDefaults:
    def test_load_when_file_missing_returns_defaults(self, isolated_env):
        cfg = Config()
        data = cfg.load()
        assert data["schema_version"] == 1
        assert data["general"]["default_character"] == "feibi"
        assert data["general"]["default_language"] == "zh"
        assert data["network"]["hf_endpoint"] == "https://huggingface.co"
        assert data["server"]["host"] == "127.0.0.1"
        assert data["server"]["port"] == 8000

    def test_defaults_match_prd_schema(self):
        """PRD §6.7 完整 Schema。"""
        assert set(DEFAULTS.keys()) == {
            "schema_version", "general", "engine", "network", "server",
        }
        g = DEFAULTS["general"]
        assert g["default_language"] in VALID_LANGUAGES
        assert g["play"] in VALID_PLAY_MODES
        assert g["if_exists"] in VALID_IF_EXISTS


class TestConfigValidation:
    def test_invalid_language_rejected(self, isolated_env):
        cfg = Config()
        cfg.load()
        cfg.set("general.default_language", "fr")
        errors = cfg.validate()
        assert len(errors) == 1
        assert "default_language" in errors[0]

    def test_invalid_port_rejected(self, isolated_env):
        cfg = Config()
        cfg.load()
        cfg.set("server.port", 99999)
        errors = cfg.validate()
        assert len(errors) == 1


class TestConfigPersistence:
    def test_save_creates_file(self, isolated_env):
        cfg = Config()
        cfg.load()
        cfg.save()
        assert cfg.path.exists()

    def test_save_is_atomic_with_backup(self, isolated_env):
        cfg = Config()
        cfg.load()
        cfg.save()  # 第一次创建
        cfg.set("general.default_character", "mika")
        cfg.save()  # 第二次应产生 .bak
        bak = cfg.path.with_suffix(".toml.bak")
        assert bak.exists(), "原子写应该产生 .bak 文件"

    def test_schema_version_too_high_rejected(self, isolated_env, tmp_config_dir):
        path = tmp_config_dir / "config.toml"
        path.write_text("schema_version = 999\n")
        cfg = Config(path)
        with pytest.raises(Exception) as excinfo:
            cfg.load()
        # 应该是 EnvError
        from genie_term.errors import EnvError
        assert isinstance(excinfo.value, EnvError)

    def test_get_set_roundtrip(self, isolated_env):
        cfg = Config()
        cfg.load()
        cfg.set("general.default_character", "mika")
        cfg.set("server.port", 9000)
        assert cfg.get("general.default_character") == "mika"
        assert cfg.get("server.port") == 9000

    def test_reset(self, isolated_env):
        cfg = Config()
        cfg.load()
        cfg.set("general.default_character", "mika")
        cfg.reset()
        assert cfg.get("general.default_character") == "feibi"


class TestConfigCoercion:
    def test_set_bool_via_string(self, isolated_env):
        cfg = Config()
        cfg.load()
        # set() 直接设值（不做类型转换），config_set 命令才转换
        cfg.set("network.offline", True)
        assert cfg.get("network.offline") is True
