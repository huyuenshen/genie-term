# genie-term 架构说明

> 本文档描述 genie-term 的分层架构、数据流、红线约束与上游集成策略。
> 需求唯一真相源是 `docs/PRD.md`（v1.2 Unix 版）；本文件与 PRD 冲突时以 PRD 为准。

---

## 1. 分层总览

```
┌─────────────────────────────────────────────────────┐
│  cli.py          typer 装配 + 异常→退出码映射         │  ← 不 import genie_tts
├─────────────────────────────────────────────────────┤
│  commands/       9 个子命令组（业务编排）              │  ← 不 import genie_tts
│  core/           config / registry / audio / player  │  ← 不 import genie_tts
│  download/       genie_data / verify                 │  ← 不 import genie_tts
├─────────────────────────────────────────────────────┤
│  engine/
│  ├── bootstrap.py   env 注入（GENIE_DATA_DIR 等）    │  ← 不 import genie_tts
│  └── adapter.py     ⚠ 全项目唯一 import genie_tts    │
├─────────────────────────────────────────────────────┤
│  genie-tts-unix==2.0.2（受控 fork，vendor/ 内有源码）  │
└─────────────────────────────────────────────────────┘
```

**分层规则**（违反即评审打回）：

1. 只有 `engine/adapter.py` 可以 `import genie_tts`。上游 API 变更只改这一个文件。
2. `cli.py` 顶层禁止 import onnxruntime/genie_tts——否则 `genie-term --help` 冷启动超 400ms（PRD §2.4 验收线）。
3. 路径一律经 `core/paths.py`（platformdirs）解析，禁止硬编码 `~/.local/...`。

---

## 2. 模块职责

| 模块 | 职责 | 关键 API |
|------|------|----------|
| `cli.py` | typer 装配、命令分发、异常→退出码映射 | `main()` |
| `errors.py` | 7 种异常类 + 退出码常量 + 映射表 | `exception_to_exit_code()` |
| `core/paths.py` | platformdirs 目录解析（XDG / ~/Library） | `resolve_data_dir()` 等 |
| `core/config.py` | config.toml 读写、校验、原子写（.bak + os.replace） | `Config.load/set/save` |
| `core/registry.py` | 角色注册表读写、model_version 自动推断、必需文件清单 | `load_registry()` |
| `core/audio.py` | 参考音频校验、产物 >1KB 验证、时长探测 | `verify_product_or_raise()` |
| `core/player.py` | 播放策略链 sounddevice→afplay→ffplay→paplay→aplay | `play()` |
| `engine/bootstrap.py` | env 注入（进程内仅一次）、离线开关 | `ensure_env()` |
| `engine/adapter.py` | 唯一上游接触点：加载/参考音频/合成/转换/服务 | `synth()` 等 |
| `download/genie_data.py` | snapshot_download 绝对目录下载 | `download_genie_data()` |
| `download/verify.py` | GenieData 必需文件校验 | — |
| `commands/*.py` | 9 个子命令组的参数解析与业务编排 | — |

---

## 3. 关键数据流

### 3.1 say 合成流程

```
genie-term say "文本" -c feibi
  │
  ├─ cli.main() → typer 分发 → commands/say.py
  ├─ 文本来源解析: 位置参数 > -f FILE > stdin（三者全空 → UsageError, 码 2）
  ├─ Config.load() 读 general.default_character / play / if_exists
  ├─ Registry.get(char) → 角色不存在 → UsageError(码 2)
  ├─ 模型目录 / 参考音频存在性检查 → EnvError(码 10)
  ├─ engine.bootstrap.ensure_env()     ← GENIE_DATA_DIR 注入（仅一次）
  ├─ engine.adapter.synth()
  │    ├─ genie_tts.tts(name, text, play=False, save_path=...)
  │    └─ core.audio.verify_product_or_raise()  ← 产物 >1KB，否则 EngineError(码 20)
  ├─ 可选播放（core/player.py 策略链；失败只警告，不改退出码）
  └─ --json: stdout 仅一个 JSON 对象；进度/警告全走 stderr
```

### 3.2 download 流程

```
genie-term download genie-data
  ├─ 非交互无 --yes → UsageError(码 2)
  ├─ download/genie_data.py:
  │    ├─ HF_ENDPOINT 在 import huggingface_hub 之前设置
  │    └─ snapshot_download(repo_id="High-Logic/Genie",
  │                          allow_patterns="GenieData/**",
  │                          local_dir=<绝对目录>)
  ├─ 失败 → NetworkError(码 11) + hf-mirror 修复命令
  └─ download character → 下载后解析 prompt_wav.json 自动注册到 registry
```

### 3.3 异常→退出码映射

```
try:
    app(standalone_mode=False)        # cli.py main()
except typer.Exit as e:        → sys.exit(e.exit_code)
except KeyboardInterrupt:      → 130
except GenieTermError as e:    → sys.exit(e.code)   # UsageError=2 / EnvError=10 /
                               #   NetworkError=11 / PlaybackError=12 /
                               #   EngineError=20 / MissingTorchError=21
except Exception:              → 20（GENIE_TERM_DEBUG=1 才打印堆栈）
```

---

## 4. 上游六大陷阱与对策

上游 `genie-tts 2.0.2` 有六个已知陷阱，对策逐条落在 `engine/adapter.py` 与 `download/genie_data.py`：

