"""commands/download.py —— genie-data / character / roberta 下载命令组。

PRD §4.7：
  genie-term download genie-data [--mirror URL] [--yes]    # 391MB
  genie-term download character NAME [--yes]               # 预置角色约 230MB + 自动注册
  genie-term download roberta [--yes]                     # 可选，自实现（上游未导出）

红线：
  - 禁止调用上游 download_genie_data()（它 local_dir="." 污染 CWD）
  - 用 huggingface_hub.snapshot_download 指定绝对目录，pattern 用 GenieData/**
  - HF_ENDPOINT 必须在 import huggingface_hub 之前设
  - 失败统一退出码 11 + hf-mirror 提示
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import typer

from genie_term.errors import NetworkError, UsageError

app = typer.Typer(
    name="download",
    help="下载资源 (genie-data|character|roberta)",
    add_completion=False,
    invoke_without_command=True,
)


# PRD §6.4 陷阱 3：预置角色名称映射
_PRESET_CHARACTERS = {"feibi", "mika", "thirtyseven", "37"}
_CHAR_ALIAS = {
    "37": "thirtyseven",
    "菲比": "feibi",
    "未花": "mika",
    "feibi": "feibi",
    "mika": "mika",
    "thirtyseven": "thirtyseven",
}


# ========== genie-data ==========

@app.command("genie-data")
def download_genie_data_cmd(
    mirror: str | None = typer.Option(None, "--mirror", help="HF mirror endpoint"),
    yes: bool = typer.Option(False, "--yes", help="跳过确认"),
    force: bool = typer.Option(False, "--force", help="已存在时重下"),
) -> None:
    """下载 GenieData（约 391MB，必需资源）。"""
    from genie_term.core.config import effective_data_dir
    from genie_term.download.genie_data import download_genie_data

    data_dir = effective_data_dir()
    typer.echo(f"下载 GenieData → {data_dir}")

    if not yes and not sys.stdin.isatty():
        raise UsageError(
            "非交互式环境下载需要 --yes",
            fix="genie-term download genie-data --yes",
        )
    if not yes and sys.stdin.isatty():
        confirm = typer.confirm("确认下载约 391MB？")
        if not confirm:
            raise typer.Exit(code=0)

    try:
        result = download_genie_data(data_dir, mirror=mirror, force=force)
        typer.echo(f"✅ GenieData 就绪: {result}")
    except NetworkError:
        raise


# ========== character ==========

@app.command("character")
def download_character_cmd(
    name: str = typer.Argument(..., help="角色名 (feibi|mika|thirtyseven)"),
    mirror: str | None = typer.Option(None, "--mirror", help="HF mirror endpoint"),
    yes: bool = typer.Option(False, "--yes", help="跳过确认"),
) -> None:
    """下载预置角色并自动注册（约 230MB）。"""
    from genie_term.core.config import effective_data_dir
    from genie_term.download.genie_data import download_character as _dl_char

    # 别名归一化
    normalized = _CHAR_ALIAS.get(name.lower(), name.lower())
    if normalized not in _PRESET_CHARACTERS:
        raise UsageError(
            f"未知预置角色 '{name}'",
            fix=f"可用预置角色: {', '.join(sorted(_PRESET_CHARACTERS - {'37'}))}",
        )

    data_dir = effective_data_dir()
    typer.echo(f"下载角色 '{normalized}' → {data_dir}")

    if not yes and not sys.stdin.isatty():
        raise UsageError(
            "非交互式环境下载需要 --yes",
            fix=f"genie-term download character {normalized} --yes",
        )
    if not yes and sys.stdin.isatty():
        confirm = typer.confirm("确认下载约 230MB？")
        if not confirm:
            raise typer.Exit(code=0)

    try:
        char_dir = _dl_char(data_dir, normalized, mirror=mirror)
        typer.echo(f"✅ 模型下载完成: {char_dir}")
    except NetworkError:
        raise

    # ---- 自动注册（PRD §C.6：预置角色自带 prompt_wav.json） ----
    _auto_register_preset(normalized, char_dir, data_dir)


def _auto_register_preset(char_name: str, char_dir: Path, data_dir: Path) -> None:
    """下载后自动注册预置角色。

    从角色目录查找 prompt_wav.json（HF 仓库提供）。
    """
    from genie_term.core.registry import load_registry

    reg = load_registry()

    # prompt_wav.json 可能在角色目录下或 prompt_wav/ 子目录
    prompt_json = None
    for candidate in [
        char_dir / "prompt_wav.json",
        char_dir / "prompt_wav" / "prompt_wav.json",
    ]:
        if candidate.exists():
            prompt_json = candidate
            break

    # 同时找 wav 文件
    prompt_wav_path = None
    prompt_text = ""

    if prompt_json:
        try:
            with open(prompt_json, encoding="utf-8") as f:
                pw_data = json.load(f)
            # prompt_wav.json 格式推断：{"wav": "path.wav", "text": "..."} 或 {"zh": {"wav":..., "text":...}}
            if "wav" in pw_data:
                wav_path = pw_data["wav"]
                prompt_text = pw_data.get("text", "")
                p = Path(wav_path)
                if not p.is_absolute():
                    p = char_dir / wav_path
                if p.exists():
                    prompt_wav_path = p
            else:
                # 按语言嵌套
                first_lang = next(iter(pw_data.values())) if pw_data else {}
                if isinstance(first_lang, dict):
                    wav_path = first_lang.get("wav", "")
                    prompt_text = first_lang.get("text", "")
                    p = Path(wav_path)
                    if not p.is_absolute():
                        # 尝试在 prompt_wav/ 子目录
                        p = char_dir / "prompt_wav" / wav_path
                    if p.exists():
                        prompt_wav_path = p
        except (json.JSONDecodeError, OSError):
            pass

    # 如果没有 json，尝试找 .wav 文件
    if not prompt_wav_path:
        for pattern in ["*.wav", "prompt_wav/*.wav"]:
            wavs = list(char_dir.glob(pattern))
            if wavs:
                prompt_wav_path = wavs[0]
                break

    if not prompt_wav_path:
        typer.echo("⚠ 未找到 prompt_wav.json 或 .wav，跳过自动注册", err=True)
        typer.echo(f"  手动注册: genie-term characters add {char_name} --model-dir {char_dir} --lang zh --prompt-wav ... --prompt-text ...", err=True)
        return

    # 推断 model_version
    model_version = "v2"
    if (char_dir / "prompt_encoder_fp32.onnx").exists():
        model_version = "v2ProPlus"

    # 推断语言（PRD §PredefinedCharacter）
    _lang_map = {"feibi": "zh", "mika": "jp", "thirtyseven": "en"}
    lang = _lang_map.get(char_name, "zh")

    char_data = {
        "kind": "preset",
        "language": lang,
        "model_version": model_version,
        "model_dir": str(char_dir),
        "prompt_wav": str(prompt_wav_path),
        "prompt_text": prompt_text or f"预置角色 {char_name} 的参考音频",
    }

    try:
        reg.add(char_name, char_data, force=True)
        reg.save()
        typer.echo(f"✅ 角色 '{char_name}' 自动注册成功 ({model_version}, {lang})")
    except Exception as exc:
        typer.echo(f"⚠ 自动注册失败: {exc}", err=True)


# ========== roberta ==========

@app.command("roberta")
def download_roberta_cmd(
    mirror: str | None = typer.Option(None, "--mirror", help="HF mirror endpoint"),
    yes: bool = typer.Option(False, "--yes", help="跳过确认"),
) -> None:
    """下载中文 RoBERTa 韵律模型（可选）。"""
    from genie_term.core.config import effective_data_dir
    from genie_term.download.genie_data import download_roberta

    data_dir = effective_data_dir()
    typer.echo(f"下载 RoBERTa → {data_dir}")

    if not yes and not sys.stdin.isatty():
        raise UsageError(
            "非交互式环境下载需要 --yes",
            fix="genie-term download roberta --yes",
        )
    if not yes and sys.stdin.isatty():
        confirm = typer.confirm("确认下载可选的 RoBERTa 模型？")
        if not confirm:
            raise typer.Exit(code=0)

    try:
        result = download_roberta(data_dir, mirror=mirror)
        if result.exists():
            typer.echo(f"✅ RoBERTa 就绪: {result}")
        else:
            typer.echo("⚠ RoBERTa 在仓库中未找到（可选组件，V1 可能已下线）", err=True)
    except NetworkError:
        raise
