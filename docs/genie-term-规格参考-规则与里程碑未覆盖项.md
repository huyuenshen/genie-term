> 本文件收录 **.trae/rules/project_rules.md（红线/约束）** 和 **docs/milestones/ 下的 M0–M4 任务清单（执行步骤）** 都没有完整写进、但 Agent 落地代码时必须照着做的「规格细节」。唯一真相源仍是 `docs/genie-term-PRD-v1.2-Unix版.docx`（v1.2 Unix 版），本文件只是把它对 Agent 最有用、且前两份文件没展开的部分汇总成一张「照着抄」的参考表。
> 用法：与 `.trae/rules/project_rules.md` + `docs/milestones/` 中对应里程碑文件一起交给 TRAE SOLO Agent。写某个命令前，先回本文件查它的完整参数、JSON、异常表，避免凭记忆补错。

---

## A. V1 量化验收线（PRD §2.4）—— M4 性能/发布任务的判定基准
| 指标 | 目标 | 测量方式 |
| --- | --- | --- |
| 安装成功率 | 干净 Ubuntu 24.04（无 gcc）与干净 macOS（无 Xcode CLT）均 ≥95% | 发布前 10 次全新容器 + 若干 macOS 真机安装 |
| 首声时间 | ≤10 分钟（百兆带宽，含 391MB + 单角色 230MB） | 计时脚本 |
| 命令成功率 | 首声路径 3 条命令一次成功 ≥90% | 5 名目标用户可用性测试 |
| 帮助可读性 | 每个子命令 `-h` 至少 2 个可直接复制的示例 | CI 快照测试 |
| 冷启动 | `genie-term --help` P95 ≤400ms | hyperfine |

> 注：首声 ≤10 分钟是对**终端用户**的指标，不是开发工期。开发侧不设工期。

## B. 非目标 & V1 明确不做（PRD §2.5 / §3）—— 防止 Agent 越界加功能
- **永久非目标**：GUI/TUI 播放器、模型训练、内置模型权重、云端 TTS、Windows 支持、非主线的其余 Unix-like（BSD/Solaris 等）、多用户/多租户。
- **目标平台（V1 主线）**：面向所有 Unix-like，先落地 Linux（Ubuntu/Debian/Fedora/Arch）与 macOS（Apple Silicon + Intel）；BSD/Solaris 后续按需扩展。
- **P2（V1 不做，别在 M0–M4 里实现）**：批量任务队列、SRT 字幕输出、`--lang en` 界面本地化、社区角色包、语速/音调参数、`read`（长文流式）命令、`--format mp3`（运行时探测 ffmpeg 才支持）。
- **P1 已确认进 V1**：convert、serve、config、shell completion、镜像源、离线模式。
- **交互式 REPL 不做**。

## C. 完整命令规格（PRD §4）—— 写 commands/*.py 时照此实现参数与行为

### C.1 全局约定（§4.1）
- **输出分流**：stdout 只放结果（路径、JSON、表格）；进度条/警告/日志一律 stderr。
- **`--json`**：stdout 恰好一个 JSON 对象；不换行美化；字段 snake_case；路径为绝对路径。
- **`--quiet`**：抑制 stderr 的进度与提示，仅保留错误。
- **`--yes`**：跳过所有交互确认（下载、覆盖、0.0.0.0 监听）。
- **`--offline`**：禁止任何网络请求；缺失资源直接报错并给手动放置路径。
- **`--no-color`**：同时尊重 `NO_COLOR` 与 `TERM=dumb`。
- **非 TTY**：不提问；需要确认时退出码 2 并打印带 `--yes` 的完整命令。
- **Ctrl-C**：清理临时文件，退出码 130，不打印 traceback。
- **参数优先级**：CLI > 环境变量 > config.toml > 内置默认。

**退出码（写死，不可漂移）**：`0` 成功 / `2` 用法·参数·需确认但非交互 / `10` 环境缺失（数据、模型、系统库、Python 版本）/ `11` 网络失败（HF/镜像不可达、下载中断）/ `12` 播放失败（仅影响 `--play`，合成成功仍返回 0）/ `20` 引擎内部错误 / `21` 缺少 torch（仅 convert）/ `130` 用户中断。

### C.2 命令树（§4.2）
```
genie-term init / doctor / say [TEXT]
genie-term characters list|show|add|use|remove
genie-term download genie-data|character|roberta
genie-term convert            # 需 [convert]
genie-term serve
genie-term config show|get|set|reset|path
genie-term completion bash|zsh|fish
genie-term version
```

