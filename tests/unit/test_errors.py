"""tests/unit/test_errors.py —— 退出码契约测试。

PRD §4.1 退出码写死不可漂移。
"""

from __future__ import annotations

import pytest

from genie_term.errors import (
    EXIT_ENGINE,
    EXIT_ENV,
    EXIT_INTERRUPT,
    EXIT_NETWORK,
    EXIT_NO_TORCH,
    EXIT_OK,
    EXIT_PLAYBACK,
    EXIT_USAGE,
    EnvError,
    EngineError,
    GenieTermError,
    MissingTorchError,
    NetworkError,
    PlaybackError,
    UsageError,
    exception_to_exit_code,
)


class TestExitCodes:
    """PRD §4.1 退出码。"""

    def test_constants_match_prd(self):
        assert EXIT_OK == 0
        assert EXIT_USAGE == 2
        assert EXIT_ENV == 10
        assert EXIT_NETWORK == 11
        assert EXIT_PLAYBACK == 12
        assert EXIT_ENGINE == 20
        assert EXIT_NO_TORCH == 21
        assert EXIT_INTERRUPT == 130

    def test_usage_error_code(self):
        err = UsageError("test")
        assert err.code == EXIT_USAGE

    def test_env_error_code(self):
        err = EnvError("test")
        assert err.code == EXIT_ENV

    def test_network_error_code(self):
        err = NetworkError("test")
        assert err.code == EXIT_NETWORK

    def test_playback_error_code(self):
        err = PlaybackError("test")
        assert err.code == EXIT_PLAYBACK

    def test_engine_error_code(self):
        err = EngineError("test")
        assert err.code == EXIT_ENGINE

    def test_missing_torch_error_code(self):
        err = MissingTorchError("test")
        assert err.code == EXIT_NO_TORCH

    def test_exception_to_exit_code_genie_term_error(self):
        err = UsageError("test")
        assert exception_to_exit_code(err) == EXIT_USAGE

    def test_exception_to_exit_code_unknown(self):
        assert exception_to_exit_code(ValueError("test")) == EXIT_ENGINE

    def test_exception_to_exit_code_keyboard_interrupt(self):
        assert exception_to_exit_code(KeyboardInterrupt()) == EXIT_INTERRUPT

    def test_error_format(self):
        err = UsageError(
            "输入为空",
            location="genie-term say",
            fix="genie-term say '你好'",
        )
        formatted = str(err)
        assert "[错误] 输入为空" in formatted
        assert "位置: genie-term say" in formatted
        assert "下一步: genie-term say '你好'" in formatted
