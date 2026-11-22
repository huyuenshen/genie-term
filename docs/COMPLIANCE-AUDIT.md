# genie-term 合规性审计报告

> 审计对象：`/home/neurosamalover/Documents/Projects/pys/genie-term`（0.0.1a0，M0–M3 主体）
> 审计依据（唯一真相源优先级）：
> 1. `docs/genie-term-PRD-v1.2-Unix版.docx`（PRD，正文标注为 v1.1/v1.2 Unix 版）
> 2. [.trae/rules/project_rules.md](file:///home/neurosamalover/Documents/Projects/pys/genie-term/.trae/rules/project_rules.md)
> 3. [docs/genie-term-规格参考-规则与里程碑未覆盖项.md](file:///home/neurosamalover/Documents/Projects/pys/genie-term/docs/genie-term-%E8%A7%84%E6%A0%BC%E5%8F%82%E8%80%83-%E8%A7%84%E5%88%99%E4%B8%8E%E9%87%8C%E7%A8%8B%E7%A2%91%E6%9C%AA%E8%A6%86%E7%9B%96%E9%A1%B9.md)（补充规格，A–M 节）
> 4. [docs/DECISION-M0.md](file:///home/neurosamalover/Documents/Projects/pys/genie-term/docs/DECISION-M0.md)（M0 方案 B 授权记录）
> 审计日期：2026-11-22
> 审计方式：逐章条款 → 代码/目录/配置/文档对照 → 运行时取证（pytest、ruff、CLI 实跑、异常路径）
> 说明：本报告同时记录**整改前**问题与**整改后**状态；“已修复”项均已在本次会话落地并验证。

---

## 0. 结论摘要

| 指标 | 审计时 | 整改后 |
| --- | --- | --- |
| 总体合规评分 | **62 / 100** | **86 / 100** |
| 严重违规 | 15 项 | 0 项 |
| 一般违规 | 20 项 | 2 项（CI、性能） |
| 轻微建议 | 6 项 | 5 项（架构预留/规格歧义） |
| 项目红线（project_rules §4） | 10/12 通过 | **12/12 通过** |
| 离线测试 | 67 通过 | **81 通过** |
| 静态检查 `ruff check src tests` | 失败（134 错误） | **全绿** |

**核心结论**：项目分层、上游单点封装、原子写、数据目录、必需文件清单等骨架符合 PRD；但审计发现多项**会导致真实用户路径失败**的偏差，集中在退出码契约、`say` 播放/数据目录/JSON、预置角色注册、huggingface_hub 2.x 兼容、离线模式与 convert 注册。上述问题已全部修复并通过离线测试验证。剩余未完成项主要是 CI 工作流、`--help` 冷启动性能与真实联网 E2E，属于 M4 发布阶段任务。

---

## 1. 评分明细

| 维度 | 权重 | 审计时 | 整改后 | 主要依据 |
| --- | --- | --- | --- | --- |
| 命令功能与参数完整性 | 20% | 55 | 92 | PRD §4.3–§4.10、补充规格 §C |
| 退出码与输出契约 | 20% | 50 | 96 | PRD §4.1、§7；project_rules §4 |
| 架构分层与红线 | 15% | 92 | 96 | PRD §6.2/§6.3/§6.4；rules §4/§5 |
| 数据/配置/注册表 Schema | 15% | 88 | 95 | PRD §6.6/§6.7；补充规格 §D/§E |
| 工程交付物与 CI | 10% | 55 | 70 | PRD §6.5/§11/§14 |
| 测试与质量门禁 | 10% | 58 | 82 | PRD §10；rules §3 |
| 性能指标 | 10% | 55 | 65 | PRD §2.4/§6.10 |

加权得分：`20%×92 + 20%×96 + 15%×96 + 15%×95 + 10%×70 + 10%×82 + 10%×65 ≈ 86`。

---

## 2. 符合项清单（按 PRD 章节）

| 条款 | 要求摘要 | 实现证据 | 结论 |
| --- | --- | --- | --- |
| §1 / §2.5 | 不做 GUI/训练/内置权重/云端/Windows；Unix-like 主线 | 代码仅 CLI；无 GUI/训练依赖 | 符合 |
| §3 | P0 全命令；P1 convert/serve/config/completion/镜像/离线；P2 不实现 | 9 个命令组齐全；P2 未越界 | 符合 |
| §4.1 | stdout 只放结果，进度/警告走 stderr | `say/init/download/convert/serve` 进度均 `err=True` | 符合 |
| §4.1 | `--json` 单对象、snake_case、绝对路径 | doctor/say/characters/version/convert/serve 均为单对象；本次修正 `characters` 美化换行 | 符合 |
| §4.1 | `--quiet` / `--no-color` / `--offline` | [context.py](file:///home/neurosamalover/Documents/Projects/pys/genie-term/src/genie_term/context.py) + `cli.py` 全局选项 | 符合 |
| §4.1 | 非 TTY 不提问，需确认缺 `--yes` → 2 | init/download/remove/serve/config reset 均已守卫 | 符合 |
| §4.1 | Ctrl-C 清理临时文件 → 130 | convert 临时目录在 `KeyboardInterrupt` 分支清理；`cli.main` 映射 130 | 符合 |
| §4.1 | 参数优先级 CLI > env > config > 默认 | `effective_data_dir` 已按此顺序修正 | 符合 |
| §4.2 | 命令树完整 | [cli.py](file:///home/neurosamalover/Documents/Projects/pys/genie-term/src/genie_term/cli.py#L67-L106) | 符合 |
| §4.3 | init 7 步、幂等、`--force`、`--mirror`、`--data-dir` | [init.py](file:///home/neurosamalover/Documents/Projects/pys/genie-term/src/genie_term/commands/init.py) | 符合 |
| §4.4 | doctor 12 项、✔/⚠/✘、有 ✘→10、末尾修复命令、`--json` | [doctor.py](file:///home/neurosamalover/Documents/Projects/pys/genie-term/src/genie_term/commands/doctor.py) | 符合 |
| §4.5 | say 三文本来源、语言优先级、输出命名、播放链、产物 >1KB | [say.py](file:///home/neurosamalover/Documents/Projects/pys/genie-term/src/genie_term/commands/say.py) | 符合 |
| §4.6 | characters list/show/add/use/remove 及校验规则 | [characters.py](file:///home/neurosamalover/Documents/Projects/pys/genie-term/src/genie_term/commands/characters.py) | 符合 |
| §4.7 | 绝对目录 snapshot_download、pattern、镜像、离线、码 11 | [genie_data.py](file:///home/neurosamalover/Documents/Projects/pys/genie-term/src/genie_term/download/genie_data.py) | 符合 |
| §4.8 | convert 缺 torch→21、只给一条命令、9 文件校验、注册 | [convert.py](file:///home/neurosamalover/Documents/Projects/pys/genie-term/src/genie_term/commands/convert.py) | 符合 |
| §4.9 | serve 默认回环、0.0.0.0 需 allow-public + 二次确认、workers≤1、`--json` | [serve.py](file:///home/neurosamalover/Documents/Projects/pys/genie-term/src/genie_term/commands/serve.py) | 符合 |
| §4.10 | config / completion / version | `commands/config.py`、`completion.py`、`version.py` | 符合 |
| §5.1–§5.4 | 首次安装、自有模型、脚本化、离线四条流程可复制 | README 与 init/download/say/convert 支持 | 符合 |
| §6.1 | 依赖版本策略 | typer/rich/platformdirs/tomli/tomli-w/hatchling 均符合；`genie-tts-unix==2.0.2` 为 M0 方案 B 授权（见 DECISION-M0 §2） | 符合（授权偏差） |
| §6.2 | 分层与单向依赖 | commands→core/download→engine；业务层无 `genie_tts` | 符合 |
| §6.3 | 上游函数契约 | [adapter.py](file:///home/neurosamalover/Documents/Projects/pys/genie-term/src/genie_term/engine/adapter.py) 覆盖 load/set_ref/tts/unload/convert/serve | 符合 |
| §6.4 | 六个上游陷阱对策 | adapter/bootstrap/download 注释与实现逐条对应 | 符合 |
| §6.6 | 数据布局与 7+2 文件清单 | `core/registry.py` 单一来源；`download/verify.py` 复用 | 符合 |
| §6.7 | config/registry Schema 与更高版本拒绝 | `core/config.py`、`core/registry.py` | 符合 |
| §6.9 | 平台/Python 承诺 | `requires-python = ">=3.10,<3.13"`；README 平台 | 符合 |
| §6.11 | 先落盘 wav，播放失败不影响退出码 | `adapter.synth` → `verify` → `player.play`（失败仅警告） | 符合 |
| §7 | 错误四要素、无裸 traceback、日志脱敏 | `errors.py`；新增 `core/log.py`（长度+哈希） | 符合 |
| §8 | 不 sudo、不写系统目录、原子写、无 telemetry | 代码审计通过 | 符合 |
| §9 | US-01～US-16 | 见第 6 节运行证据 | 基本符合（US-01 需真实安装环境） |
| §10.1 | 单元/集成离线、engine_stub 顺序 | 81 用例，含 adapter 红线 AST 测试 | 符合 |
| rules §4 | 12 条红线 | 逐条核对，见下表 | 全部符合 |

### 2.1 project_rules §4 红线逐条核对

| 红线 | 结果 | 证据 |
| --- | --- | --- |
| 仅 `engine/adapter.py` 可 `import genie_tts` | 通过 | grep + [test_cli.py](file:///home/neurosamalover/Documents/Projects/pys/genie-term/tests/integration/test_cli.py#L193-L225) |
| 路径一律 platformdirs | 通过 | [paths.py](file:///home/neurosamalover/Documents/Projects/pys/genie-term/src/genie_term/core/paths.py) |
| `GENIE_DATA_DIR`/`HF_ENDPOINT` 在 import 前设置、进程内一次 | 通过 | [bootstrap.py](file:///home/neurosamalover/Documents/Projects/pys/genie-term/src/genie_term/engine/bootstrap.py) |
| 禁用上游 `download_genie_data()` | 通过 | 全项目无该调用 |
| 不依赖 `tts()` 返回值，产物 >1KB | 通过 | `adapter.synth` + `core/audio.verify_product_or_raise` |
| `--json` stdout 单对象 | 通过 | 本次修复 characters 的 `indent=2` |
| 退出码 0/2/10/11/12/20/21/130 | 通过 | 本次修复用法错误 20→2；SIGPIPE 安静退出 |
| registry/config 原子写 `.bak` + `os.replace` | 通过 | `config.py`、`registry.py` |
| 禁止 `shell=True` | 通过 | `player.py` 全部列表参数 |
| 非 TTY 绝不提问 | 通过 | 本次修复 `remove --purge` |
| serve 默认回环、公网需 allow-public | 通过 | `serve.py` |
| 错误无裸 traceback、日志不记录文本 | 通过 | `errors.py`、`core/log.py` |
| 不 sudo、不写 /usr /etc、>100MB 显式确认 | 通过 | init/download 均确认 391MB/230MB |

---

## 3. 不符合项明细

等级定义：
- **严重**：违反退出码/输出契约、核心用户路径不可用、红线违规；
- **一般**：功能偏差、规范违反但不阻断主路径；
- **轻微**：命名/文档/结构一致性建议。

### 3.1 严重违规（审计时 15 项，整改后 0）

| ID | 条款 | 当前实现（审计时） | 偏差 | 状态 |
| --- | --- | --- | --- | --- |
| S-01 | PRD §4.1 退出码 | `app(standalone_mode=False)` 抛出的 click 用法错误落入 `except Exception` → **20**；实测 `genie-term say --bad`、`genie-term nope` 均为 20 | 用法/未知命令/未知参数应为 **2** | 已修复（typer 内置 click 异常映射） |
| S-02 | PRD §4.1 参数优先级 | `effective_data_dir()` 先读 config，再读 env | env 应优先于 config | 已修复 |
| S-03 | PRD §5.4 离线部署 | `say` 用 `resolve_data_dir()`，忽略 `config engine.data_dir` | 设置 data_dir 后 say 仍用默认目录 | 已修复（改用 `effective_data_dir`） |
| S-04 | PRD §4.5 规则 5 | `_should_play(play)` 直接接收布尔；`--play` 在非 TTY 不播放，`--no-play` 在 TTY 反而播放 | 布尔应归一化为 always/never | 已修复 |
| S-05 | PRD §4.6 / §6.7 | 预置角色自动注册 `model_dir=角色根目录` | 必需文件在 `tts_models/`，注册校验必失败 | 已修复（`download/presets.py`） |
| S-06 | PRD §4.7 | `snapshot_download(..., local_dir_use_symlinks=False, resume_download=True)` | huggingface_hub 2.4.0 已删除这两个参数 → **TypeError**，下载必失败 | 已修复 |
| S-07 | PRD §4.7 / §6.4 陷阱 6 | RoBERTa `local_dir=GenieData` 但 pattern 为 `GenieData/RoBERTa/**` | 会下到 `GenieData/GenieData/RoBERTa` | 已修复（local_dir=数据根） |
| S-08 | PRD §4.1 非 TTY | `characters remove --purge` 无 `--yes` 时直接 `typer.confirm` | 非 TTY 抛 Abort（退出码 1），应退出 2 并给命令 | 已修复 |
| S-09 | PRD §6.4 陷阱 2 | `say` 只检查 model/prompt，不检查 GenieData；`adapter.check_genie_tts` 只检查 data_dir 存在 | GenieData 不完整时 import 上游可能 `input()` 挂起 | 已修复（合成前 `verify_genie_data`，先报 10） |
| S-10 | PRD §4.5 示例 | `--json` 仅 `{"output": ...}` | 缺 `ok/character/duration_s/elapsed_ms` | 已修复 |
| S-11 | PRD §5.4 | `init` / `download` 无 `--offline` | 离线部署命令不可用 | 已修复 |
| S-12 | PRD §4.5 规则 6 | 首用角色模型缺失仅报错，无 TTY 下载询问；`--yes` 未使用 | 非 TTY 无 `--yes` 应码 10；TTY 应询问 230MB | 已修复 |
| S-13 | PRD §4.8 / §5.2 | `convert --register` 只打印后续命令，不注册；不接受 `--prompt-wav/--prompt-text` | README/PRD 示例命令不可执行 | 已修复 |
| S-14 | PRD §4.9 | `serve` 无 `--json`，未打印 `{"host","port","docs"}` | 缺少约定输出 | 已修复 |
| S-15 | PRD §4.1 / §10.2 | `completion bash \| head -1` 触发 BrokenPipeError → 内部错误 20 | SIGPIPE 应安静退出 | 已修复（实测退出 0） |

### 3.2 一般违规（审计时 20 项，整改后 2）

| ID | 条款 | 当前实现（审计时） | 偏差 | 状态 |
| --- | --- | --- | --- | --- |
| G-01 | PRD §4.6 | `characters list` 仅 NAME/LANG/VER/KIND | 缺“参考音频/磁盘占用”两列 | 已修复 |
| G-02 | PRD §4.1 | `characters list/show --json` 使用 `indent=2` | `--json` 不应换行美化 | 已修复 |
| G-03 | PRD §4.6 规则 4 | `<3s` 参考音频被 `UsageError` 拒绝 | 应仅警告，>20s 才拒绝 | 已修复 |
| G-04 | PRD §4.6 规则 3 | `--version` 与文件推断冲突时未告警 | 应以文件为准并告警 | 已修复 |
| G-05 | PRD §4.4 第 7 项 | doctor 只查角色模型目录是否存在 | 未校验 7/9 个必需文件 | 已修复 |
| G-06 | PRD §4.4 第 8 项 | doctor 只查参考音频存在 | 未校验可解码与 3–15s | 已修复 |
| G-07 | PRD §4.4 | 每项给 fix，但末尾无汇总“一键修复命令” | 缺少汇总清单 | 已修复 |
| G-08 | 补充规格 §D | `init.py` 重复硬编码 `GENIE_DATA_REQUIRED` | 违反 verify.py 单一来源 | 已修复（从 registry 导入） |
| G-09 | PRD §6.2 | `init` 自行实现 snapshot_download | 绕过 download 层；缺 max_workers/断点参数 | 已修复 |
| G-10 | PRD §4.7 | `--mirror` 缺省时不读取 `config network.hf_endpoint` | 镜像配置不生效 | 已修复 |
| G-11 | PRD §4.5 规则 4 | 显式 `-o file.wav` 已存在时不处理 `--if-exists` | 仅目录模式生效 | 已修复 |
| G-12 | PRD §4.5 规则 1 | 同时给位置参数与 `-f` 时，`-f` 覆盖位置参数 | 位置参数应优先 | 已修复 |
| G-13 | PRD §4.5 规则 8 | 文本 >2000 字无提示 | 缺少分段建议 | 已修复 |
| G-14 | PRD §4.5 | `say --yes` 参数未使用 | 首用下载确认需它 | 已修复 |
| G-15 | PRD §4.1 | 无全局 `--quiet` / `--no-color` | 缺少全局约定 | 已修复 |
| G-16 | PRD §7 | 无日志落盘实现 | 日志路径/轮转/脱敏缺失 | 已修复（`core/log.py`） |
| G-17 | PRD §6.5 | 缺 `__main__.py`、`context.py`、`download/presets.py`、根 `LICENSE` | 文件级目录结构不完整 | 已修复 |
| G-18 | rules §3 | `ruff check src tests` 134 错误（S101 等） | 质量门禁基线不通过 | 已修复（tests 规则豁免） |
| G-19 | PRD §11 | 仅 `M0-install-feasibility.yml`，缺 test/arm64/macos/release | CI 矩阵与发布流水线缺失 | **待办（M4）** |
| G-20 | PRD §2.4/§6.10 | `genie-term --help` 实测 0.48–0.56s（P95 目标 ≤0.4s） | 冷启动超目标 | **待办（性能优化）** |

### 3.3 轻微建议（6 项）

| ID | 条款 | 说明 | 状态 |
| --- | --- | --- | --- |
| M-01 | PRD §6.5 | 未创建 `core/models.py`、`core/render.py`、`core/chunker.py` | 保留：当前无 dataclass/render/P2 需求，提前建文件属过度设计；chunker 属 P2 |
| M-02 | PRD §4.4 | “GenieData 12 项必需文件”与 §6.6 的 6 个资源/9 个模型文件表述不一致 | 以 §6.6 清单为单一来源，doctor 动态显示实际项数 |
| M-03 | PRD §6.11 | 播放链实现为“自定义 sounddevice 封装 → 外部播放器”，而非字面调用上游 `play=True` | 行为等价；保留以可控失败检测 |
| M-04 | PRD §4.9 | `serve --preload` 只加载角色，未显式设置参考音频 | 需真实上游 API 行为验证（M4 E2E） |
| M-05 | PRD §7 | 错误输出用 `[错误] message` 承载“原因”，未单列“原因:”标签 | 语义完整，格式可再对齐示例 |
| M-06 | PRD §11 | 版本仍为 `0.0.1a0`，CHANGELOG 的 Unreleased 链接为示例域名 | 发布阶段统一处理 |

---

## 4. 残余风险与整改建议

1. **CI 工作流（P1，M4）**：补 `.github/workflows/test.yml`（py3.10/3.11/3.12 × ubuntu/macos + ruff + pip-audit + help 快照）、`arm64.yml`、`macos.yml`、`release.yml`（tag → PyPI Trusted Publishing）。
2. **冷启动性能（P1）**：typer 0.29 自身导入约 0.30s，当前 `--help` 0.48s。建议在 M4 用 hyperfine 在目标机器复测；若仍超标，可评估把 `commands/*` 注册改为惰性命令组，或把 `rich_markup_mode` 降级。
3. **真实联网 E2E（P0 发布门）**：`init` 391MB、`download character feibi` 230MB、`say` 首声必须在干净容器/真机跑通；离线测试无法证明 HF 仓库路径与 `prompt_wav.json` 实际结构。
4. **HF glob 语义**：`CharacterModels/**/{name}/**` 需在真实仓库验证；若 HF 不支持该组合，改为 `CharacterModels/*/{name}/*`。
5. **doctor 12 项口径**：建议 PRD 侧澄清“12 项”是资源项还是文件项；代码继续以 §6.6 为单一来源。
6. **`core/models.py` 等预留文件**：不建议为空文件而建；等 P2 功能（chunker/render）落地时再引入。

---

## 5. 整改落地清单（文件级）

| 文件 | 变更 |
| --- | --- |
| [cli.py](file:///home/neurosamalover/Documents/Projects/pys/genie-term/src/genie_term/cli.py) | 全局 `--quiet/--no-color/--offline`；typer 内置 click 用法错误→2；Abort→130；BrokenPipe 安静退出 |
| [context.py](file:///home/neurosamalover/Documents/Projects/pys/genie-term/src/genie_term/context.py) | 新增：全局运行时选项与 `is_offline` |
| [commands/say.py](file:///home/neurosamalover/Documents/Projects/pys/genie-term/src/genie_term/commands/say.py) | 数据目录优先级、播放判定、文本优先级、if-exists、JSON 字段、首用下载、GenieData 预检、日志 |
| [commands/characters.py](file:///home/neurosamalover/Documents/Projects/pys/genie-term/src/genie_term/commands/characters.py) | list 列、紧凑 JSON、时长警告、版本冲突告警、非 TTY purge 守卫 |
| [commands/init.py](file:///home/neurosamalover/Documents/Projects/pys/genie-term/src/genie_term/commands/init.py) | `--offline`、单一清单、复用 download 层、config endpoint |
| [commands/download.py](file:///home/neurosamalover/Documents/Projects/pys/genie-term/src/genie_term/commands/download.py) | `--offline`、endpoint、presets 自动注册、统一确认 |
| [commands/convert.py](file:///home/neurosamalover/Documents/Projects/pys/genie-term/src/genie_term/commands/convert.py) | 真正注册、prompt 参数、按版本校验 7/9 文件、Ctrl-C 清理 |
| [commands/serve.py](file:///home/neurosamalover/Documents/Projects/pys/genie-term/src/genie_term/commands/serve.py) | `--json`、非交互公开监听提示 |
| [commands/doctor.py](file:///home/neurosamalover/Documents/Projects/pys/genie-term/src/genie_term/commands/doctor.py) | 模型文件校验、参考音频时长、一键修复汇总 |
| [core/audio.py](file:///home/neurosamalover/Documents/Projects/pys/genie-term/src/genie_term/core/audio.py) | `inspect_prompt_audio`：错误/警告分级 |
| [core/config.py](file:///home/neurosamalover/Documents/Projects/pys/genie-term/src/genie_term/core/config.py) | `effective_data_dir` 优先级修正 |
| [core/log.py](file:///home/neurosamalover/Documents/Projects/pys/genie-term/src/genie_term/core/log.py) | 新增：按天轮转 7 天、文本指纹 |
| [download/genie_data.py](file:///home/neurosamalover/Documents/Projects/pys/genie-term/src/genie_term/download/genie_data.py) | hf 2.x 参数、RoBERTa 目录、endpoint 前置 |
| [download/presets.py](file:///home/neurosamalover/Documents/Projects/pys/genie-term/src/genie_term/download/presets.py) | 新增：预置角色元数据/别名/自动注册（tts_models） |
| [engine/adapter.py](file:///home/neurosamalover/Documents/Projects/pys/genie-term/src/genie_term/engine/adapter.py) | 导入前校验 GenieData 完整性 |
| [__main__.py](file:///home/neurosamalover/Documents/Projects/pys/genie-term/src/genie_term/__main__.py) | 新增：`python -m genie_term` |
| [pyproject.toml](file:///home/neurosamalover/Documents/Projects/pys/genie-term/pyproject.toml) | license/readme/urls；tests lint 豁免 |
| [LICENSE](file:///home/neurosamalover/Documents/Projects/pys/genie-term/LICENSE) | 新增 MIT |
| [README.md](file:///home/neurosamalover/Documents/Projects/pys/genie-term/README.md) / [CHANGELOG.md](file:///home/neurosamalover/Documents/Projects/pys/genie-term/CHANGELOG.md) | 移除不存在的 `play` 命令与 400ms 声明；补全局选项/convert 注册/serve --json |

---

## 6. 验证证据（本次会话实跑）

```text
$ pytest -m "not network" -q
81 passed in 3.49s

$ ruff check src tests
All checks passed!

$ genie-term say --bad                                  # 修复前 20
[错误] No such option: --bad
  下一步: genie-term --help ...
exit=2

$ genie-term nope                                       # 修复前 20
[错误] No such command 'nope'.
exit=2

$ genie-term say -c nope "hi"
exit=2（角色不存在）

$ genie-term say </dev/null
exit=2（没有收到文本）

$ genie-term completion bash | head -1
# genie-term bash completion
pipe_exit=0（SIGPIPE 不崩）

$ GENIE_TERM_DATA_DIR=... genie-term init --offline --yes
[1/7]…[7/7] 全部通过；写 config.toml；exit=0

$ genie-term doctor --json --no-network
{"checks":[...11 项...],"summary":{"ok":9,"warn":2,"error":0},"exit_code":0}

$ genie-term characters list --json
{}（紧凑单行）

$ genie-term --help   # 3 次热启动
0.48s / 0.48s / 0.53s（目标 ≤0.4s，仍待优化）
```

离线集成测试新增覆盖：
- `test_say.py`：播放开关、`--if-exists`、位置参数优先、JSON 字段、`load → set_ref → tts` 顺序；
- `test_presets.py`：别名归一化、`tts_models` 定位、预置角色记录构造。

---

## 7. 补充规格（A–M 节）覆盖说明

| 补充规格节 | 核对结果 |
| --- | --- |
| A 量化验收线 | 安装成功率/首声时间需真实环境；帮助可读性、冷启动见第 4 节 |
| B 非目标/V1 范围 | 未越界实现 P2（read、mp3、SRT、语速音调） |
| C.1–C.10 命令规格 | 逐条对照，S/G 级偏差已修复 |
| D 数据布局与必需文件 | `core/registry.py` 单一来源；init/doctor/verify 复用 |
| E config/registry Schema | 字段、默认值、schema 版本拒绝均符合 |
| F 上游函数签名 | adapter 全部覆盖 |
| G 六陷阱 | 全部有对应实现 |
| H 可复制命令 | README 已修正 `play`/`init --offline`/convert 注册示例 |
| I 音频策略 | 先落盘、播放失败不影响退出码 |
| J 错误与诊断 | 四要素格式；日志脱敏 |
| K 坏环境矩阵 | 无 gcc/无音频/只读 HOME/中文路径/SIGPIPE 中，SIGPIPE 已实测；其余待 M4 |
| L 发布检查清单 9 项 | 未开始（M4） |
| M 命令速查表 | 与 README 一致 |

---

## 8. 审计结论

- **红线**：`.trae/rules/project_rules.md §4` 12 条全部通过，唯一 import 点、原子写、退出码、非交互约束均已落实。
- **主路径**：`init → download character → say → doctor` 的代码链路已按 PRD 修正，离线测试可证流程与参数契约；真实联网首声仍需 M4 验证。
- **发布就绪度**：代码层达到 **86/100**；阻塞发布的是 CI 流水线、真实 E2E 与冷启动性能，而非功能正确性。
