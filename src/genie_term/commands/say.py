"""commands/say.py —— genie-term say 合成命令。

PRD §4.5 完整规格：
  genie-term say [TEXT] [-c NAME] [-l zh|en|jp] [-o PATH] [-f FILE]
                   [--play/--no-play] [--split-sentence/--no-split]
                   [--if-exists overwrite|skip|timestamp|fail] [--json] [--yes]

文本来源优先级：位置参数 > -f > stdin（非 TTY 且非空），三者全空→退出码 2
语言优先级：-l > 角色语言 > 配置默认；上游只支持 zh/en/jp，注册阶段已拒绝其他
--if-exists 默认 overwrite
首次用某角色模型未下载时 TTY 询问；非 TTY 无 --yes→退出码 10
产物校验：合成后确认文件存在且 >1KB（否则引擎失败码 20）
播放失败不改退出码（仍 0）

退出码：角色不存在→2；参考音频丢失→10；模型目录缺文件→10；输入为空→2；引擎异常→20
"""

from __future__ import annotations

import json as _json
import sys
import time
from datetime import datetime
from pathlib import Path

import typer

from genie_term import context
from genie_term.errors import EXIT_OK, EnvError, UsageError

app = typer.Typer(
    name="say",
    help="合成语音",
    add_completion=False,
    invoke_without_command=True,
)

_VALID_IF_EXISTS = {"overwrite", "skip", "timestamp", "fail"}
_VALID_LANGUAGES = {"zh", "en", "jp"}


# ========== 输出文件名生成 ==========

def _generate_output_path(
    output_dir: str | Path,
    character: str,
    if_exists: str = "overwrite",
) -> Path:
    """-o 是目录时自动命名：genie_<角色>_<YYYYmmdd-HHMMSS>.wav。"""
    d = Path(output_dir).expanduser()
    d.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = d / f"genie_{character}_{timestamp}.wav"

    if path.exists() and if_exists == "timestamp":
        path = d / (
            f"genie_{character}_{timestamp}-"
            f"{datetime.now().microsecond // 1000:03d}.wav"
        )
    return path


def _resolve_if_exists(path: Path, if_exists: str) -> Path | None:
    """显式 -o 文件已存在时按 --if-exists 处理；返回 None 表示跳过。"""
    if not path.exists():
        return path
    if if_exists == "overwrite":
        return path
    if if_exists == "skip":
        return None
    if if_exists == "fail":
        raise UsageError(
            f"输出文件已存在: {path}",
            fix="换个文件名或用 --if-exists overwrite|timestamp",
        )
    # timestamp
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return path.with_name(f"{path.stem}-{stamp}{path.suffix}")


# ========== 播放决策链 ==========

def _should_play(play_mode: bool | str) -> bool:
    """根据 CLI/配置和 TTY 状态决定是否播放。

    PRD §4.5：--play 默认仅交互式 TTY 且检测到播放器时为开。
    """
    if play_mode is True or play_mode == "always":
        return True
    if play_mode is False or play_mode == "never":
        return False
    if not sys.stdin.isatty():
        return False
    from genie_term.core.player import get_available_player

    return get_available_player() is not None


# ========== 输入解析 ==========

def _resolve_text(text: str | None, input_file: str | None) -> str:
    """位置参数 > -f > stdin（PRD §4.5 规则 1）。"""
    if text is not None and text.strip():
        return text.strip()

    if input_file:
        p = Path(input_file).expanduser()
        if not p.exists():
            raise UsageError(
                f"文本文件不存在: {p}",
                fix=f"确认路径后重试: genie-term say -f {p} '补一句'",
            )
        return p.read_text(encoding="utf-8").strip()

    if not sys.stdin.isatty():
        return sys.stdin.read().strip()

    return ""