### C.3 init（§4.3）
`genie-term init [--yes] [--mirror URL] [--data-dir PATH] [--force]`
顺序（每步失败立即停止并给下一步）：1 解析数据目录（`--data-dir > GENIE_TERM_DATA_DIR > 平台默认，经 platformdirs：Linux XDG / macOS `~/Library`）→ 2 检查 Python 版本与关键依赖可导入（不 import genie_tts）→ 3 磁盘剩余 ≥2GB 否则警告（不阻塞）→ 4 下载 GenieData 391MB（进度/断点续传/可重试）→ 5 校验必需清单（缺一项即列文件名）→ 6 写 config.toml（已存在不覆盖，除非 `--force`）→ 7 打印下一步 `genie-term say -c feibi "你好"`。幂等：重复只校验；`--force` 才重下。

### C.4 doctor（§4.4）
`genie-term doctor [--json] [--network/--no-network]`。✔/⚠/✘ 三级 + 末尾一键修复命令；**有 ✘ → 码 10，仅 ⚠ → 码 0**。12 项检查（每项修复命令按平台给：Linux 的 apt/dnf/pacman、macOS 的 brew）：
1 Python 3.10–3.12（✘，3.13 标 ⚠ 实验性）·2 依赖完整性 onnxruntime 可 import（✘，pipx reinstall）·3 是否 root 运行（⚠）·4 GenieData 12 项必需文件（✘，genie-term init）·5 中文 RoBERTa 可选（⚠，download roberta）·6 注册表可读/schema 版本（✘，备份+config reset）·7 已注册角色模型目录与必需文件（✘）·8 参考音频存在可解码 3–15s（✘，重新 add）·9 音频输出设备（Linux /dev/snd 或 PULSE_SERVER；macOS CoreAudio 可用输出设备）（⚠）·10 播放器（macOS afplay/ffplay；Linux ffplay/paplay/aplay）（⚠）·11 磁盘 ≥2GB（⚠）·12 HF 端点连通 5s 超时（✘，可 --no-network 跳过）。
`--json`：`{"checks":[{"id":"python","level":"ok","message":"...","fix":null}],"summary":{"ok":10,"warn":2,"error":0},"exit_code":0}`

### C.5 say（§4.5）
```
genie-term say [TEXT] [-c NAME] [-l zh|en|jp] [-o PATH] [-f FILE]
               [--play/--no-play] [--split-sentence/--no-split]
               [--if-exists overwrite|skip|timestamp|fail] [--json] [--yes]
```
规则：文本来源 位置参数 > `-f` > stdin（非 TTY 且非空），三者全空→码 2；未指定 `-c` 用 `general.default_character`，仍空→码 2 并列出可用角色；语言优先级 `-l` > 角色语言 > 配置默认，上游只支持 zh/en/jp，其他语言在**注册阶段**拒绝；`-o` 是目录则自动命名，缺省 `output_dir/genie_<角色>_<YYYYmmdd-HHMMSS>.wav`，已存在按 `--if-exists`（默认 overwrite）；`--play` 默认：交互式 TTY 且检测到播放器才开，播放链 sounddevice（macOS 走 CoreAudio、Linux 走 ALSA/Pulse）→afplay(macOS 自带)→ffplay→paplay→aplay→仅存盘，命中即止（Windows 不在主线）；播放失败不改退出码（仍 0）；首次用某角色模型未下载时 TTY 询问「需下载约 230MB」，非 TTY 无 --yes→码 10；**产物校验：合成后确认文件存在且 >1KB，否则视为引擎失败（码 20）**；长文本 V1 不在 CLI 切分（交上游 split_sentence=True），>2000 字提示改用 read（未上线则提示分段）。
异常表：角色不存在→码 2；参考音频丢失→码 10；模型目录缺文件→码 10；输入为空→码 2；引擎异常→码 20（附 doctor + 日志路径）。

### C.6 characters（§4.6）
`list [--json]`（名称/语言/模型版本/来源/参考音频/磁盘占用）·`show NAME [--json]`·`add NAME --model-dir DIR --lang zh|en|jp [--prompt-wav F --prompt-text T] [--version v2|v2ProPlus] [--force]`·`use NAME`·`remove NAME [--purge] [--yes]`（默认只删注册，`--purge` 才删模型目录，需二次确认）。
**add 注册校验（写库前）**：① `--model-dir` 存在且转绝对路径；② 必需文件齐全（见 D 节），缺则拒绝列出；③ model_version 自动推断（有 `prompt_encoder_fp32.onnx`→v2ProPlus，否则 v2，与 `--version` 冲突以文件为准并告警）；④ **参考音频必填成对**（`--prompt-wav` 与 `--prompt-text`），扩展名限 `.wav/.flac/.ogg/.aiff/.aif`，时长 3–15s 最佳（<3s 警告，>20s 拒绝）；⑤ 写入「读→.bak→临时文件→os.replace」。预置角色 feibi/mika/thirtyseven 由 download character 注册，自带 prompt_wav.json，无需用户提供。

### C.7 download（§4.7）
`genie-data [--mirror URL] [--yes]`（391MB）·`character NAME [--yes]`（预置角色约 230MB 并注册）·`roberta [--yes]`（可选中文韵律，**2.0.2 未导出 download_roberta_data，必须自实现**）。约束：不用上游 `download_genie_data()`（写 CWD），改 `huggingface_hub.snapshot_download` 指定绝对目录；`HF_ENDPOINT` 必须在 import huggingface_hub **之前**设；`--offline` 只校验并打印手动放置路径；失败（DNS/403/超时/磁盘满）统一码 11，错误带镜像命令 `genie-term config set network.hf_endpoint https://hf-mirror.com`。