| # | 陷阱 | 对策 | 落点 |
|---|------|------|------|
| 1 | `GENIE_DATA_DIR` 在 `Core/Resources.py` **模块导入时**读取固化，事后设置无效 | `bootstrap.ensure_env()` 在 import 前注入，进程内仅一次（幂等哨兵） | `engine/bootstrap.py` |
| 2 | 数据目录不存在时导入期执行 `input("是否下载…")`，非 TTY 挂起/EOFError | import 前先检查 `resolve_data_dir().exists()`，不存在就不 import，由我们先报错 | `adapter.check_genie_tts()` |
| 3 | `download_genie_data()` 用 `local_dir="."` 污染 CWD，且 pattern 只匹配一层 | 禁用该 API，自写 `snapshot_download` 到绝对目录，pattern 用 `GenieData/**` | `download/genie_data.py` |
| 4 | `load_predefined_character()` 把模型下到相对路径 `./CharacterModels/` | `_temporary_chdir` 上下文管理器临时 chdir 到 data_dir，异常也恢复 | `adapter.py` |
| 5 | `tts()` 缺参考音频时只 `logger.error` 后 return，退出码仍 0、无产物 | 合成后强制校验产物存在且 >1KB，否则 `EngineError`（码 20） | `adapter.synth()` + `core/audio.py` |
| 6 | 文档提到的 `download_roberta_data()` 在 2.0.2 未导出，调用即 AttributeError | 自实现 `snapshot_download(repo, "GenieData/RoBERTa/**")`；仓库无此路径则静默降级（可选组件） | `download/genie_data.py` |

---

## 5. 受控 fork（genie-tts-unix）

上游 PyPI 包 `genie-tts==2.0.2` 有两个**安装阻塞**，fork 仅改依赖声明、核心 TTS 逻辑零改动：

| 问题 | fork 修改 |
|------|-----------|
| `jieba_fast` 仅 sdist，需要 gcc/clang（干净容器/无 Xcode CLT 装不上） | 替换为纯 Python `jieba`（多平台 wheel） |
| `onnxruntime==1.22.1` 已从 PyPI 下架 | 放宽为 `onnxruntime>=1.16,<2` |

fork 源码在 `vendor/genie-tts-unix/`，以 `genie-tts-unix==2.0.2` 发布。升级 fork 必须重跑全部离线测试 + 真机首声回归。

---

## 6. 数据布局与路径解析

所有路径经 `core/paths.py` → `platformdirs` 解析，可用环境变量覆盖（优先级：CLI 参数 > 环境变量 > 平台默认）：

| 用途 | Linux (XDG) | macOS | 环境变量 |
|------|-------------|-------|----------|
| config.toml | `~/.config/genie-term/` | `~/Library/Application Support/genie-term/` | `GENIE_TERM_CONFIG_DIR` |
| GenieData / CharacterModels / registry.toml | `~/.local/share/genie-term/` | `~/Library/Application Support/genie-term/` | `GENIE_TERM_DATA_DIR` |
| 日志 | `~/.local/state/genie-term/logs/` | `~/Library/Logs/genie-term/` | `GENIE_TERM_LOG_DIR` |
| 缓存/临时 | `~/.cache/genie-term/tmp/` | `~/Library/Caches/genie-term/` | `GENIE_TERM_CACHE_DIR` |

**必需文件清单**（`core/registry.py` 单一来源，`doctor`/`verify.py` 共用）：

- 基线 7 个：`t2s_encoder_fp32.bin/.onnx`、`t2s_first_stage_decoder_fp32.onnx`、`t2s_shared_fp16.bin`、`t2s_stage_decoder_fp32.onnx`、`vits_fp16.bin`、`vits_fp32.onnx`
- v2ProPlus 追加 2 个：`prompt_encoder_fp16.bin`、`prompt_encoder_fp32.onnx`

`model_version` 自动推断规则：模型目录存在 `prompt_encoder_fp32.onnx` → `v2ProPlus`，否则 `v2`；与 `--version` 冲突时以文件为准并告警。

---

## 7. 并发与进程模型

- **CLI 短生命周期**：每次命令独立进程，合成走进程内直调；不支持并行跑多个 `say`（上游单进程全局单例，CPU 争抢）。
- **serve 长驻**：`genie-term serve` 调上游 `start_server(host, port, workers)`；`--workers` 上限 1（多 worker 只增内存不增吞吐）。默认只听 `127.0.0.1`；`--host 0.0.0.0` 必须 `--allow-public` + TTY 二次确认，否则退出码 2。上游 API **无鉴权**，不要裸奔公网。

---

## 8. 测试策略

红线：测试不得真实联网、不得真实加载模型。

```
tests/
├── conftest.py           isolated_env（临时目录覆盖 platformdirs）/ fake_model_dir / fake_wav
├── unit/                 errors / config / registry / audio（67 个用例）
└── integration/test_cli.py
                          CliRunner 端到端：退出码契约、非交互 --yes、
                          0.0.0.0 拒绝、workers 上限、completion 输出、
                          红线断言（adapter.py 外无 genie_tts import）
```

运行：`pip install -e ".[dev]" && pytest -m "not network"`；lint：`ruff check src`（CI 必须全绿）。
