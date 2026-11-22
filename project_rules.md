# genie-term —— TRAE 项目规则

> 本文件放进仓库 `.trae/rules/project_rules.md`，TRAE SOLO Agent 每次会话自动读取。
> 这是**约束层**，不是需求全文。需求唯一真相源是 `docs/PRD.md`（即 genie-term-PRD-v1.2-Unix 版）。

## 0. 项目一句话
Unix-like 原生 GenieTTS 命令行封装（当前主线平台为 Linux 与 macOS，目标覆盖所有 Unix-like）。目标：干净 Ubuntu 24.04 或干净 macOS 上 `pipx install genie-term`，一条 `genie-term say` 出声，全程不依赖 Wine、不要求用户写 Python。安装方式仅 `pipx install genie-term`。

## 1. 技术栈（不得越界新增依赖）
- Python 3.10–3.12（3.13 实验性，不承诺）
- CLI: typer（>=0.12,<1）｜终端: rich（>=13,<15）
- 引擎: genie-tts==2.0.2（进程内直调，版本锁定，升级须过回归）
- 打包: hatchling｜配置: tomllib/tomli + tomli_w｜路径: platformdirs
- 测试: pytest>=8,<10 + CliRunner
- **禁止**引入 numpy/pandas 自建栈、音频编辑库、GUI 库；**禁止**新增 PRD §6.1 之外的依赖。

## 2. 规范入口
`docs/PRD.md` 是唯一真相源；本文件与 PRD 冲突时**以 PRD 为准**。命令规格见 PRD §4，退出码契约见 §4.1，上游陷阱见 §6.4，安装可行性见 §6.8。

## 3. 关键命令（开工/自测基线）
```bash
pip install -e ".[dev]" && pytest -m "not network"   # 安装+跑离线测试
ruff check src tests                                  # lint
pipx install --editable .                             # 本地以 pipx 链路验证
```

## 4. 红线（违反即代码评审打回，不可协商）
- 只有 `src/genie_term/engine/adapter.py` 可以 `import genie_tts`；其余任何模块出现该 import 一律退回。目的是上游 API 变更只改一个文件。
- 路径、数据/配置/日志/cache 目录一律经 `platformdirs` 解析（Linux 用 XDG、macOS 用 `~/Library`），禁止硬编码 `~/.local/...` 或 `/home/...`。
- `GENIE_DATA_DIR` / `HF_ENDPOINT` **必须**在 `import genie_tts` / `import huggingface_hub` **之前**设置，且进程内只允许一次（上游在模块导入时固化这些变量，事后设无效）。
- **禁止**调用上游 `download_genie_data()`（它 `local_dir="."` 会污染当前工作目录）；下载必须用 `snapshot_download` 指定绝对目录，pattern 用 `GenieData/**`。
- **禁止**依赖上游 `tts()` 的返回值判断成功（它缺参考音频时只打日志、return、退出码仍 0）；合成后**必须**校验产物文件存在且 >1KB，否则抛 EngineError。
- `--json` 模式 stdout **只能**有一个 JSON 对象；进度/警告/日志一律走 stderr。
- 退出码严格按 PRD §4.1（0/2/10/11/12/20/21/130），不可漂移。
- registry/config 写入：校验 → 备份 `.bak` → 临时文件 → `os.replace`（原子写）。
- **禁止** `shell=True`；外部播放器（macOS：afplay/ffplay；Linux：ffplay/paplay/aplay）用列表参数 `subprocess.run([...])`。
- 非 TTY 时**绝不提问**：需要确认（下载/覆盖/0.0.0.0 监听）而缺 `--yes` → 退出码 2 并打印带 `--yes` 的完整命令；导入阶段绝不能触发上游 `input()`（否则脚本挂起/EOFError）。
- `serve` 默认只听 `127.0.0.1`；`--host 0.0.0.0` 必须配 `--allow-public` + TTY 二次确认，否则退出码 2；上游 API 无鉴权，README 须明示「不要裸奔公网」。
- 错误信息禁止裸 traceback（除非 `GENIE_TERM_DEBUG=1`）；每条错误必须含「是什么/在哪/下一条命令」。
- 日志不记录合成文本内容（只记长度 + 哈希前 8 位）；默认无遥测、无崩溃上报。
- 不 sudo、不写 `/usr`/`/etc`、超过 100MB 的下载必须显式确认。
- **测试不得真实联网、不得真实加载模型**（用 engine_stub 断言调用顺序 load→set_ref→tts→产物校验）。

## 5. 分层落点（PRD §6.2/§6.5）
- `cli.py` 只做 typer 装配、全局选项解析、命令分发、异常→退出码映射；**顶层禁止 import onnxruntime/genie_tts**（否则 `--help` 超 400ms）。
- 业务层（`registry.py`/`config.py`/`audio.py`/`player.py`/`download/`）**不 import genie_tts**。
- `engine/adapter.py` 是全项目唯一接触上游的地方；`engine/bootstrap.py` 负责 env 注入、离线、镜像、版本检查。

## 6. 开工顺序（强约束）
M0 决策门未出结论前，**不许写任何业务代码**。M0 结论（jieba-fast 能否在无 gcc 的 Linux 容器 / 无 Xcode Command Line Tools 的 macOS 上装上）决定走方案 A 还是方案 B，直接影响 README 与依赖声明。任务拆分见 `genie-term-M0到M4开发任务清单.md`。