### C.8 convert（§4.8）
`genie-term convert --pth a.pth --ckpt a.ckpt [--version v2|v2ProPlus] --name NAME [--out DIR] [--register/--no-register] [--json]`
缺 torch→码 21，**只给一条**正确命令：`pipx inject genie-term torch --index-url https://download.pytorch.org/whl/cpu`（v1.0 的 `genie-term[convert]` 语法是错的）。流程：校验输入→建输出临时目录→`genie_tts.convert_to_onnx()`→校验产物 9 个文件→原子改名→询问是否注册（非交互需 `--register`）；失败清临时+码 20。

### C.9 serve（§4.9）
`genie-term serve [--host 127.0.0.1] [--port 8000] [--workers 1] [--preload NAME] [--allow-public] [--json]`。默认只监听 127.0.0.1；`--host 0.0.0.0` 必须配 `--allow-public` 且 TTY 二次确认，否则码 2；`--workers` 上限 1（上游进程内全局单例，多 worker 只增内存不增吞吐）；上游 API **无鉴权**，README 明示「不要裸奔公网」。

### C.10 config / completion / version（§4.10）
`config show|get KEY|set KEY VALUE|reset --yes|path`；`completion bash|zsh|fish` 输出脚本（README 给 `source <(genie-term completion bash)`）；`version [--json]` 打印 genie-term/genie-tts/onnxruntime/Python/平台。

## D. 数据布局与必需文件清单（PRD §6.6）—— verify.py 的单一来源
目录（下列为 Linux/XDG 路径；macOS 经 platformdirs 映射到 `~/Library/Application Support/genie-term`（数据/配置）、`~/Library/Logs/genie-term`（日志）、`~/Library/Caches/genie-term`（缓存），结构与下列同构）：
```
~/.config/genie-term/config.toml
~/.local/share/genie-term/GenieData/        # 391MB
├── chinese-hubert-base/  speaker_encoder.onnx
├── G2P/ChineseG2P/  G2P/EnglishG2P/
├── v2/{Models}  v2ProPlus/{Models}
└── RoBERTa/                                # 可选
~/.local/share/genie-term/CharacterModels/{v2,v2ProPlus}/<name>/tts_models/
~/.local/state/genie-term/logs/genie-term.log
~/.cache/genie-term/tmp/
```
**模型目录必需文件（verify.py 单一来源，共 12 项）**：
- 基线 7 个：`t2s_encoder_fp32.bin`、`t2s_encoder_fp32.onnx`、`t2s_first_stage_decoder_fp32.onnx`、`t2s_shared_fp16.bin`、`t2s_stage_decoder_fp32.onnx`、`vits_fp16.bin`、`vits_fp32.onnx`
- v2ProPlus 追加 2 个：`prompt_encoder_fp16.bin`、`prompt_encoder_fp32.onnx`
- doctor §4.4 第 4 项「GenieData 12 项必需文件」即按此清单校验。

