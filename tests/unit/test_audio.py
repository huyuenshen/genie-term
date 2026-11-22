"""tests/unit/test_audio.py —— 音频工具校验。"""

from __future__ import annotations

import pytest

from genie_term.core.audio import (
    MIN_PRODUCT_SIZE,
    PROMPT_ALLOWED_EXTS,
    check_prompt_audio,
    is_supported_prompt,
    probe_duration,
    verify_product,
    verify_product_or_raise,
)
from genie_term.errors import EngineError


class TestPromptAudioCheck:
    def test_allowed_extensions(self):
        assert is_supported_prompt("ref.wav")
        assert is_supported_prompt("ref.flac")
        assert is_supported_prompt("ref.ogg")
        assert is_supported_prompt("ref.aiff")
        assert is_supported_prompt("ref.aif")
        assert not is_supported_prompt("ref.mp3")
        assert not is_supported_prompt("ref.m4a")

    def test_allowed_exts_set(self):
        assert {".wav", ".flac", ".ogg", ".aiff", ".aif"} == PROMPT_ALLOWED_EXTS

    def test_missing_file(self, tmp_path):
        ok, problems = check_prompt_audio(tmp_path / "nonexist.wav")
        assert ok is False
        assert any("不存在" in p for p in problems)

    def test_wrong_extension(self, tmp_path):
        bad = tmp_path / "bad.mp3"
        bad.write_bytes(b"fake")
        ok, problems = check_prompt_audio(bad)
        assert ok is False


class TestProbeDuration:
    def test_wav_probe(self, fake_wav):
        dur = probe_duration(fake_wav)
        assert dur is not None
        assert dur > 0

    def test_nonexistent(self, tmp_path):
        dur = probe_duration(tmp_path / "nope.wav")
        assert dur is None


class TestProductVerification:
    def test_product_ok(self, fake_wav):
        # fake_wav 约 1700 bytes > 1KB
        ok, err = verify_product(fake_wav)
        assert ok is True
        assert err is None

    def test_product_too_small(self, tmp_path):
        tiny = tmp_path / "tiny.wav"
        tiny.write_bytes(b"x" * 100)  # 100 bytes < 1KB
        ok, err = verify_product(tiny)
        assert ok is False
        assert "太小" in err

    def test_product_missing(self, tmp_path):
        ok, err = verify_product(tmp_path / "ghost.wav")
        assert ok is False
        assert "不存在" in err

    def test_verify_product_or_raise_ok(self, fake_wav):
        verify_product_or_raise(fake_wav)  # should not raise

    def test_verify_product_or_raise_raises(self, tmp_path):
        tiny = tmp_path / "tiny.wav"
        tiny.write_bytes(b"x" * 100)
        with pytest.raises(EngineError):
            verify_product_or_raise(tiny)


class TestMinProductSize:
    def test_min_size_is_1kb(self):
        assert MIN_PRODUCT_SIZE == 1024
