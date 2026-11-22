"""tests/unit/test_say.py —— say 关键行为（PRD §4.5）。"""

from __future__ import annotations

from pathlib import Path

import pytest

from genie_term.commands.say import (
    _generate_output_path,
    _resolve_if_exists,
    _should_play,
    run_say,
)
from genie_term.errors import UsageError


class TestPlayDecision:
    def test_play_flag_always_plays(self):
        assert _should_play(True) is True

    def test_no_play_never_plays(self):
        assert _should_play(False) is False

    def test_auto_non_tty_is_off(self, monkeypatch):
        monkeypatch.setattr("sys.stdin.isatty", lambda: False)
        assert _should_play("auto") is False

    def test_explicit_modes(self):
        assert _should_play("always") is True
        assert _should_play("never") is False


class TestIfExists:
    def test_explicit_file_fail(self, tmp_path):
        target = tmp_path / "a.wav"
        target.write_bytes(b"x")
        with pytest.raises(UsageError):
            _resolve_if_exists(target, "fail")

    def test_explicit_file_skip(self, tmp_path):
        target = tmp_path / "a.wav"
        target.write_bytes(b"x")
        assert _resolve_if_exists(target, "skip") is None

    def test_explicit_file_timestamp(self, tmp_path):
        target = tmp_path / "a.wav"
        target.write_bytes(b"x")
        resolved = _resolve_if_exists(target, "timestamp")
        assert resolved is not None
        assert resolved != target
        assert resolved.suffix == ".wav"

    def test_directory_naming(self, tmp_path):
        path = _generate_output_path(tmp_path, "feibi")
        assert path.parent == tmp_path
        assert path.name.startswith("genie_feibi_")
        assert path.suffix == ".wav"


class TestSayFlow:
    @pytest.fixture
    def ready_data(self, isolated_env):
        genie_data = isolated_env["data_dir"] / "GenieData"
        for rel in (
            "chinese-hubert-base",
            "G2P/ChineseG2P",
            "G2P/EnglishG2P",
            "v2/Models",
            "v2ProPlus/Models",
        ):
            (genie_data / rel).mkdir(parents=True, exist_ok=True)
        (genie_data / "speaker_encoder.onnx").write_bytes(b"x")
        return genie_data

    @pytest.fixture
    def stub_adapter(self, monkeypatch):
        from genie_term.engine import adapter

        calls: list[tuple] = []

        def fake_load(name, model_dir, language="zh"):
            calls.append(("load", name, str(model_dir), language))

        def fake_set_ref(name, wav, text, language="zh"):
            calls.append(("set_ref", name))

        def fake_synth(name, text, output, *, split_sentence=True):
            calls.append(("tts", name, text))
            out = Path(output)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(b"RIFF" + b"x" * 4096)
            return out

        monkeypatch.setattr(adapter, "load_character", fake_load)
        monkeypatch.setattr(adapter, "set_reference_audio", fake_set_ref)
        monkeypatch.setattr(adapter, "synth", fake_synth)
        return calls

    def test_json_result_fields(
        self, isolated_env, ready_data, registry_with_character, stub_adapter, tmp_path
    ):
        result = run_say(
            "你好",
            character="testchar",
            output=str(tmp_path / "out.wav"),
            play=False,
        )
        assert result["ok"] is True
        assert result["character"] == "testchar"
        assert Path(result["output"]).is_absolute()
        assert "elapsed_ms" in result
        assert "duration_s" in result
        assert stub_adapter[0][0] == "load"
        assert stub_adapter[1][0] == "set_ref"
        assert stub_adapter[2][0] == "tts"

    def test_positional_text_wins_over_file(
        self, isolated_env, ready_data, registry_with_character, stub_adapter, tmp_path
    ):
        source = tmp_path / "input.txt"
        source.write_text("文件内容", encoding="utf-8")
        run_say(
            "参数内容",
            character="testchar",
            input_file=str(source),
            output=str(tmp_path / "out.wav"),
            play=False,
        )
        assert stub_adapter[2][2] == "参数内容"