## E. 配置与注册表完整 Schema（PRD §6.7）—— config.py / registry.py 默认值
> 下方示例为 Linux 绝对路径；macOS 经 platformdirs 形如 `/Users/<u>/Library/Application Support/genie-term/...`，`output_dir = "~/Music/genie-term"` 两平台通用。
```toml
# ~/.config/genie-term/config.toml
schema_version = 1
[general]
default_character = "feibi"
default_language  = "zh"          # zh|en|jp
output_dir        = "~/Music/genie-term"
play              = "auto"        # auto|always|never
if_exists         = "overwrite"   # overwrite|skip|timestamp|fail
[engine]
data_dir = ""                     # 空=XDG 默认
threads  = 0                      # 0=自动
[network]
hf_endpoint = "https://huggingface.co"
offline     = false
[server]
host = "127.0.0.1"
port = 8000
```
```toml
# ~/.local/share/genie-term/registry.toml
schema_version = 1
[characters.feibi]
kind = "preset"                   # preset|local|converted
language = "zh"
model_version = "v2ProPlus"
model_dir = "/home/u/.local/share/genie-term/CharacterModels/v2ProPlus/feibi/tts_models"
prompt_wav  = "/home/u/.local/share/genie-term/CharacterModels/v2ProPlus/feibi/prompt_wav/zh_....wav"
prompt_text = "参考音频文本"
created_at = "2026-11-18T20:12:33+08:00"
genie_term_version = "1.1.0"
```
规则：`prompt_wav/prompt_text` 对**所有 kind 均必填**（preset 由下载器从 prompt_wav.json 填充）；读到更高 schema_version 时拒绝写入并提示升级。

## F. 上游集成契约函数签名（PRD §6.3）—— adapter.py 只能调这些
| 能力 | 上游函数 | 关键参数 |
| --- | --- | --- |
| 加载本地模型 | `load_character(character_name, onnx_model_dir, language)` | language ∈ Chinese/English/Japanese（zh/en/jp 归一化） |
| 加载预置角色 | `load_predefined_character(name)` | 别名 feibi/菲比、mika/未花、37/thirtyseven |
| 设置参考音频 | `set_reference_audio(character_name, audio_path, audio_text, language=None)` | 仅 `.wav/.flac/.ogg/.aiff/.aif` |
| 合成 | `tts(character_name, text, play=False, split_sentence=True, save_path=None)` | 同步阻塞，**无返回值**，必须自校验产物 |
| 流式合成 | `tts_async(...) → AsyncIterator[bytes]` | 32kHz/16bit/mono，**V1 不使用** |
| 卸载 | `unload_character(name)` | 进程内单例，CLI 短生命周期可不用 |
| 模型转换 | `convert_to_onnx(torch_pth_path, torch_ckpt_path, output_dir)` | 仅 V2/V2ProPlus，需 torch |
| HTTP 服务 | `start_server(host, port, workers)` | 上游 FastAPI，无鉴权，workers 建议 1 |

## G. 上游六个陷阱与对策（PRD §6.4）—— adapter.py 注释里逐条对应
1. `GENIE_DATA_DIR` 在 `Core/Resources.py` **模块导入时**读取并固化 → 之后再设无效；env 必须在 import genie_tts 之前注入，进程内仅一次。
2. 数据目录不存在时导入阶段执行 `input("是否下载…(y/N)")` → 非 TTY 抛 EOFError/挂起；导入前保证目录与文件齐全，缺数据由我们先报错，绝不让导入发生。
3. `download_genie_data()` 用 `local_dir="."` + `allow_patterns="GenieData/*"` → 污染 CWD 且只匹配一层；自写 `snapshot_download` 到绝对路径，pattern 用 `GenieData/**`。
4. `load_predefined_character()` 把模型下到 `./CharacterModels/...` 并读 prompt_wav.json → 同样污染 CWD；在 adapter 内用上下文管理器临时 chdir 到 `<data_dir>` 再调用（异常也恢复）。
5. `tts()` 缺参考音频时只 `logger.error` 然后 return → 退出码 0、无文件；注册期强制参考音频，合成后校验产物存在且 >1KB，否则抛 EngineError。
6. README 提到的 `download_roberta_data()` 在 2.0.2 中**未导出** → 照文档调用直接 AttributeError；自实现 `snapshot_download(repo,"GenieData/RoBERTa/**")`，仓库无此路径则 V1 下线。
补充：sounddevice 导入在 TTSPlayer 内 try/except，缺 PortAudio 只关播放不影响合成——所以「无声卡」是 ⚠ 不是 ✘。

