"""core/player.py —— 播放策略决策链。

PRD §6.11：
  播放是可选后处理：先试 sounddevice（macOS CoreAudio / Linux ALSA/Pulse），
  失败则外部播放器（macOS: afplay/ffplay；Linux: ffplay/paplay/aplay），
  全失败只警告，**不影响退出码**。

红线：
  - 不引入 ffmpeg 作为硬依赖
  - subprocess.run 用列表参数，禁止 shell=True
  - sounddevice 导入在 try/except 内，缺 PortAudio 只关播放不影响合成
"""

from __future__ import annotations

import platform
import shutil
import subprocess
from pathlib import Path

# 播放策略（PRD §6.11）
_MACOS_PLAYERS = ["afplay", "ffplay"]
_LINUX_PLAYERS = ["ffplay", "paplay", "aplay"]


def _try_sounddevice(audio_path: str | Path) -> bool:
    """尝试用 sounddevice 播放（缺 PortAudio 不影响合成）。"""
    try:
        import sounddevice as sd
        import soundfile as sf

        data, samplerate = sf.read(str(audio_path))
        sd.play(data, samplerate)
        sd.wait()  # 阻塞直到播放结束
        return True
    except Exception:
        return False


def _try_external_player(audio_path: str | Path) -> str | None:
    """尝试外部播放器，返回使用的播放器名（全失败返回 None）。

    红线：subprocess.run 用列表参数，禁止 shell=True。
    """
    system = platform.system().lower()
    if system == "darwin":
        players = _MACOS_PLAYERS
    elif system == "linux":
        players = _LINUX_PLAYERS
    else:
        return None

    audio_str = str(audio_path)
    for player in players:
        if not shutil.which(player):
            continue
        try:
            subprocess.run(
                [player, audio_str],
                check=False,
                capture_output=True,
                timeout=60,
            )
            return player
        except Exception:
            continue
    return None


def play(audio_path: str | Path, *, prefer_sounddevice: bool = True) -> bool:
    """执行播放策略链，返回是否成功。

    Args:
        audio_path: 音频文件路径
        prefer_sounddevice: 优先 sounddevice 还是直接外部播放器

    Returns:
        True = 至少一种播放器成功；False = 全部失败

    注意：播放失败**不影响合成退出码**，调用方决定是否警告用户。
    """
    path = Path(audio_path)
    if not path.exists():
        return False

    if prefer_sounddevice and _try_sounddevice(path):
        return True

    return bool(_try_external_player(path))


def get_available_player() -> str | None:
    """返回当前系统第一个可用的外部播放器名，不可用返回 None。"""
    system = platform.system().lower()
    if system == "darwin":
        players = _MACOS_PLAYERS
    elif system == "linux":
        players = _LINUX_PLAYERS
    else:
        return None

    for p in players:
        if shutil.which(p):
            return p
    return None
