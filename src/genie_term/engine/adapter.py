"""engine/adapter.py —— 全项目唯一接触 genie_tts 的地方。

红线（project_rules.md §4）：
  - 只有此文件可以 import genie_tts；其余任何模块出现该 import 一律退回
  - 目的：上游 API 变更只改这一个文件

陷阱对策（PRD §6.4，adapter.py 注释逐条对应）：
  1. GENIE_DATA_DIR 在 Core/Resources.py 模块导入时固化 → bootstrap.ensure_env 在 import 前注入
  2. 数据目录不存在时导入期 input() 阻塞 → 导入前保证目录存在或自行报错
  3. download_genie_data() 污染 CWD → 禁用此 API，自写绝对目录 snapshot_download
  4. load_predefined_character() 下载到相对目录 → 临时 chdir 到 data_dir 调用
  5. tts() 无参考音频时 logger.error 后 return → 合成后校验产物 >1KB（由 audio.verify_product_or_raise 执行）
  6. download_roberta_data() 未导出 → 自实现 snapshot_download（在 download/genie_data.py）
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

# ========== M1: 依赖检查 + 版本查询 ==========

def check_onnxruntime() -> tuple[bool, str | None]:
    """检查 onnxruntime 是否可导入。"""
    try:
        import onnxruntime
        return True, onnxruntime.__version__
    except ImportError:
        return False, None


def check_genie_tts() -> tuple[bool, str | None]:
    """检查 genie_tts 是否可导入。

    陷阱 2 对策：上游在数据目录不存在时 import 期会 input() 阻塞。
    所以先 ensure_env，再检查目录是否存在，**不存在就不 import**。
    """
    from ..core.paths import resolve_data_dir
    from .bootstrap import ensure_env as _ensure

    _ensure()  # 确保 GENIE_DATA_DIR 已注入

    # 检查数据目录（不管 env 有没有设，都解析到最终路径）
    data_dir = resolve_data_dir()
    if not data_dir.exists():
        return False, None

    # 陷阱 2：GenieData 不完整时导入上游会 input() 挂起/EOFError
    from ..download.verify import verify_genie_data

    if verify_genie_data(data_dir / "GenieData"):
        return False, None

    try:
        import genie_tts
        return True, getattr(genie_tts, "__version__", "unknown")
    except ImportError:
        return False, None
    except Exception:
        return False, None


def get_engine_versions() -> dict[str, str | None]:
    """获取 genie_tts + onnxruntime 版本字典。"""
    _, genie_ver = check_genie_tts()
    _, ort_ver = check_onnxruntime()
    return {"genie_tts": genie_ver, "onnxruntime": ort_ver}


# ========== 环境注入 ==========

def ensure_env(
    data_dir: str | None = None,
    hf_endpoint: str | None = None,
    offline: bool = False,
) -> None:
    """在 import genie_tts 前注入 env（委托给 bootstrap）。"""
    from .bootstrap import ensure_env as _ensure
    _ensure(data_dir, hf_endpoint, offline)


# ========== 陷阱 4 对策：临时 chdir 到 data_dir ==========

@contextmanager
def _temporary_chdir(target: str | Path) -> Iterator[None]:
    """临时切换工作目录，异常也恢复。

    陷阱 4 对策：load_predefined_character() 内部用相对路径 CharacterModels/
    我们先 chdir 到 data_dir 再调用。
    """
    old_cwd = os.getcwd()
    os.chdir(str(target))
    try:
        yield
    finally:
        os.chdir(old_cwd)


# ========== 语言归一化 ==========

_LANG_MAP = {
    "zh": "Chinese",
    "en": "English",
    "jp": "Japanese",
}


def _to_genie_lang(lang: str) -> str:
    """genie_tts 接受 Chinese/English/Japanese，我们接受 zh/en/jp。"""
    return _LANG_MAP.get(lang.lower(), lang)


# ========== M2: 合成接口 ==========

def load_character(
    name: str,
    model_dir: str | Path,
    language: str = "zh",
) -> None:
    """加载本地模型角色。"""
    import genie_tts

    genie_tts.load_character(
        name,
        str(Path(model_dir).resolve()),
        _to_genie_lang(language),
    )


def load_predefined_character(
    name: str,
    data_dir: str | Path,
) -> None:
    """加载预置角色（陷阱 4 对策：临时 chdir）。"""
    import genie_tts

    with _temporary_chdir(data_dir):
        genie_tts.load_predefined_character(name)


def set_reference_audio(
    name: str,
    audio_path: str | Path,
    audio_text: str,
    language: str = "zh",
) -> None:
    """设置参考音频（.wav/.flac/.ogg/.aiff/.aif）。"""
    import genie_tts

    genie_tts.set_reference_audio(
        name,
        str(Path(audio_path).resolve()),
        audio_text,
        _to_genie_lang(language),
    )


def synth(
    name: str,
    text: str,
    output_path: str | Path,
    *,
    split_sentence: bool = True,
) -> Path:
    """执行合成 + 产物校验（陷阱 5 对策）。

    genie_tts.tts() 无返回值，我们必须自校验产物。
    """
    import genie_tts

    output = Path(output_path).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    # 陷阱 5 对策：tts 缺参考音频时只打日志 return，退出码仍 0
    # 所以必须：调用 → 校验产物
    genie_tts.tts(
        name,
        text,
        play=False,
        split_sentence=split_sentence,
        save_path=str(output),
    )

    # 产物校验（audio.py 的 verify_product_or_raise 会抛 EngineError → 退出码 20）
    from ..core.audio import verify_product_or_raise
    verify_product_or_raise(output)

    return output


def unload_character(name: str) -> None:
    """卸载角色（进程内单例，CLI 短生命周期可不用）。"""
    import genie_tts
    genie_tts.unload_character(name)


# ========== M3 预留接口 ==========

def convert(pth: str | Path, ckpt: str | Path, output_dir: str | Path) -> None:
    """模型转换（需要 torch）。"""
    import genie_tts
    genie_tts.convert_to_onnx(
        str(Path(pth).resolve()),
        str(Path(ckpt).resolve()),
        str(Path(output_dir).resolve()),
    )


def serve(host: str, port: int, workers: int = 1) -> None:
    """启动 HTTP 服务（上游 FastAPI，无鉴权）。"""
    import genie_tts
    genie_tts.start_server(host, port, workers)