## H. 关键流程可复制命令（PRD §5）—— README / 文档 / 脚本示例直接引用
- **首次安装到第一声（§5.1）**：`sudo apt install pipx libportaudio2`（macOS：`brew install pipx`，并先 `xcode-select --install` 以便 jieba-fast 可编译）→ `pipx ensurepath && exec $SHELL -l` → `pipx install genie-term` → `genie-term init` → `genie-term say -c feibi -o hello.wav "你好，世界"`。失败分支必须首屏可见（无 gcc→§6.8 处理、HF 不通→镜像、无声卡→只出文件）。
- **使用自己的 GPT-SoVITS 模型（§5.2）**：`pipx inject genie-term torch --index-url .../cpu` → `genie-term convert --pth my.pth --ckpt my.ckpt --name myvoice --register --prompt-wav ref.wav --prompt-text "参考音频里说的那句话"` → `genie-term say -c myvoice "测试一句"`。
- **脚本化（§5.3）**：`while IFS= read -r line; do genie-term say -c feibi --json "$line" | jq -r .output; done < lines.txt`。**约束**：不要并行跑多个 say（CPU 争抢，上游也不建议），并发入口是 serve。
- **离线/内网（§5.4）**：有网机器 `init` + `download character feibi` → 打包 `<data_dir>` → 目标机解压后 `config set engine.data_dir /path/to/data` 或 `init --offline` 仅校验。

## I. 音频策略（PRD §6.11）
合成永远先落盘（wav，32kHz/16bit/mono，实际采样率以**文件探测为准**，不硬编码）。播放是可选后处理：先试上游 `play=True`（sounddevice；macOS 走 CoreAudio、Linux 走 ALSA/Pulse），失败则外部播放器（macOS 用自带 afplay，Linux 用 ffplay/paplay/aplay），全失败只警告。不引入 ffmpeg 作为硬依赖；`--format mp3` 属 P2，运行时探测 ffmpeg。

## J. 错误与诊断规范（PRD §7）—— errors.py 输出格式
统一结构（人类可读）：
```
[错误] 缺少语音资源
  位置: ~/.local/share/genie-term/GenieData
  原因: 未找到 chinese-hubert-base/
  下一步: genie-term init
  详细: GENIE_TERM_DEBUG=1 genie-term say ...（可复制）
```
规则：禁止裸 traceback（`GENIE_TERM_DEBUG=1` 才打印堆栈）；每条错误必须有一条可复制的「下一步命令」；日志写 `~/.local/state/genie-term/logs/genie-term.log`，按天轮转保留 7 天，**不记录合成文本内容**（只记长度 + 哈希前 8 位）；默认无遥测、无崩溃上报。

## K. 坏环境必测矩阵（PRD §10.2）—— M4.2 的展开清单
无 gcc（Linux）/无 Xcode CLT（macOS）、无 build-essential（安装）·无音频输出设备（Linux /dev/snd·PULSE_SERVER；macOS CoreAudio 无可用输出）（播放）·HOME 只读、磁盘剩余 <500MB（错误处理）·路径含中文与空格（`/home/用户/我的 音频/`）·HF 403/超时/DNS 失败（镜像提示）·`LC_ALL=C`、`TERM=dumb`、`COLUMNS=40`（输出）·管道被提前关闭（`| head -1`，SIGPIPE 不崩）。

## L. 发布检查清单 9 项（PRD §14）—— M4.5 的展开清单
1 干净 ubuntu:24.04（无 gcc、无音频）与干净 macOS（无 Xcode CLT）安装成功并出声；2 Ubuntu 22.04/24.04/Debian 12/Fedora 40/Arch + macOS 真机 README 复现；3 `--json` 全命令通过 jq 校验；4 无声卡机器 `--play` 降级正确、退出码 0；5 断网、403、磁盘满、只读 HOME 四种故障提示正确；6 中文/空格路径通过；7 pip-audit 无高危、wheel 元数据 Requires-Python 正确；8 卸载文档验证无残留；9 PyPI 包名与命令名一致、README 首屏可复制。

## M. 命令速查表（PRD §15.1）—— README 首屏 / completion 示例来源
```
genie-term init                                   # 一次性准备
genie-term doctor                                 # 出问题先跑这个
genie-term characters list                        # 有哪些声音
genie-term download character feibi               # 下一个预置角色
genie-term say -c feibi "你好" -o a.wav           # 合成
echo "你好" | genie-term say -c feibi --json      # 管道
genie-term characters add my --model-dir ./tts_models --lang zh \
  --prompt-wav ref.wav --prompt-text "参考文本"   # 注册本地模型
genie-term convert --pth a.pth --ckpt a.ckpt --name my --register \
  --prompt-wav ref.wav --prompt-text "参考文本"   # 转换并注册
genie-term serve --port 8000                      # 本地 API
```
