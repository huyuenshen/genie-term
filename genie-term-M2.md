> **进度说明**：本项目由业余开发者利用**周末等碎片时间**推进，里程碑**不设工期/天数**，只按「做完什么算过关（DoD）」判断进度。一个里程碑可以跨多个周末，做完打勾即可，不要为了赶时间跳过验证步骤。
> 真相源：`docs/PRD.md`；约束层：`project_rules.md`；本清单只讲「按什么顺序做、做到什么程度算完成」。

---

## M2 · 核心合成链路
前置：M1 脚手架、config、doctor 就绪。

- [ ] **M2.1** `core/registry.py`：characters 注册表（读→.bak→临时→os.replace），schema 校验，高版本拒绝写入。〔§6.7/§4.6〕
- [ ] **M2.2** `core/audio.py`：时长探测、格式白名单（.wav/.flac/.ogg/.aiff/.aif）、**产物校验（存在且 >1KB）**。〔§4.6/§6.4 陷阱5〕
- [ ] **M2.3** `download/`：`genie_data.py`（绝对目录 snapshot_download、镜像、断点续传）+ `presets.py`（预置角色临时 chdir 到 data_dir 调用）+ `verify.py`（必需文件清单单一来源：基线 7 + v2ProPlus 追加 2）。〔§4.7/§6.6/§6.4〕
- [ ] **M2.4** `commands/download.py`：genie-data / character / roberta（roberta 自实现，仓库无该路径则 V1 下线）。失败统一退出码 11 + hf-mirror 提示。〔§4.7〕
- [ ] **M2.5** `commands/characters.py`：list/show/add/use/remove（add 强制校验 model-dir 存在、必需文件齐全、model_version 自动推断、**参考音频成对必填**、时长 <3s 警告 >20s 拒绝）。〔§4.6〕
- [ ] **M2.6** `engine/adapter.py`：`ensure_env/load_voice/synth/convert/serve`，env 在 import 前注入且进程内一次；synth 后必校验产物。〔§6.2/§6.3〕
- [ ] **M2.7** `commands/say.py`：文本来源优先级（参数>-f>stdin，全空→2）；角色默认解析；语言优先级且拒 zh/en/jp 之外；输出命名与 `--if-exists`（默认 overwrite）；`--play` 决策链（sounddevice→afplay(macOS 自带)→ffplay→paplay→aplay→仅存盘，macOS 走 CoreAudio、Linux 走 ALSA/Pulse，播放失败不影响退出码）；首次用角色下载询问；`--json` 单对象。〔§4.5〕
- [ ] **M2.8** 集成测试：用 engine_stub 断言 `load→set_ref→tts→产物校验` 顺序；覆盖 US-03/04/06/07/08。〔§9/§10.1〕

**DoD**：US-03/04/06/07/08 通过；无声卡机器 say 出文件退出码 0 仅一条 ⚠；误删参考音频 say→退出码 10 且无空文件。

---

## 本阶段提交前 · 红线自检（与 project_rules.md 同口径）
- 除 `adapter.py` 外无 `import genie_tts`；顶层 `cli.py` 无 onnxruntime/genie_tts import。
- env 在 import 前注入；无 `download_genie_data()` 调用；无 `shell=True`。
- 合成后校验产物 >1KB；`--json` stdout 单对象；退出码符合 PRD §4.1。
- 测试不联网、不真实加载模型。
