"""tests/unit/test_registry.py —— 角色注册表读写/校验/自动推断。"""

from __future__ import annotations

import pytest

from genie_term.core.registry import (
    BASELINE_REQUIRED_FILES,
    CURRENT_SCHEMA_VERSION,
    V2PROPLUS_REQUIRED_FILES,
    load_registry,
)
from genie_term.errors import UsageError


class TestRegistryBasics:
    def test_empty_registry(self, isolated_env):
        reg = load_registry()
        assert reg.list_characters() == {}
        assert reg.exists("anything") is False

    def test_add_and_get(self, isolated_env, fake_model_dir, fake_wav):
        reg = load_registry()
        reg.add("testchar", {
            "kind": "local",
            "language": "zh",
            "model_version": "v2",
            "model_dir": str(fake_model_dir),
            "prompt_wav": str(fake_wav),
            "prompt_text": "参考音频",
        })
        assert reg.exists("testchar")
        char = reg.get("testchar")
        assert char["language"] == "zh"
        assert char["kind"] == "local"

    def test_add_duplicate_without_force_rejected(self, isolated_env, fake_model_dir, fake_wav):
        reg = load_registry()
        reg.add("dup", {
            "kind": "local", "language": "zh", "model_version": "v2",
            "model_dir": str(fake_model_dir), "prompt_wav": str(fake_wav),
            "prompt_text": "ref",
        })
        with pytest.raises(UsageError):
            reg.add("dup", {
                "kind": "local", "language": "zh", "model_version": "v2",
                "model_dir": str(fake_model_dir), "prompt_wav": str(fake_wav),
                "prompt_text": "ref",
            })

    def test_remove(self, registry_with_character):
        reg = registry_with_character
        data = reg.remove("testchar")
        assert data is not None
        assert reg.exists("testchar") is False


class TestModelVersionInference:
    def test_infer_v2_when_no_prompt_encoder(self, isolated_env, fake_model_dir):
        reg = load_registry()
        inferred = reg._infer_model_version(str(fake_model_dir))
        assert inferred == "v2"

    def test_infer_v2proplus_when_prompt_encoder_exists(self, isolated_env, fake_model_dir_v2proplus):
        reg = load_registry()
        inferred = reg._infer_model_version(str(fake_model_dir_v2proplus))
        assert inferred == "v2ProPlus"


class TestRegistrySave:
    def test_save_creates_file(self, isolated_env, fake_model_dir, fake_wav):
        reg = load_registry()
        reg.add("save_test", {
            "kind": "local", "language": "zh", "model_version": "v2",
            "model_dir": str(fake_model_dir), "prompt_wav": str(fake_wav),
            "prompt_text": "ref",
        })
        reg.save()
        assert reg.path.exists()

    def test_save_and_reload(self, isolated_env, fake_model_dir, fake_wav):
        reg1 = load_registry()
        reg1.add("reload_test", {
            "kind": "local", "language": "en", "model_version": "v2",
            "model_dir": str(fake_model_dir), "prompt_wav": str(fake_wav),
            "prompt_text": "hello",
        })
        reg1.save()

        reg2 = load_registry()
        char = reg2.get("reload_test")
        assert char is not None
        assert char["language"] == "en"


class TestRequiredFiles:
    def test_baseline_7_files(self):
        assert len(BASELINE_REQUIRED_FILES) == 7

    def test_v2proplus_adds_2(self):
        assert len(V2PROPLUS_REQUIRED_FILES) == 2

    def test_all_v2proplus_files(self):
        all_files = BASELINE_REQUIRED_FILES + V2PROPLUS_REQUIRED_FILES
        assert len(all_files) == 9
