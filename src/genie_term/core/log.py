"""core/log.py —— 日志落盘（PRD §7）。

规则：
  - 写 <state_dir>/logs/genie-term.log，按天轮转保留 7 天
  - **不记录合成文本内容**，只记录长度与 SHA-256 前 8 位
  - 默认无遥测、无崩溃上报
"""

from __future__ import annotations

import hashlib
import logging
from logging.handlers import TimedRotatingFileHandler

_LOGGER_NAME = "genie_term"
_configured = False


def text_fingerprint(text: str) -> str:
    """安全的文本指纹：长度 + 哈希前 8 位，绝不写入原文。"""
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:8]
    return f"len={len(text)},sha8={digest}"


def get_logger() -> logging.Logger:
    """返回已配置文件处理器（按天轮转 7 天）的 logger。失败时降级为 NullHandler。"""
    global _configured
    logger = logging.getLogger(_LOGGER_NAME)
    if _configured:
        return logger
    logger.setLevel(logging.INFO)
    logger.propagate = False
    try:
        from .paths import log_file

        path = log_file()
        path.parent.mkdir(parents=True, exist_ok=True)
        handler: logging.Handler = TimedRotatingFileHandler(
            str(path), when="midnight", backupCount=7, encoding="utf-8"
        )
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    except Exception:
        handler = logging.NullHandler()
    logger.addHandler(handler)
    _configured = True
    return logger


def log_event(event: str, **fields: object) -> None:
    """记录结构化事件（字段为简单标量）。"""
    detail = " ".join(f"{k}={v}" for k, v in fields.items())
    get_logger().info("%s %s", event, detail)
