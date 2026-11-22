"""download/presets.py —— 预置角色元数据与自动注册。

PRD §4.6/§4.7/§6.4 陷阱 4：
  预置角色（feibi/mika/thirtyseven）由 download character 注册，
  自带 prompt_wav.json 与参考音频，不需要用户提供。

registry 中的 model_dir 必须是 `<角色目录>/tts_models`（模型文件所在），
而不是角色根目录——否则必需文件校验必然失败。
"""

from __future__ import annotations

import json
from pathlib import Path

PRESET_CHARACTERS = {"feibi", "mika", "thirtyseven"}

CHAR_ALIAS = {
    "37": "thirtyseven",
    "thirtyseven": "thirtyseven",
    "feibi": "feibi",
    "菲比": "feibi",
    "mika": "mika",
    "未花": "mika",
}

PRESET_LANGUAGES = {"feibi": "zh", "mika": "jp", "thirtyseven": "en"}


def normalize_name(name: str) -> str:
    """把别名/大小写归一化为标准预置角色名。"""
    lowered = name.strip().lower()
    return CHAR_ALIAS.get(lowered, lowered)


def resolve_model_dir(char_dir: str | Path) -> Path:
    """返回模型文件所在目录：有 tts_models 子目录则用它，否则用角色根目录。"""
    root = Path(char_dir)
    tts_models = root / "tts_models"
    return tts_models if tts_models.is_dir() else root


def _find_prompt_assets(char_dir: Path) -> tuple[Path | None, str]:
    """从 prompt_wav.json 或目录中的 wav 推断参考音频与文本。"""
    prompt_json = None
    for candidate in [
        char_dir / "prompt_wav.json",
        char_dir / "prompt_wav" / "prompt_wav.json",
        char_dir / "tts_models" / "prompt_wav.json",
    ]:
        if candidate.exists():
            prompt_json = candidate
            break

    if prompt_json is not None:
        try:
            with open(prompt_json, encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict) and "wav" in data:
                wav_name = str(data.get("wav", ""))
                text = str(data.get("text", ""))
                path = Path(wav_name)
                if not path.is_absolute():
                    path = prompt_json.parent / wav_name
                if path.exists():
                    return path, text
            elif isinstance(data, dict) and data:
                first = next(iter(data.values()))
                if isinstance(first, dict):
                    wav_name = str(first.get("wav", ""))
                    text = str(first.get("text", ""))
                    for base in (prompt_json.parent, char_dir / "prompt_wav"):
                        path = Path(wav_name)
                        if not path.is_absolute():
                            path = base / wav_name
                        if path.exists():
                            return path, text
        except (json.JSONDecodeError, OSError, TypeError):
            pass

    for pattern in ("*.wav", "prompt_wav/*.wav", "tts_models/*.wav"):
        wavs = sorted(char_dir.glob(pattern))
        if wavs:
            return wavs[0], ""
    return None, ""


def infer_model_version(model_dir: Path) -> str:
    return "v2ProPlus" if (model_dir / "prompt_encoder_fp32.onnx").exists() else "v2"


def build_character_record(name: str, char_dir: str | Path) -> dict | None:
    """构造可直接写入 registry 的预置角色记录；缺参考音频时返回 None。"""
    root = Path(char_dir).resolve()
    prompt_wav, prompt_text = _find_prompt_assets(root)
    if prompt_wav is None:
        return None
    model_dir = resolve_model_dir(root)
    return {
        "kind": "preset",
        "language": PRESET_LANGUAGES.get(name, "zh"),
        "model_version": infer_model_version(model_dir),
        "model_dir": str(model_dir),
        "prompt_wav": str(prompt_wav),
        "prompt_text": prompt_text or f"预置角色 {name} 的参考音频",
    }


def auto_register_preset(name: str, char_dir: str | Path) -> bool:
    """下载后自动注册预置角色；成功返回 True。"""
    from ..context import info
    from ..core.registry import load_registry

    record = build_character_record(name, char_dir)
    if record is None:
        info("⚠ 未找到 prompt_wav.json 或 .wav，跳过自动注册")
        info(
            f"  手动注册: genie-term characters add {name} "
            f"--model-dir {resolve_model_dir(char_dir)} --lang "
            f"{PRESET_LANGUAGES.get(name, 'zh')} --prompt-wav ... --prompt-text ..."
        )
        return False

    try:
        reg = load_registry()
        reg.add(name, record, force=True)
        reg.save()
    except Exception as exc:  # noqa: BLE001 - 自动注册失败不应中断下载
        info(f"⚠ 自动注册失败: {exc}")
        return False

    info(
        f"✅ 角色 '{name}' 自动注册成功 "
        f"({record['model_version']}, {record['language']})"
    )
    return True
