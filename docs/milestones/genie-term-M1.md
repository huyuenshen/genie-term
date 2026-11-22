> **进度说明**：本项目由业余开发者利用**周末等碎片时间**推进，里程碑**不设工期/天数**，只按「做完什么算过关（DoD）」判断进度。一个里程碑可以跨多个周末，做完打勾即可，不要为了赶时间跳过验证步骤。
> 真相源：`docs/genie-term-PRD-v1.2-Unix版.docx`；约束层：`.trae/rules/project_rules.md`；本清单只讲「按什么顺序做、做到什么程度算完成」。

---

## M1 · 脚手架 + 环境与配置
前置：M0 已出结论（决定了依赖声明与 README 是否提 gcc / Xcode CLT）。

- [ ] **M1.1** 建目录骨架（PRD §6.5 文件级结构：`src/genie_term/{cli.py,context.py,errors.py,core/,download/,engine/,commands/}`、`tests/{unit,integration,e2e}/`、`.github/workflows/`）。〔§6.5〕
- [ ] **M1.2** `pyproject.toml`：hatchling 构建、console script 入口 `genie-term`、extras `[convert]`/`[dev]`、`Requires-Python>=3.10,<3.13`。〔§6.1/§11〕
- [ ] **M1.3** `errors.py`：`GenieTermError(code, message, fix)` + 异常→退出码映射表（0/2/10/11/12/20/21/130）。〔§4.1/§7〕
- [ ] **M1.4** `core/paths.py`：经 `platformdirs` 做数据/配置/日志/cache 目录解析（Linux 走 XDG、macOS 走 `~/Library`，禁止硬编码路径）；优先级 `--data-dir > GENIE_TERM_DATA_DIR > 平台默认`。〔§6.6〕
- [ ] **M1.5** `core/config.py`：读写/校验/迁移 config.toml（schema_version=1），原子写 + .bak。〔§6.7〕
- [ ] **M1.6** `commands/version.py`（打印 genie-term/genie-tts/onnxruntime/Python/平台）+ `commands/config.py`（show/get/set/reset/path）。〔§4.10〕
- [ ] **M1.7** `commands/doctor.py`：12 项检查 + ✔/⚠/✘ 三级报告 + 每项按平台给修复命令（Linux 的 apt/dnf/pacman、macOS 的 brew）+ `--json` 结构。有 ✘→退出码 10，仅 ⚠→0。〔§4.4〕
- [ ] **M1.8** `commands/init.py`：5 步顺序（解析目录→查 Python/依赖→查磁盘→下 391MB→校验 12 项→写 config→打印下一步）；幂等，`--force` 才重下。〔§4.3〕
- [ ] **M1.9** CI `test.yml`（Linux 矩阵 + ruff + pip-audit + help 快照）+ macOS runner job（Apple Silicon）；`engine/adapter.py` 占位但保证除它之外无 genie_tts import（加 lint/CI 断言）。〔§11/红线〕

**DoD**：CI 绿；真实下载 391MB 成功；`--help`/`version` P95 ≤400ms（顶层无重依赖 import）。

---

## 本阶段提交前 · 红线自检（与 project_rules.md 同口径）
- 除 `adapter.py` 外无 `import genie_tts`；顶层 `cli.py` 无 onnxruntime/genie_tts import。
- env 在 import 前注入；无 `download_genie_data()` 调用；无 `shell=True`。
- 合成后校验产物 >1KB；`--json` stdout 单对象；退出码符合 PRD §4.1。
- 测试不联网、不真实加载模型。
