"""tests/conftest.py —— pytest fixtures。"""

from __future__ import annotations

import pytest

# ========== 临时目录 fixture ==========

@pytest.fixture
def tmp_data_dir(tmp_path):
    """模拟 platformdirs 数据目录。"""
    data = tmp_path / "share" / "genie-term"
    data.mkdir(parents=True, exist_ok=True)
    return data


@pytest.fixture
def tmp_config_dir(tmp_path):
    """模拟平台配置目录。"""
    cfg = tmp_path / "config" / "genie-term"
    cfg.mkdir(parents=True, exist_ok=True)
    return cfg


@pytest.fixture
def isolated_env(monkeypatch, tmp_data_dir, tmp_config_dir):
    """隔离环境变量，用临时目录覆盖 platformdirs。"""
    monkeypatch.setenv("GENIE_TERM_DATA_DIR", str(tmp_data_dir))
    monkeypatch.setenv("GENIE_TERM_CONFIG_DIR", str(tmp_config_dir))
    # 确保 genie_tts 不会被意外 import
    monkeypatch.delenv("GENIE_DATA_DIR", raising=False)
    monkeypatch.delenv("HF_ENDPOINT", raising=False)
    return {
        "data_dir": tmp_data_dir,
        "config_dir": tmp_config_dir,
    }


# ========== 模拟角色模型目录 ==========

@pytest.fixture
def fake_model_dir(tmp_path):
    """创建一个包含必需文件的假模型目录。"""
    model = tmp_path / "fake_model"
    model.mkdir(parents=True)
    for f in [
        "t2s_encoder_fp32.bin",
        "t2s_encoder_fp32.onnx",
        "t2s_first_stage_decoder_fp32.onnx",
        "t2s_shared_fp16.bin",
        "t2s_stage_decoder_fp32.onnx",
        "vits_fp16.bin",
        "vits_fp32.onnx",
    ]:
        (model / f).write_bytes(b"fake" * 100)  # 400 bytes each
    return model


@pytest.fixture
def fake_model_dir_v2proplus(fake_model_dir):
    """v2ProPlus 格式：在 fake_model_dir 基础上加 2 个文件。"""
    (fake_model_dir / "prompt_encoder_fp16.bin").write_bytes(b"fake" * 100)
    (fake_model_dir / "prompt_encoder_fp32.onnx").write_bytes(b"fake" * 100)
    return fake_model_dir


@pytest.fixture
def fake_wav(tmp_path):
    """创建一个最小合法 WAV 文件（44 字节头 + 数据）。"""
    wav = tmp_path / "ref.wav"
    # 最小 WAV: 44 字节 RIFF 头 + 一些 data
    header = (
        b"RIFF"
        + (36).to_bytes(4, "little")  # file size - 8
        + b"WAVE"
        + b"fmt "
        + (16).to_bytes(4, "little")  # chunk size
        + (1).to_bytes(2, "little")   # PCM
        + (1).to_bytes(2, "little")   # channels
        + (16000).to_bytes(4, "little")  # sample rate
        + (16000 * 2).to_bytes(4, "little")  # byte rate
        + (2).to_bytes(2, "little")   # block align
        + (16).to_bytes(2, "little")  # bits per sample
        + b"data"
        + (1600).to_bytes(4, "little")  # data size
    )
    wav.write_bytes(header + b"\x00" * 1600)  # 总共 >1KB
    return wav


@pytest.fixture
def registry_with_character(isolated_env, fake_model_dir, fake_wav):
    """注册一个本地角色到空 registry。"""
    from genie_term.core.registry import load_registry

    reg = load_registry()
    reg.add("testchar", {
        "kind": "local",
        "language": "zh",
        "model_version": "v2",
        "model_dir": str(fake_model_dir),
        "prompt_wav": str(fake_wav),
        "prompt_text": "参考音频内容",
    })
    reg.save()
    return reg
