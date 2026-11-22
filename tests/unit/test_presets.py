"""tests/unit/test_presets.py —— 预置角色自动注册（PRD §4.6/§4.7）。"""

from __future__ import annotations

from genie_term.download.presets import (
    build_character_record,
    normalize_name,
    resolve_model_dir,
)


def _make_char(tmp_path, version="v2ProPlus", with_wav=True):
    char_dir = tmp_path / "CharacterModels" / version / "feibi"
    models = char_dir / "tts_models"
    models.mkdir(parents=True)
    for name in ("t2s_encoder_fp32.onnx", "vits_fp32.onnx"):
        (models / name).write_bytes(b"x")
    if version == "v2ProPlus":
        (models / "prompt_encoder_fp32.onnx").write_bytes(b"x")
    if with_wav:
        wav = char_dir / "prompt_wav" / "zh_test.wav"
        wav.parent.mkdir(parents=True)
        wav.write_bytes(b"x" * 64)
    return char_dir


class TestPresets:
    def test_alias_normalization(self):
        assert normalize_name("37") == "thirtyseven"
        assert normalize_name("菲比") == "feibi"
        assert normalize_name("MIKA") == "mika"

    def test_model_dir_prefers_tts_models(self, tmp_path):
        char_dir = _make_char(tmp_path)
        assert resolve_model_dir(char_dir) == char_dir / "tts_models"

    def test_record_uses_tts_models(self, tmp_path):
        char_dir = _make_char(tmp_path)
        record = build_character_record("feibi", char_dir)
        assert record is not None
        assert record["kind"] == "preset"
        assert record["model_dir"].endswith("tts_models")
        assert record["model_version"] == "v2ProPlus"
        assert record["prompt_wav"].endswith(".wav")

    def test_missing_prompt_returns_none(self, tmp_path):
        char_dir = _make_char(tmp_path, with_wav=False)
        assert build_character_record("feibi", char_dir) is None
