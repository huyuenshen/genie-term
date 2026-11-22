"""tests/integration/test_cli.py —— CLI 端到端行为测试。

红线：测试不得真实联网、不得真实加载模型。
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from genie_term.cli import app
from genie_term.errors import (
    EXIT_OK,
    MissingTorchError,
    UsageError,
)


runner = CliRunner()


# ========== version ==========

class TestVersionCommand:
    def test_version_plain(self):
        result = runner.invoke(app, ["version"])
        assert result.exit_code == EXIT_OK
        assert "genie-term" in result.stdout

    def test_version_json(self):
        result = runner.invoke(app, ["version", "--json"])
        assert result.exit_code == EXIT_OK
        data = json.loads(result.stdout)
        assert "genie_term" in data
        assert "python" in data


# ========== characters ==========

class TestCharactersCommand:
    def test_list_empty(self, isolated_env):
        result = runner.invoke(app, ["characters", "list"])
        assert result.exit_code == EXIT_OK
        assert "无已注册角色" in result.stdout

    def test_list_json_empty(self, isolated_env):
        result = runner.invoke(app, ["characters", "list", "--json"])
        assert result.exit_code == EXIT_OK
        assert json.loads(result.stdout) == {}


# ========== config ==========

class TestConfigCommand:
    def test_config_path(self, isolated_env):
        result = runner.invoke(app, ["config", "path"])
        assert result.exit_code == EXIT_OK
        assert "genie-term" in result.stdout

    def test_config_show(self, isolated_env):
        result = runner.invoke(app, ["config", "show"])
        assert result.exit_code == EXIT_OK
        assert "schema_version" in result.stdout

    def test_config_get(self, isolated_env):
        result = runner.invoke(app, ["config", "get", "general.default_character"])
        assert result.exit_code == EXIT_OK
        assert result.stdout.strip() == "feibi"

    def test_config_set(self, isolated_env):
        result = runner.invoke(app, ["config", "set", "server.port", "9000"])
        assert result.exit_code == EXIT_OK
        result = runner.invoke(app, ["config", "get", "server.port"])
        assert result.exit_code == EXIT_OK
        assert result.stdout.strip() == "9000"

    def test_config_reset_no_yes_non_tty(self, isolated_env):
        """非 TTY 下 reset 无 --yes 应抛 UsageError。"""
        with pytest.raises(UsageError) as excinfo:
            runner.invoke(app, ["config", "reset"], catch_exceptions=False)
        assert "--yes" in str(excinfo.value)


# ========== say ==========

class TestSayCommand:
    def test_say_no_text(self, isolated_env):
        with pytest.raises(UsageError) as excinfo:
            runner.invoke(app, ["say"], catch_exceptions=False)
        assert "没有合成文本" in str(excinfo.value)

    def test_say_unknown_character(self, isolated_env):
        with pytest.raises(UsageError) as excinfo:
            runner.invoke(app, ["say", "-c", "nonexistent", "你好"], catch_exceptions=False)
        assert "不存在" in str(excinfo.value)


# ========== download ==========

class TestDownloadCommand:
    def test_download_unknown_character(self, isolated_env):
        with pytest.raises(UsageError):
            runner.invoke(app, ["download", "character", "notachar"], catch_exceptions=False)

    def test_download_roberta_no_yes(self, isolated_env):
        with pytest.raises(UsageError) as excinfo:
            runner.invoke(app, ["download", "roberta"], catch_exceptions=False)
        assert "--yes" in str(excinfo.value)


# ========== doctor ==========

class TestDoctorCommand:
    def test_doctor_runs(self, isolated_env):
        result = runner.invoke(app, ["doctor", "--no-network"])
        assert result.exit_code != 0

    def test_doctor_json(self, isolated_env):
        result = runner.invoke(app, ["doctor", "--json", "--no-network"])
        assert result.exit_code != 0
        data = json.loads(result.stdout)
        assert "checks" in data
        assert "summary" in data
        assert "exit_code" in data


# ========== convert ==========

class TestConvertCommand:
    def test_convert_missing_torch(self, isolated_env, tmp_path):
        """缺 torch → MissingTorchError（码 21）。"""
        fake_pth = tmp_path / "a.pth"
        fake_ckpt = tmp_path / "a.ckpt"
        fake_pth.write_bytes(b"x")
        fake_ckpt.write_bytes(b"x")

        with pytest.raises(MissingTorchError) as excinfo:
            runner.invoke(app, [
                "convert",
                "--pth", str(fake_pth),
                "--ckpt", str(fake_ckpt),
                "--name", "test",
                "--no-register",
            ], catch_exceptions=False)
        assert excinfo.value.code == 21


# ========== serve ==========

class TestServeCommand:
    def test_serve_public_without_allow(self, isolated_env):
        with pytest.raises(UsageError) as excinfo:
            runner.invoke(app, ["serve", "--host", "0.0.0.0"], catch_exceptions=False)
        assert "--allow-public" in str(excinfo.value)

    def test_serve_too_many_workers(self, isolated_env):
        with pytest.raises(UsageError) as excinfo:
            runner.invoke(app, ["serve", "--workers", "5"], catch_exceptions=False)
        assert "workers" in str(excinfo.value)


# ========== completion ==========

class TestCompletionCommand:
    def test_bash(self, isolated_env):
        result = runner.invoke(app, ["completion", "bash"])
        assert result.exit_code == EXIT_OK
        assert "complete" in result.stdout

    def test_zsh(self, isolated_env):
        result = runner.invoke(app, ["completion", "zsh"])
        assert result.exit_code == EXIT_OK
        assert "compdef" in result.stdout

    def test_fish(self, isolated_env):
        result = runner.invoke(app, ["completion", "fish"])
        assert result.exit_code == EXIT_OK
        assert "completions" in result.stdout

    def test_invalid_shell(self, isolated_env):
        """无效 shell → 退出码 2（typer.Exit）。"""
        result = runner.invoke(app, ["completion", "invalid"])
        assert result.exit_code == 2


# ========== engine/adapter 红线测试 ==========

class TestAdapterImportRule:
    """确保除了 adapter.py 外没有其他地方 import genie_tts。"""

    def test_no_genie_tts_import_elsewhere(self):
        import ast
        import os

        src_dir = os.path.join(os.path.dirname(__file__), "..", "..", "src", "genie_term")

        violations = []
        for root, dirs, files in os.walk(src_dir):
            dirs[:] = [d for d in dirs if d != "__pycache__"]
            for f in files:
                if not f.endswith(".py"):
                    continue
                fp = os.path.join(root, f)
                rel = os.path.relpath(fp, src_dir)
                if rel == "engine/adapter.py":
                    continue
                try:
                    tree = ast.parse(open(fp).read())
                except SyntaxError:
                    continue
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            if alias.name == "genie_tts":
                                violations.append(f"{rel}: import genie_tts")
                    elif isinstance(node, ast.ImportFrom):
                        if node.module == "genie_tts":
                            violations.append(f"{rel}: from genie_tts import ...")

        assert violations == [], f"红线违规（adapter.py 之外 import genie_tts）: {violations}"
