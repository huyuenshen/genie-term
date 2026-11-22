> **进度说明**：本项目由业余开发者利用**周末等碎片时间**推进，里程碑**不设工期/天数**，只按「做完什么算过关（DoD）」判断进度。一个里程碑可以跨多个周末，做完打勾即可，不要为了赶时间跳过验证步骤。
> 真相源：`docs/PRD.md`；约束层：`project_rules.md`；本清单只讲「按什么顺序做、做到什么程度算完成」。

---

## M0 · 安装可行性决策门（★ 不通过不许进 M1）
目标：确认 `jieba-fast==0.53`（PyPI 仅 sdist、无 wheel）能否在无编译器环境装上——Linux 指无 gcc/build-essential，macOS 指无 Xcode Command Line Tools（clang）。这是「一条命令装好」的最大威胁（PRD §6.8 / §12）。

- [ ] **M0.1** 拉最小包 `genie-term==0.0.1a0`（只声明 genie-tts==2.0.2 依赖链，不含业务代码）。〔§6.8〕
- [ ] **M0.2** 在 `docker run --rm ubuntu:24.04`（**不装 build-essential**）执行 `pipx install genie-term==0.0.1a0`，记录退出码与报错。〔§6.8〕
- [ ] **M0.2b** 在干净 macOS 环境（GitHub Actions `macos-latest` runner，或确认未装 Xcode CLT 的 Apple Silicon 真机）执行同一命令，记录退出码与报错——jieba-fast 在 macOS 同样只有源码包，无 clang 时安装会失败，风险与 Linux 无 gcc 等价。〔§6.8〕
- [ ] **M0.3** 判定分支并落结论到 `docs/DECISION-M0.md`：〔§6.8〕
      - 通过 → 走正常路径，README 不提 gcc；
      - 失败 → 选定兜底方案：
        - **方案 A**（预编译 wheel 随包，不改上游）：CI 用 cibuildwheel 为 jieba-fast 0.53 构建 cp310–cp312 ×（Linux manylinux x86_64/aarch64 + macOS arm64/x86_64）轮子，cibuildwheel 原生覆盖这两类 Unix 平台；在 genie-term 依赖里用 PEP 508 `jieba-fast @ https://…whl` + `python_version/platform_machine/platform_system` 环境标记满足上游同名依赖。
        - **方案 B**（受控 fork，推荐兜底）：fork genie-tts → 发 `genie-tts-unix`（import 名仍 genie_tts，命名从 -linux 改 -unix 以同时覆盖 Linux 与 macOS），用纯 Python `jieba` 替代 `jieba_fast`、ChineseG2P/ToneSandhi 的 posseg 改 `jieba.posseg`；保留版权声明，README 声明差异与同步策略。
- [ ] **M0.4** 上游六陷阱 spike：验证「import 前注入 env」「导入期不触发 input()」「不调 download_genie_data」「predefined 角色临时 chdir」「产物校验代替返回值」「roberta 未导出需自实现或下线」。〔§6.4〕

**DoD**：M0 决策门有明确结论；`import genie_tts` 在受控 env 下可稳定成功；PRD §6.8 验收标准达成（干净 ubuntu:24.04 无 gcc **与** 干净 macOS 无 Xcode CLT，`pipx install` 均退出码 0 且 `genie-term doctor` 可运行）。

---

## 本阶段提交前 · 红线自检（与 project_rules.md 同口径）
- 除 `adapter.py` 外无 `import genie_tts`；顶层 `cli.py` 无 onnxruntime/genie_tts import。
- env 在 import 前注入；无 `download_genie_data()` 调用；无 `shell=True`。
- 合成后校验产物 >1KB；`--json` stdout 单对象；退出码符合 PRD §4.1。
- 测试不联网、不真实加载模型。
