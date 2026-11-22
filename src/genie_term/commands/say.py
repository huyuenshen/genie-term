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
from datetime import datetime
from pathlib import Path

import typer

from genie_term.errors import (
    EXIT_OK,
    EnvError,
    UsageError,
)

app = typer.Typer(
    name="say",
    help="合成语音",
    add_completion=False,
    invoke_without_command=True,
)


# ========== 输出文件名生成 ==========

def _generate_output_path(
    output_dir: str | Path,
    character: str,
    if_exists: str = "overwrite",
) -> Path:
    """生成输出路径。

    -o 是目录时自动命名：genie_<角色>_<YYYYmmdd-HHMMSS>.wav
    已存在时按 --if-exists 处理。
    """
    d = Path(output_dir).expanduser()
    d.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    filename = f"genie_{character}_{timestamp}.wav"
    path = d / filename

    if path.exists():
        if if_exists == "skip":
            raise typer.Exit(code=EXIT_OK)  # 跳过即成功
        elif if_exists == "fail":
            raise UsageError(
                f"输出文件已存在: {path}",
                fix="换个文件名或用 --if-exists overwrite|timestamp",
            )
        elif if_exists == "timestamp":
            # 追加毫秒避免冲突
            filename = f"genie_{character}_{timestamp}-{datetime.now().microsecond // 1000:03d}.wav"
            path = d / filename
        # overwrite: 直接覆盖

    return path


# ========== 播放决策链 ==========

def _should_play(play_mode: str) -> bool:
    """根据配置和 TTY 状态决定是否播放。"""
    if play_mode == "always":
        return True
    if play_mode == "never":
        return False
    # auto: 交互式 TTY 才播放
    return sys.stdin.isatty()


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
) -> Path:
    """执行合成流程，返回输出文件路径。

    Raises 对应的 GenieTermError（退出码由调用方映射）。
    """
    from genie_term.core.config import load_config
    from genie_term.core.paths import resolve_data_dir
    from genie_term.core.registry import load_registry
    from genie_term.engine import adapter
    from genie_term.engine.bootstrap import ensure_env

    cfg = load_config()
    reg = load_registry()

    # ---- 文本来源 ----
    if input_file:
        with open(input_file, encoding="utf-8") as f:
            text = f.read().strip()
    elif text is None and not sys.stdin.isatty():
        text = sys.stdin.read().strip()

    if not text:
        available = list(reg.list_characters().keys())
        msg = "没有合成文本"
        if not character and available:
            msg += f"\n可用角色: {', '.join(available)}"
        raise UsageError(
            msg,
            fix="genie-term say '你好' 或 echo '你好' | genie-term say",
        )

    # ---- 角色解析 ----
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
            fix=f"可用角色: {', '.join(available) if available else 'genie-term download character feibi'}",
        )

    # ---- 语言解析 ----
    effective_lang = language or char_data.get("language") or cfg.get("general.default_language", "zh")
    if effective_lang not in {"zh", "en", "jp"}:
        raise UsageError(
            f"语言 '{effective_lang}' 不支持（上游只支持 zh/en/jp）",
            fix="genie-term characters add ... --lang zh|en|jp",
        )

    # ---- 模型/参考音频检查 ----
    model_dir = char_data.get("model_dir", "")
    if not model_dir or not Path(model_dir).exists():
        raise EnvError(
            f"角色 '{char_name}' 模型目录缺失: {model_dir}",
            fix=f"genie-term download character {char_name}" if char_data.get("kind") == "preset"
                 else f"genie-term characters remove {char_name} --purge && genie-term characters add ...",
        )

    prompt_wav = char_data.get("prompt_wav", "")
    prompt_text = char_data.get("prompt_text", "")
    if not prompt_wav or not Path(prompt_wav).exists():
        raise EnvError(
            f"角色 '{char_name}' 参考音频缺失",
            fix=f"genie-term characters add {char_name} --model-dir ... --prompt-wav ... --prompt-text ...",
        )

    # ---- 确保 env 注入 + 加载角色 ----
    data_dir = resolve_data_dir()
    ensure_env(data_dir=str(data_dir))

    # 加载角色 + 设置参考音频
    char_data.get("model_version", "v2")
    kind = char_data.get("kind", "local")

    if kind == "preset":
        adapter.load_predefined_character(char_name, data_dir)
    else:
        adapter.load_character(char_name, model_dir, effective_lang)

    adapter.set_reference_audio(char_name, prompt_wav, prompt_text, effective_lang)

    # ---- 输出路径 ----
    if output:
        out_path = Path(output).expanduser()
        if out_path.is_dir():
            out_path = _generate_output_path(out_path, char_name, if_exists)
    else:
        output_dir = cfg.get("general.output_dir", "~/Music/genie-term")
        out_path = _generate_output_path(output_dir, char_name, if_exists)

    # ---- 合成 ----
    typer.echo(f"合成中: {char_name} ({effective_lang}) → {out_path}", err=True)
    result_path = adapter.synth(
        char_name,
        text,
        out_path,
        split_sentence=split_sentence,
    )

    # ---- 播放（播放失败不改退出码） ----
    play_mode = play if play is not None else cfg.get("general.play", "auto")
    if _should_play(play_mode):
        from genie_term.core.player import play as _player_play
        typer.echo("播放中...", err=True)
        played = _player_play(result_path)
        if not played:
            typer.echo("⚠ 未找到可用播放器，仅存盘", err=True)

    return result_path


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
) -> None:
    if ctx.invoked_subcommand is not None:
        return

    try:
        path = run_say(
            text=text,
            character=character,
            language=language,
            output=output,
            input_file=input_file,
            play=play,
            split_sentence=split_sentence,
            if_exists=if_exists,
            yes=yes,
        )
    except (UsageError, EnvError):
        # 这些已经格式化好了 message
        raise
    except Exception:
        raise

    if json_flag:
        typer.echo(_json.dumps({"output": str(path)}, ensure_ascii=False))
    else:
        typer.echo(f"✅ {path}")

    raise typer.Exit(code=EXIT_OK)
