> **进度说明**：本项目由业余开发者利用**周末等碎片时间**推进，里程碑**不设工期/天数**，只按「做完什么算过关（DoD）」判断进度。一个里程碑可以跨多个周末，做完打勾即可，不要为了赶时间跳过验证步骤。
> 真相源：`docs/genie-term-PRD-v1.2-Unix版.docx`；约束层：`.trae/rules/project_rules.md`；本清单只讲「按什么顺序做、做到什么程度算完成」。

---

## M4 · 文档 + 真机验证 + 发布
前置：M1–M3 功能完成。

- [ ] **M4.1** README 首屏：三条命令（init→say→doctor）+ 各平台系统准备（Linux 各发行版 apt/dnf/pacman、macOS 用 Homebrew）；失败分支首屏可见（Linux 无 gcc / macOS 无 Xcode CLT→§6.8 处理、HF 不通→镜像、无声卡/无音频输出设备→只出文件）。〔§5.1〕
- [ ] **M4.2** 坏环境矩阵全跑：无 gcc（Linux）/无 Xcode CLT（macOS）/ 无音频输出设备（Linux /dev/snd·PULSE_SERVER；macOS CoreAudio）/ 只读 HOME / 磁盘<500MB / 路径含中文空格 / HF 403超时DNS失败 / LC_ALL=C·TERM=dumb·COLUMNS=40 / `| head -1`（SIGPIPE 不崩）。〔§10.2〕
- [ ] **M4.3** 各平台真机 README 复现：Linux（Ubuntu 22.04/24.04、Debian 12、Fedora 40、Arch）+ macOS（Apple Silicon，macOS 13/14/15 任选），至少覆盖 Ubuntu 两种 + macOS 一种。〔§6.9/§14〕
- [ ] **M4.4** 性能基准：`hyperfine 'genie-term version'` 记入 CHANGELOG；doctor（不含网络）≤3s；合成不劣化上游 15%（转引必带测试条件）。〔§6.10/§10.3〕
- [ ] **M4.5** 发布检查清单 §14 全绿 + PyPI 包名可用性（被占则 `genie-term-cli`，命令名仍 genie-term）+ Trusted Publishing。〔§11/§14〕
- [ ] **M4.6** CHANGELOG + LICENSE + 卸载文档（三目录清理，验证无残留）。〔§11〕

**DoD**：PRD §14 发布检查清单全绿，产出 `0.1.0`。

---

## 本阶段提交前 · 红线自检（与 project_rules.md 同口径）
- 除 `adapter.py` 外无 `import genie_tts`；顶层 `cli.py` 无 onnxruntime/genie_tts import。
- env 在 import 前注入；无 `download_genie_data()` 调用；无 `shell=True`。
- 合成后校验产物 >1KB；`--json` stdout 单对象；退出码符合 PRD §4.1。
- 测试不联网、不真实加载模型。
