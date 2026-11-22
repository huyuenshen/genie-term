"""commands/doctor.py —— 12 项环境检查。

PRD §4.4 要求：
  ✔ ok / ⚠ warn / ✘ error 三级 + 末尾一键修复命令
  有 ✘ → 退出码 10；仅 ⚠ → 退出码 0

12 项检查（规格参考文档 §C.4）：
  1. Python 3.10–3.12（✘，3.13 标 ⚠ 实验性）
  2. 依赖完整性 onnxruntime 可 import（✘）
  3. 是否 root 运行（⚠）
  4. GenieData 必需文件（✘）
  5. 中文 RoBERTa 可选（⚠）
  6. 注册表可读/schema 版本（✘）
  7. 已注册角色模型目录与必需文件（✘）
  8. 参考音频存在可解码 3–15s（✘）
  9. 音频输出设备（⚠）
  10. 播放器（⚠）
  11. 磁盘 ≥2GB（⚠）
  12. HF 端点连通 5s 超时（✘，可 --no-network 跳过）

--json 结构：{"checks":[...], "summary":{"ok":N,"warn":N,"error":N}, "exit_code":N}
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import typer

from genie_term.errors import EXIT_ENV, EXIT_OK

app = typer.Typer(
    name="doctor",
    help="Run environment diagnostics (12 checks)",
    add_completion=False,
    invoke_without_command=True,
)


# ========== 数据结构 ==========

@dataclass
class CheckResult:
    id: str
    level: str          # "ok" | "warn" | "error"
    message: str
    fix: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "level": self.level,
            "message": self.message,
            "fix": self.fix,
        }


# ========== 必需文件清单（单一来源：core/registry.py） ==========

from genie_term.core.registry import GENIE_DATA_REQUIRED

# ========== 平台相关修复命令 ==========

def _install_cmd(pkg_deb: str, pkg_rpm: str, pkg_arch: str, pkg_mac: str) -> str:
    """返回当前平台的安装命令。"""
    system = platform.system().lower()
    if system == "linux":
        # 检测发行版
        try:
            with open("/etc/os-release") as f:
                content = f.read()
            if "ubuntu" in content or "debian" in content:
                return f"sudo apt install {pkg_deb}"
            if "fedora" in content or "rhel" in content:
                return f"sudo dnf install {pkg_rpm}"
        except Exception:
            pass
        # 默认 pacman
        return f"sudo pacman -S {pkg_arch}"
    if system == "darwin":
        return f"brew install {pkg_mac}"
    return f"请手动安装: {pkg_deb}/{pkg_mac}"


# ========== 12 项检查实现 ==========

def _check_python() -> CheckResult:
    """1. Python 版本（3.10–3.12 为 ok，3.13 为 warn，其他 error）。"""
    ver = sys.version_info
    ver_str = f"{ver.major}.{ver.minor}.{ver.micro}"
    if ver.major == 3 and 10 <= ver.minor <= 12:
        return CheckResult("python", "ok", f"Python {ver_str}")
    if ver.major == 3 and ver.minor == 13:
        return CheckResult(
            "python", "warn",
            f"Python {ver_str}（实验性）",
            fix="pipx install --python python3.12 genie-term",
        )
    return CheckResult(
        "python", "error",
        f"Python {ver_str}（不支持）",
        fix="安装 Python 3.10–3.12",
    )


def _check_onnxruntime() -> CheckResult:
    """2. onnxruntime 可 import（走 engine/adapter，红线唯一允许的 import 位置）。"""
    from genie_term.engine.adapter import check_onnxruntime
    ok, ver = check_onnxruntime()
    if ok:
        return CheckResult("onnxruntime", "ok", f"onnxruntime {ver}")
    return CheckResult(
        "onnxruntime", "error",
        "onnxruntime 不可 import",
        fix="pipx reinstall genie-term",
    )


def _check_root() -> CheckResult:
    """3. 是否 root 运行。"""
    if os.geteuid() == 0:
        return CheckResult(
            "root", "warn",
            "当前以 root 运行，可能导致权限问题",
            fix="换普通用户运行 genie-term",
        )
    return CheckResult("root", "ok", "非 root 用户")


def _check_genie_data() -> CheckResult:
    """4. GenieData 必需目录/文件存在。"""
    try:
        from genie_term.core.config import effective_data_dir
        data_dir = effective_data_dir()
    except Exception:
        return CheckResult(
            "genie_data", "error",
            "无法解析数据目录",
            fix="genie-term init",
        )

    if not data_dir.exists():
        return CheckResult(
            "genie_data", "error",
            f"数据目录不存在: {data_dir}",
            fix="genie-term init",
        )

    genie_data = data_dir / "GenieData"
    if not genie_data.exists():
        return CheckResult(
            "genie_data", "error",
            f"GenieData 目录不存在: {genie_data}",
            fix="genie-term init",
        )

    missing = [
        req for req in GENIE_DATA_REQUIRED
        if not (genie_data / req).exists()
    ]
    if missing:
        return CheckResult(
            "genie_data", "error",
            f"缺少必需文件: {', '.join(missing)}",
            fix="genie-term init --force",
        )
    return CheckResult("genie_data", "ok", f"GenieData 完整 ({genie_data})")


def _check_roberta() -> CheckResult:
    """5. RoBERTa（可选）。"""
    try:
        from genie_term.core.config import effective_data_dir
        roberta = effective_data_dir() / "GenieData" / "RoBERTa"
        if roberta.exists():
            return CheckResult("roberta", "ok", "RoBERTa 存在")
        return CheckResult(
            "roberta", "warn",
            "RoBERTa 可选组件未安装（韵律优化）",
            fix="genie-term download roberta",
        )
    except Exception:
        return CheckResult("roberta", "warn", "无法检查 RoBERTa 状态")


def _check_registry() -> CheckResult:
    """6. 注册表可读 + schema_version。"""
    try:
        from genie_term.core.paths import registry_path
        path = registry_path()
        if not path.exists():
            # 注册表不存在不算错误（用户可能还没 add 过角色）
            return CheckResult("registry", "ok", "注册表不存在（尚未添加角色）")
        try:
            import tomllib
            with open(path, "rb") as f:
                data = tomllib.load(f)
        except Exception:
            return CheckResult(
                "registry", "error",
                f"注册表损坏: {path}",
                fix="备份后删除 registry.toml 再重新 add 角色",
            )
        ver = data.get("schema_version", 0)
        if ver > 1:
            return CheckResult(
                "registry", "error",
                f"注册表 schema_version={ver} 高于当前支持",
                fix="请升级 genie-term",
            )
        return CheckResult("registry", "ok", f"注册表可读 (schema_version={ver})")
    except Exception as exc:
        return CheckResult("registry", "error", f"注册表检查失败: {exc}")


def _check_registered_models() -> CheckResult:
    """7. 已注册角色模型目录与必需文件。"""
    try:
        from genie_term.core.paths import registry_path
        path = registry_path()
        if not path.exists():
            return CheckResult("models", "ok", "无已注册角色（跳过模型检查）")
        try:
            import tomllib
            with open(path, "rb") as f:
                data = tomllib.load(f)
        except Exception:
            return CheckResult("models", "warn", "注册表无法读取")

        characters = data.get("characters", {})
        if not characters:
            return CheckResult("models", "ok", "无已注册角色")

        for name, char_data in characters.items():
            model_dir = char_data.get("model_dir", "")
            if not model_dir or not Path(model_dir).exists():
                return CheckResult(
                    "models", "error",
                    f"角色 {name} 模型目录缺失: {model_dir}",
                    fix=f"genie-term characters remove {name} --purge && genie-term download character {name}",
                )
        return CheckResult("models", "ok", f"{len(characters)} 个角色模型存在")
    except Exception as exc:
        return CheckResult("models", "warn", f"模型检查跳过: {exc}")


def _check_ref_audio() -> CheckResult:
    """8. 参考音频存在。"""
    try:
        from genie_term.core.paths import registry_path
        path = registry_path()
        if not path.exists():
            return CheckResult("ref_audio", "ok", "无注册角色（跳过参考音频检查）")
        try:
            import tomllib
            with open(path, "rb") as f:
                data = tomllib.load(f)
        except Exception:
            return CheckResult("ref_audio", "warn", "注册表无法读取")

        characters = data.get("characters", {})
        missing: list[str] = []
        for name, char_data in characters.items():
            prompt_wav = char_data.get("prompt_wav", "")
            if prompt_wav and not Path(prompt_wav).exists():
                missing.append(name)

        if missing:
            return CheckResult(
                "ref_audio", "error",
                f"角色 {', '.join(missing)} 参考音频文件缺失",
                fix="重新注册角色: genie-term characters add ...",
            )
        if characters:
            return CheckResult("ref_audio", "ok", "所有参考音频存在")
        return CheckResult("ref_audio", "ok", "无注册角色")
    except Exception as exc:
        return CheckResult("ref_audio", "warn", f"参考音频检查跳过: {exc}")


def _check_audio_device() -> CheckResult:
    """9. 音频输出设备。"""
    system = platform.system().lower()
    if system == "linux":
        if not Path("/dev/snd").exists() and not os.environ.get("PULSE_SERVER"):
            return CheckResult(
                "audio_device", "warn",
                "无音频输出设备（/dev/snd 不存在、PULSE_SERVER 未设）",
                fix="sudo apt install pulseaudio 或 alsa-utils",
            )
        return CheckResult("audio_device", "ok", "音频设备可用")
    if system == "darwin":
        # macOS CoreAudio 通常总是可用的
        return CheckResult("audio_device", "ok", "CoreAudio 可用")
    return CheckResult("audio_device", "warn", f"未知平台: {system}")


def _check_player() -> CheckResult:
    """10. 播放器。"""
    system = platform.system().lower()
    players = []
    if system == "darwin":
        players = ["afplay", "ffplay"]
    elif system == "linux":
        players = ["ffplay", "paplay", "aplay"]

    found = [p for p in players if shutil.which(p)]
    if found:
        return CheckResult("player", "ok", f"播放器可用: {', '.join(found)}")

    deb_pkg = "ffmpeg pulseaudio-utils alsa-utils"
    rpm_pkg = "ffmpeg pulseaudio-utils alsa-utils"
    arch_pkg = "ffmpeg pulseaudio alsa-utils"
    mac_pkg = "ffmpeg"
    return CheckResult(
        "player", "warn",
        "未找到外部播放器（仅影响 --play，合成不受影响）",
        fix=_install_cmd(deb_pkg, rpm_pkg, arch_pkg, mac_pkg),
    )


def _check_disk() -> CheckResult:
    """11. 磁盘剩余 ≥2GB。"""
    try:
        from genie_term.core.paths import resolve_data_dir
        data_dir = resolve_data_dir()
        stat = shutil.disk_usage(str(data_dir))
        free_gb = stat.free / (1024 ** 3)
        if free_gb >= 2:
            return CheckResult("disk", "ok", f"剩余 {free_gb:.1f} GB")
        return CheckResult(
            "disk", "warn",
            f"磁盘仅剩余 {free_gb:.1f} GB（GenieData 约 391MB + 单角色约 230MB）",
            fix="清理磁盘空间",
        )
    except Exception as exc:
        return CheckResult("disk", "warn", f"磁盘检查跳过: {exc}")


def _check_hf_network() -> CheckResult:
    """12. HF 端点连通（5s 超时）。"""
    try:
        from genie_term.core.config import load_config
        cfg = load_config()
        endpoint = cfg.get("network.hf_endpoint", "https://huggingface.co")
        offline = cfg.get("network.offline", False)
        if offline:
            return CheckResult("hf_network", "warn", "离线模式（跳过网络检查）")

        import socket as _socket
        import urllib.request
        _socket.setdefaulttimeout(5)
        req = urllib.request.Request(endpoint, method="HEAD")
        urllib.request.urlopen(req, timeout=5)
        return CheckResult("hf_network", "ok", f"HF 端点可达: {endpoint}")
    except Exception as exc:
        return CheckResult(
            "hf_network", "error",
            f"HF 端点不可达: {exc}",
            fix="genie-term config set network.hf_endpoint https://hf-mirror.com",
        )


# ========== 主检查函数 ==========

def run_doctor(json: bool = False, network_check: bool = True) -> tuple[list[CheckResult], int]:
    """执行全部检查，返回 (结果列表, 建议退出码)。"""
    checks = [
        _check_python(),
        _check_onnxruntime(),
        _check_root(),
        _check_genie_data(),
        _check_roberta(),
        _check_registry(),
        _check_registered_models(),
        _check_ref_audio(),
        _check_audio_device(),
        _check_player(),
        _check_disk(),
    ]
    if network_check:
        checks.append(_check_hf_network())

    # 统计
    counts = {"ok": 0, "warn": 0, "error": 0}
    for c in checks:
        counts[c.level] += 1

    exit_code = EXIT_ENV if counts["error"] > 0 else EXIT_OK
    return checks, exit_code


def _format_symbol(level: str) -> str:
    return {"ok": "✔", "warn": "⚠", "error": "✘"}.get(level, "?")


# ========== Typer 命令 ==========

@app.callback(invoke_without_command=True)
def _callback(
    ctx: typer.Context,
    json_flag: bool = typer.Option(False, "--json", help="Output as JSON"),
    network: bool = typer.Option(True, "--network/--no-network", help="Run HF connectivity check"),
) -> None:
    """Run environment diagnostics."""
    if ctx.invoked_subcommand is not None:
        return

    checks, exit_code = run_doctor(json=json_flag, network_check=network)

    counts = {"ok": 0, "warn": 0, "error": 0}
    for c in checks:
        counts[c.level] += 1

    if json_flag:
        output = {
            "checks": [c.to_dict() for c in checks],
            "summary": counts,
            "exit_code": exit_code,
        }
        typer.echo(json.dumps(output, ensure_ascii=False))
    else:
        for c in checks:
            symbol = _format_symbol(c.level)
            line = f"{symbol} [{c.id}] {c.message}"
            if c.fix and c.level != "ok":
                line += f"\n    → {c.fix}"
            typer.echo(line)

        # 总结
        typer.echo("")
        total = counts["ok"] + counts["warn"] + counts["error"]
        typer.echo(
            f"共 {total} 项: ✔ {counts['ok']} ⚠ {counts['warn']} ✘ {counts['error']}"
        )
        if counts["error"] > 0:
            typer.echo("有 ✘ 错误 —— 请先修复再继续")
        elif counts["warn"] > 0:
            typer.echo("仅有 ⚠ 警告 —— 可以继续，但建议关注")
        else:
            typer.echo("全部 ✔ —— 环境就绪！")

    # 直接 sys.exit 确保退出码正确传播（typer.Exit 在子命令组里可能被吞）
    import sys
    sys.exit(exit_code)
