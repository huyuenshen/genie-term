"""core/audio.py —— 音频工具。

PRD §4.6 / §6.4 陷阱 5 对策：
  - 格式白名单（prompt 音频限 .wav/.flac/.ogg/.aiff/.aif）
  - prompt 时长检查：3–15s 最佳（<3s 警告，>20s 拒绝）
  - **合成产物校验**：存在且 >1KB，否则视为引擎失败（退出码 20）

红线：不在此文件 import genie_tts/onnxruntime。
"""

from __future__ import annotations

import struct
from pathlib import Path

# prompt 音频允许扩展名
PROMPT_ALLOWED_EXTS = {".wav", ".flac", ".ogg", ".aiff", ".aif"}

# 合成产物最低大小（字节），低于此值视为引擎失败
MIN_PRODUCT_SIZE = 1024  # 1KB


def is_supported_prompt(path: str | Path) -> bool:
    """检查文件扩展名是否在白名单内。"""
    ext = Path(path).suffix.lower()
    return ext in PROMPT_ALLOWED_EXTS


def probe_duration(path: str | Path) -> float | None:
    """探测音频时长（秒）。返回 None 表示无法探测。

    支持：WAV（RIFF 头）、FLAC（metadata block）、OGG。
    简单实现——只探测最常见的 WAV；复杂格式交给 soundfile（在 adapter 里）。
    """
    p = Path(path)
    if not p.exists():
        return None

    ext = p.suffix.lower()

    if ext == ".wav":
        return _probe_wav_duration(p)
    # 其他格式：尝试 soundfile（延迟 import）
    try:
        import soundfile as sf
        info = sf.info(str(p))
        return info.duration
    except Exception:
        return None


def _probe_wav_duration(path: Path) -> float | None:
    """手动解析 WAV RIFF 头获取时长。"""
    try:
        with open(path, "rb") as f:
            header = f.read(44)
        if len(header) < 44 or header[:4] != b"RIFF" or header[8:12] != b"WAVE":
            return None
        # fmt chunk
        channels = struct.unpack_from("<H", header, 22)[0]
        sample_rate = struct.unpack_from("<I", header, 24)[0]
        bits_per_sample = struct.unpack_from("<H", header, 34)[0]
        # data chunk size（找 'data' chunk）
        file_size = path.stat().st_size
        # RIFF header = 12 bytes, fmt chunk ≈ 24 bytes
        # 更可靠：从后往前找 data chunk
        with open(path, "rb") as f:
            # 扫一遍找 data chunk
            pos = 12
            while pos < file_size - 8:
                f.seek(pos)
                chunk_id = f.read(4)
                chunk_size = struct.unpack("<I", f.read(4))[0]
                if chunk_id == b"data":
                    data_size = chunk_size
                    break
                pos += 8 + chunk_size + (chunk_size % 2)
            else:
                return None

        if sample_rate == 0 or channels == 0 or bits_per_sample == 0:
            return None
        bytes_per_sample = bits_per_sample // 8
        total_samples = data_size / (channels * bytes_per_sample)
        return total_samples / sample_rate
    except Exception:
        return None


def check_prompt_audio(path: str | Path) -> tuple[bool, list[str]]:
    """检查参考音频是否合格。

    Returns:
        (是否通过, 问题列表)
    """
    problems: list[str] = []
    p = Path(path)

    if not p.exists():
        problems.append(f"文件不存在: {path}")
        return False, problems

    if not is_supported_prompt(p):
        problems.append(
            f"扩展名 {p.suffix} 不在白名单内 ({sorted(PROMPT_ALLOWED_EXTS)})"
        )
        return False, problems

    duration = probe_duration(p)
    if duration is None:
        problems.append("无法探测音频时长")
    elif duration < 3:
        problems.append(f"音频时长 {duration:.1f}s 太短（<3s，建议 3-15s）")
    elif duration > 20:
        problems.append(f"音频时长 {duration:.1f}s 超过上限 20s")

    return len(problems) == 0, problems


def verify_product(path: str | Path) -> tuple[bool, str | None]:
    """合成产物校验（陷阱 5 对策）。

    Returns:
        (是否合格, 错误消息或 None)
    """
    p = Path(path)

    if not p.exists():
        return False, f"合成产物不存在: {path}"

    size = p.stat().st_size
    if size < MIN_PRODUCT_SIZE:
        return False, f"合成产物太小 ({size} bytes < {MIN_PRODUCT_SIZE} bytes)，可能引擎失败"

    return True, None


def verify_product_or_raise(path: str | Path) -> None:
    """verify_product 失败时抛 EngineError。"""
    ok, err = verify_product(path)
    if not ok:
        from ..errors import EngineError
        raise EngineError(
            err or "合成产物校验失败",
            location=str(path),
            fix="运行 genie-term doctor 检查环境；检查日志 GENIE_TERM_DEBUG=1 genie-term say ...",
        )