def _ensure_character_model(
    char_name: str, char_data: dict, *, yes: bool
) -> dict:
    """首次使用预置角色时按 PRD §4.5 规则 6 处理模型缺失。"""
    model_dir = char_data.get("model_dir", "")
    if model_dir and Path(model_dir).exists():
        return char_data

    if char_data.get("kind") != "preset":
        raise EnvError(
            f"角色 '{char_name}' 模型目录缺失: {model_dir}",
            fix=f"genie-term characters remove {char_name} --purge && "
                f"genie-term characters add {char_name} --model-dir ...",
        )

    from genie_term.core.config import effective_data_dir

    data_dir = effective_data_dir()
    manual_path = data_dir / "CharacterModels" / "v2ProPlus" / char_name

    if context.is_offline():
        raise EnvError(
            f"角色 '{char_name}' 模型未下载，且当前为离线模式",
            location=str(manual_path),
            fix=f"在有网机器运行 genie-term download character {char_name} --yes，"
                f"再把数据目录拷贝到 {data_dir}",
        )

    should_download = yes
    if not should_download and sys.stdin.isatty():
        should_download = typer.confirm(
            f"角色 '{char_name}' 模型未下载，是否下载约 230MB？"
        )
    if not should_download:
        raise EnvError(
            f"角色 '{char_name}' 模型未下载",
            location=str(manual_path),
            fix=f"genie-term download character {char_name} --yes",
        )

    from genie_term.download.genie_data import download_character
    from genie_term.download.presets import auto_register_preset

    char_dir = download_character(data_dir, char_name)
    auto_register_preset(char_name, char_dir)

    from genie_term.core.registry import load_registry

    refreshed = load_registry().get(char_name)
    if not refreshed or not Path(refreshed.get("model_dir", "")).exists():
        raise EnvError(
            f"角色 '{char_name}' 下载后仍未就绪",
            location=str(char_dir),
            fix=f"手动注册: genie-term characters add {char_name} --model-dir {char_dir}",
        )
    return refreshed


# ========== 主合成流程 ==========

def run_say(
    text: str | None = None,
    *,
    character: str | None = None,
    language: str | None = None,
    output: str | None = None,
    input_file: str | None = None,
    play: bool | None = None,
    split_sentence: bool = True,
    if_exists: str = "overwrite",
    yes: bool = False,
    offline: bool = False,
) -> dict:
    """执行合成流程，返回结果字典（供人类/JSON 两种输出使用）。"""
    from genie_term.core.config import effective_data_dir, load_config
    from genie_term.core.log import log_event, text_fingerprint
    from genie_term.core.registry import load_registry

    if if_exists not in _VALID_IF_EXISTS:
        raise UsageError(
            f"--if-exists 取值非法: {if_exists}",
            fix="允许: overwrite|skip|timestamp|fail",
        )

    cfg = load_config()
    reg = load_registry()

    resolved_text = _resolve_text(text, input_file)
    if not resolved_text:
        available = list(reg.list_characters().keys())
        msg = "没有收到文本（可用参数、-f 或管道）"
        if not character and available:
            msg += f"\n可用角色: {', '.join(available)}"
        raise UsageError(msg, fix="genie-term say '你好' 或 echo '你好' | genie-term say")

    char_name = character or cfg.get("general.default_character")
    if not char_name:
        available = list(reg.list_characters().keys())
        raise UsageError(
            "未指定角色且无默认角色",
            fix=f"genie-term say -c {available[0] if available else 'feibi'} '你好'",
        )

    char_data = reg.get(char_name)
    if not char_data:
        available = list(reg.list_characters().keys())
        raise UsageError(
            f"角色 '{char_name}' 不存在",
            fix=f"genie-term characters list  # 可用: "
                f"{', '.join(available) if available else '先 genie-term download character feibi'}",
        )

    # 首次使用：模型缺失时的下载/报错
    char_data = _ensure_character_model(char_name, char_data, yes=yes)

    # 语言优先级：-l > 角色语言 > 配置默认
    effective_lang = (language or char_data.get("language")
                      or cfg.get("general.default_language", "zh")).lower()
    if effective_lang not in _VALID_LANGUAGES:
        raise UsageError(
            f"语言 '{effective_lang}' 不支持（上游只支持 zh/en/jp）",
            fix="genie-term characters add ... --lang zh|en|jp",
        )

    model_dir = char_data.get("model_dir", "")
    prompt_wav = char_data.get("prompt_wav", "")
    prompt_text = char_data.get("prompt_text", "")
    if not prompt_wav or not Path(prompt_wav).exists():
        raise EnvError(
            f"角色 '{char_name}' 的参考音频不存在: {prompt_wav}",
            fix=f"请重新注册: genie-term characters add {char_name} "
                f"--model-dir {model_dir} --prompt-wav ... --prompt-text ...",
        )

    # 环境注入必须在 import genie_tts 之前
    data_dir = effective_data_dir()
    from genie_term.download.verify import verify_genie_data
    from genie_term.engine.bootstrap import ensure_env

    missing = verify_genie_data(data_dir / "GenieData")
    if missing:
        # 陷阱 2：数据不完整时绝不能 import 上游（会 input() 挂起）
        raise EnvError(
            f"GenieData 缺少必需资源: {', '.join(missing)}",
            location=str(data_dir / "GenieData"),
            fix="genie-term init  # 或把完整 GenieData 放到上述路径",
        )

    ensure_env(data_dir=str(data_dir), offline=context.is_offline(offline))

    # 输出路径
    skipped = False
    if output:
        candidate = Path(output).expanduser()
        if candidate.is_dir() or str(output).endswith(("/", "\\")):
            out_path = _generate_output_path(candidate, char_name, if_exists)
            if out_path.exists() and if_exists == "skip":
                skipped = True
        else:
            resolved = _resolve_if_exists(candidate.resolve(), if_exists)
            if resolved is None:
                skipped = True
                out_path = candidate.resolve()
            else:
                out_path = resolved
    else:
        output_dir = cfg.get("general.output_dir", "~/Music/genie-term")
        out_path = _generate_output_path(output_dir, char_name, if_exists)
        if out_path.exists() and if_exists == "skip":
            skipped = True

    if skipped:
        log_event("say.skip", character=char_name, output=str(out_path))
        context.info(f"输出已存在，按 --if-exists skip 跳过: {out_path}")
        return {
            "ok": True,
            "character": char_name,
            "output": str(out_path),
            "skipped": True,
        }

    # 长文本提示（V1 不切分）
    if len(resolved_text) > 2000:
        context.info("⚠ 文本超过 2000 字，V1 直接交给上游 split_sentence；建议分段合成")

    # 加载角色 + 设置参考音频 + 合成
    from genie_term.engine import adapter

    kind = char_data.get("kind", "local")
    if kind == "preset":
        adapter.load_predefined_character(char_name, data_dir)
    else:
        adapter.load_character(char_name, model_dir, effective_lang)
    adapter.set_reference_audio(char_name, prompt_wav, prompt_text, effective_lang)

    context.info(f"合成中: {char_name} ({effective_lang}) → {out_path}")
    started = time.perf_counter()
    result_path = adapter.synth(
        char_name, resolved_text, out_path, split_sentence=split_sentence
    )
    elapsed_ms = int((time.perf_counter() - started) * 1000)

    from genie_term.core.audio import probe_duration

    duration = probe_duration(result_path)
    log_event(
        "say.ok",
        character=char_name,
        language=effective_lang,
        output=str(result_path),
        elapsed_ms=elapsed_ms,
        text=text_fingerprint(resolved_text),
    )

    # 播放（播放失败不改退出码）
    play_mode: bool | str = cfg.get("general.play", "auto") if play is None else play
    if _should_play(play_mode):
        from genie_term.core.player import play as _player_play

        context.info("播放中...")
        if not _player_play(result_path):
            context.info("⚠ 未找到可用播放器或播放失败，仅存盘（不影响退出码）")

    return {
        "ok": True,
        "character": char_name,
        "output": str(Path(result_path).resolve()),
        "duration_s": round(duration, 2) if duration is not None else None,
        "elapsed_ms": elapsed_ms,
    }


