# Changelog

本项目遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 格式，
版本号遵循 [SemVer](https://semver.org/lang/zh-CN/)。

## [Unreleased]

### 计划中（M4 里程碑）

- 真实联网 `init` / `download character feibi` / `say` 端到端首声验证（391MB + 230MB）
- 坏环境矩阵测试：无 gcc、无音频设备、只读 HOME、磁盘 <500MB、中文/空格路径、`| head -1` SIGPIPE
- `--json` 全命令 jq 校验、`genie-term --help` P95 ≤400ms hyperfine 实测
- pip-audit 安全扫描、PyPI 发布检查清单（PRD §14 九项）

## [0.0.1a0] - 2026-11-22

首个可用版本。M0–M3 里程碑主体完成：全部 9 个命令组、错误契约、下载与合成链路，离线测试 67 个全绿。

### Added

- **CLI 框架**：typer 装配（`cli.py`），`--version` 顶级开关，异常→退出码统一映射（`main()`），`GENIE_TERM_DEBUG=1` 才打印堆栈。
- **命令组**（9 个）：
  - `version [--json]` — genie-term / genie-tts / onnxruntime / Python / 平台信息
  - `config show|get|set|reset|path` — 配置管理，schema_version 校验，原子写
  - `doctor [--json] [--no-network]` — 12 项环境诊断，✔/⚠/✘ 三级 + 一键修复命令，有 ✘ 退出码 10
  - `init [--yes] [--mirror] [--data-dir]` — 首次初始化：下载 GenieData 391MB + 必需文件校验 + 写 config.toml
  - `download genie-data|character|roberta` — 绝对目录 `snapshot_download`；预置角色下载后解析 `prompt_wav.json` **自动注册**
  - `characters list|show|add|use|remove` — 角色注册表管理；`add` 校验参考音频成对必填、扩展名白名单、model_version 文件推断
  - `say` — 合成：位置参数/`-f`/stdin 三来源，`--json`/`--play`/`--if-exists`，产物 >1KB 校验
  - `convert` — GPT-SoVITS → ONNX；缺 torch 退出码 21 并只给一条正确注入命令；临时目录 + 原子改名 + 9 文件校验
  - `serve` — 本地 HTTP API；默认 127.0.0.1，`0.0.0.0` 需 `--allow-public` + TTY 二次确认，workers 上限 1
  - `completion bash|zsh|fish` — Shell 补全脚本
- **退出码契约**（PRD §4.1）：0 / 2 / 10 / 11 / 12 / 20 / 21 / 130，配套 `errors.py` 七种 `GenieTermError` 子类，每条错误含「是什么/在哪/下一步」。
- **核心库**：
  - `core/paths.py` — platformdirs 目录解析（Linux XDG / macOS ~/Library），环境变量覆盖
  - `core/config.py` — config.toml 读写，校验→备份 `.bak`→临时文件→`os.replace` 原子写
  - `core/registry.py` — registry.toml 角色注册表，必需文件清单单一来源（7+2 文件），model_version 自动推断
  - `core/audio.py` — 参考音频扩展名/时长校验（3–15s 最佳，>20s 拒绝），合成产物 >1KB 验证
  - `core/player.py` — 播放策略链 sounddevice→afplay(macOS)→ffplay→paplay→aplay(Linux)，全失败仅警告不影响退出码
- **引擎适配层**：
  - `engine/bootstrap.py` — `GENIE_DATA_DIR` / `HF_ENDPOINT` / 离线开关在 import 上游前注入，进程内幂等仅一次
  - `engine/adapter.py` — 全项目唯一 `import genie_tts` 的文件；加载/参考音频/合成/转换/服务八个上游函数签名封装
- **下载层**：`download/genie_data.py` — `huggingface_hub.snapshot_download` 绝对目录下载（GenieData 391MB / 预置角色约 230MB / RoBERTa 可选自实现），失败统一码 11 + hf-mirror 修复命令
- **受控 fork**：`vendor/genie-tts-unix`（`genie-tts-unix==2.0.2`）
- **测试**：单元 + 集成共 67 个离线用例，含 adapter.py 外无 `genie_tts` import 的红线 AST 断言
- **文档**：README.md、docs/ARCHITECTURE.md、docs/DECISION-M0.md

### Fixed

- **上游陷阱 2（导入期 input() 挂起）**：数据目录不存在时上游在模块导入阶段执行 `input("是否下载…(y/N)")`，非 TTY 下挂起/抛 EOFError。`adapter.check_genie_tts()` 现在先解析数据目录并检查存在性，不存在则不 import，由 genie-term 先行报错（退出码 10）。
- **console script 入口**：`pyproject.toml` 原指向 `cli:app`，绕过了 `main()` 的异常处理链导致退出码恒为 1；已修正为 `genie_term.cli:main`，退出码契约（2/10/11/20/21/130）恢复正常。

### Security

- `serve` 默认仅监听 `127.0.0.1`；`--host 0.0.0.0` 必须 `--allow-public` 且 TTY 二次确认，非交互缺 `--yes` 退出码 2。
- 非 TTY 环境绝不提问：所有需要确认的操作（下载/覆盖/公开监听）缺 `--yes` 时退出码 2 并打印带 `--yes` 的完整命令。
- 日志不记录合成文本内容；默认无遥测、无崩溃上报。
- 外部播放器一律列表参数 `subprocess.run([...])`，禁止 `shell=True`。

[Unreleased]: https://example.com/genie-term/compare/0.0.1a0...HEAD
[0.0.1a0]: https://example.com/genie-term/releases/tag/v0.0.1a0
