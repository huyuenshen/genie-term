"""errors.py —— 统一异常类型 + 退出码映射。

退出码（PRD §4.1，写死不可漂移）：
  0   成功
  2   用法/参数错误/需确认但非交互
  10  环境缺失（数据/模型/系统库/Python版本）
  11  网络失败（HF/镜像不可达、下载中断）
  12  播放失败（仅影响 --play，合成成功仍返回 0）
  20  引擎内部错误
  21  缺少 torch（仅 convert）
  130 用户中断（Ctrl-C）

红线：禁止裸 traceback（GENIE_TERM_DEBUG=1 才打印堆栈）；
每条错误必须有「是什么/在哪/下一条命令」。
"""

from __future__ import annotations

import os
import traceback

# 退出码常量
EXIT_OK = 0
EXIT_USAGE = 2          # 用法·参数·需确认但非交互
EXIT_ENV = 10           # 环境缺失
EXIT_NETWORK = 11       # 网络失败
EXIT_PLAYBACK = 12      # 播放失败
EXIT_ENGINE = 20        # 引擎内部错误
EXIT_NO_TORCH = 21      # 缺少 torch
EXIT_INTERRUPT = 130    # 用户中断


class GenieTermError(Exception):
    """genie-term 统一异常基类。

    Attributes:
        code: 退出码
        message: 人类可读错误描述
        location: 错误发生位置（文件/模块/状态）
        fix: 一条可复制的下一步命令（可空）
    """

    code: int = EXIT_ENGINE
    message: str = ""
    location: str = ""
    fix: str | None = None

    def __init__(
        self,
        message: str,
        *,
        location: str = "",
        fix: str | None = None,
        code: int | None = None,
    ):
        self.message = message
        self.location = location
        self.fix = fix
        if code is not None:
            self.code = code
        super().__init__(self._format())

    def _format(self) -> str:
        """格式化为 PRD §7 要求的人类可读错误。"""
        lines = [f"[错误] {self.message}"]
        if self.location:
            lines.append(f"  位置: {self.location}")
        if self.fix:
            lines.append(f"  下一步: {self.fix}")
        if os.environ.get("GENIE_TERM_DEBUG") == "1":
            lines.append(f"  详细: {traceback.format_exc().strip()}")
        return "\n".join(lines)


# ========== 具体异常子类（按退出码分组） ==========

class UsageError(GenieTermError):
    """退出码 2：用法/参数错误/需确认但非交互。"""
    code = EXIT_USAGE


class EnvError(GenieTermError):
    """退出码 10：环境缺失。"""
    code = EXIT_ENV


class NetworkError(GenieTermError):
    """退出码 11：网络失败。"""
    code = EXIT_NETWORK


class PlaybackError(GenieTermError):
    """退出码 12：播放失败（不影响合成）。"""
    code = EXIT_PLAYBACK


class EngineError(GenieTermError):
    """退出码 20：引擎内部错误（产物校验失败等）。"""
    code = EXIT_ENGINE


class MissingTorchError(GenieTermError):
    """退出码 21：缺少 torch（仅 convert 命令）。"""
    code = EXIT_NO_TORCH


# ========== 异常 → 退出码映射表 ==========
# cli.py 在 main() 里用这个表做最终映射
_EXCEPTION_CODE_MAP: dict[type[BaseException], int] = {
    GenieTermError: GenieTermError.code,
    UsageError: UsageError.code,
    EnvError: EnvError.code,
    NetworkError: NetworkError.code,
    PlaybackError: PlaybackError.code,
    EngineError: EngineError.code,
    MissingTorchError: MissingTorchError.code,
    KeyboardInterrupt: EXIT_INTERRUPT,
}


def exception_to_exit_code(exc: BaseException) -> int:
    """把任意异常映射为退出码。

    GenieTermError 子类直接取其 code 属性；
    未知异常默认 20（引擎内部错误）并在 debug 模式打印堆栈。
    """
    if isinstance(exc, GenieTermError):
        return exc.code
    code = _EXCEPTION_CODE_MAP.get(type(exc), EXIT_ENGINE)
    if code == EXIT_ENGINE and os.environ.get("GENIE_TERM_DEBUG") == "1":
        traceback.print_exception(exc)
    return code
