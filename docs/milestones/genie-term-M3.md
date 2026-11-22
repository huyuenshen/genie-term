> **进度说明**：本项目由业余开发者利用**周末等碎片时间**推进，里程碑**不设工期/天数**，只按「做完什么算过关（DoD）」判断进度。一个里程碑可以跨多个周末，做完打勾即可，不要为了赶时间跳过验证步骤。
> 真相源：`docs/genie-term-PRD-v1.2-Unix版.docx`；约束层：`.trae/rules/project_rules.md`；本清单只讲「按什么顺序做、做到什么程度算完成」。

---

## M3 · 进阶能力
前置：M2 合成链路打通。

- [ ] **M3.1** `commands/convert.py`：前置 torch 校验（缺失→退出码 21，**只给一条**正确命令 `pipx inject genie-term torch --index-url .../cpu`）；流程 校验→临时目录→convert_to_onnx→校验 9 文件→原子改名→询问注册（非交互需 --register）；失败清临时+码 20。〔§4.8〕
- [ ] **M3.2** `commands/serve.py`：默认 127.0.0.1；`--host 0.0.0.0` 必须 `--allow-public`+TTY 二次确认否则码 2；`--workers` 上限 1（上游进程内全局单例）。〔§4.9〕
- [ ] **M3.3** `commands/completion.py`：bash/zsh/fish 脚本输出。〔§4.10〕
- [ ] **M3.4** 镜像/离线：`--offline` 只校验不下载并打印手动放置路径；`config set network.hf_endpoint`。〔§5.4/§4.7〕
- [ ] **M3.5** 兼容测试：US-11/12/13/14；`--json` 全命令过 jq；3.13 下 doctor 标 ⚠ 并给 `pipx install --python python3.12`。〔§9〕

**DoD**：US-11/12/13/14 通过；所有 `--json` 输出可被 jq 解析，stdout 无进度条污染。

---

## 本阶段提交前 · 红线自检（与 project_rules.md 同口径）
- 除 `adapter.py` 外无 `import genie_tts`；顶层 `cli.py` 无 onnxruntime/genie_tts import。
- env 在 import 前注入；无 `download_genie_data()` 调用；无 `shell=True`。
- 合成后校验产物 >1KB；`--json` stdout 单对象；退出码符合 PRD §4.1。
- 测试不联网、不真实加载模型。