# ========== Typer 命令 ==========

@app.callback(invoke_without_command=True)
def _callback(
    ctx: typer.Context,
    text: str | None = typer.Argument(None, help="要合成的文本"),
    character: str | None = typer.Option(None, "-c", help="角色名称"),
    language: str | None = typer.Option(None, "-l", help="语言 zh|en|jp"),
    output: str | None = typer.Option(None, "-o", help="输出路径（文件或目录）"),
    input_file: str | None = typer.Option(None, "-f", "--file", help="从文件读取文本"),
    play: bool | None = typer.Option(None, "--play/--no-play", help="播放开关"),
    split_sentence: bool = typer.Option(True, "--split-sentence/--no-split", help="长文分句"),
    if_exists: str = typer.Option("overwrite", "--if-exists", help="overwrite|skip|timestamp|fail"),
    json_flag: bool = typer.Option(False, "--json", help="输出 JSON 到 stdout"),
    yes: bool = typer.Option(False, "--yes", help="跳过确认"),
    offline: bool = typer.Option(False, "--offline", help="禁止网络（缺失资源直接报错）"),
) -> None:
    if ctx.invoked_subcommand is not None:
        return

    if offline:
        context.set_offline(True)

    result = run_say(
        text=text,
        character=character,
        language=language,
        output=output,
        input_file=input_file,
        play=play,
        split_sentence=split_sentence,
        if_exists=if_exists,
        yes=yes,
        offline=offline,
    )

    if json_flag:
        typer.echo(_json.dumps(result, ensure_ascii=False))
    elif result.get("skipped"):
        typer.echo(f"↷ {result['output']}")
    else:
        typer.echo(f"✅ {result['output']}")

    raise typer.Exit(code=EXIT_OK)
