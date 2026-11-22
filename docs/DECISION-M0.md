# DECISION-M0 · 安装可行性决策门结论

> 本文件是 M0 里程碑的最终决策文档。
> 真相源：`project_rules.md` + PRD §6.8；测试证据来自本地 venv 隔离 + 上游源码审计（`/tmp/tts_check2/genie_tts-2.0.2/`）。

---

## 1. 测试执行记录

### M0.2 · Ubuntu 24.04 无 build-essential
| 步骤 | 命令 | 结果 |
|------|------|------|
| 基线（有 gcc） | `pip install jieba-fast==0.53` in venv | ✅ 成功：构建 `jieba_fast-0.53-cp314-cp314-linux_x86_64.whl` |
| 屏蔽 gcc/cc/g++/make/ld | PATH 优先 `/tmp/nocompiler/` wrapper | ❌ 失败：`ld returned 127 exit status`，`Failed building wheel for jieba-fast` |
| 上游依赖审计 | `pip download genie-tts==2.0.2 --no-deps` | ⚠️ 发现第二个硬问题 |

**关键发现**：`jieba_fast-0.53.tar.gz`（7.5MB sdist）无任何预编译 wheel，安装时必须用 Cython + gcc 编译 `.c → .so` 扩展。干净容器无 gcc → 安装必然失败。

### 额外发现：onnxruntime==1.22.1 硬钉已下架
genie-tts==2.0.2 的 `setup.py` 硬钉 `onnxruntime==1.22.1`，但 PyPI 可用版本已从 1.24.1 起，**1.22.1 不存在**。即使 jieba-fast 解决，genie-tts 本身也装不上。

### M0.2b · macOS 无 Xcode CLT
- GitHub Actions workflow 已创建：`.github/workflows/M0-install-feasibility.yml`
- macOS 侧与 Linux 等价：jieba-fast 同样只有 sdist，无 clang 必然失败
- workflow 同时覆盖 `ubuntu-24.04` runner 移除 build-essential 后安装测试

### M0.4 · 上游六陷阱 Spike（全部确认）
| # | 陷阱 | 位置 | 确认 | 对策 |
|---|------|------|------|------|
| 1 | `GENIE_DATA_DIR` 模块导入时固化 | `Core/Resources.py:L30-33` → `os.getenv("GENIE_DATA_DIR", "./GenieData")` | ✅ | import genie_tts 前注入 env，进程内仅一次 |
| 2 | 数据目录不存在时 `input()` 阻塞 | `Core/Resources.py:L67-76` | ✅ | 导入前保证目录与文件齐全；缺数据先自行报错 |
| 3 | `download_genie_data()` 用 `local_dir="."` 污染 CWD | `Core/Resources.py:L5-13` → `snapshot_download(..., local_dir=".")` | ✅ | 禁用此 API；自写绝对目录 snapshot_download |
| 4 | `load_predefined_character()` 下载到相对目录 `CharacterModels/` | `PredefinedCharacter.py:L23-33` → `save_path = "./CharacterModels/..."` | ✅ | adapter 内临时 chdir 到 data_dir 调用，异常也恢复 |
| 5 | `tts()` 无参考音频时 `logger.error` 后 return，退出码 0 | `Internal.py:L262-284` | ✅ | 禁止依赖返回值；合成后校验产物 >1KB |
| 6 | `download_roberta_data()` 未导出 | RoBERTa 检查被注释掉（L62-65） | ✅ | 自实现 snapshot_download；仓库无此路径则 V1 下线 |

---

## 2. 决策：采用方案 B —— 受控 fork

### 为什么不是方案 A（预编译 wheel 随包）
1. 我们有 **两个** 上游问题（jieba-fast + onnxruntime 硬钉），方案 A 只能解决前者
2. genie-tts 的 setup.py 硬钉 onnxruntime==1.22.1 已失效，我们必须要么覆盖要么 fork
3. cibuildwheel 只为 jieba-fast 一个包构建 wheel，维护成本高（每次上游 jieba-fast 发新版都要重构建）
4. 受控 fork 是根治方案：一次性解决所有上游问题 + 可选择性移除不需要的依赖

### 方案 B 实施计划
创建受控 fork `genie-tts-unix`（import 名仍为 `genie_tts`）：

| 修改项 | 原依赖 | 替换为 | 理由 |
|--------|--------|--------|------|
| 分词引擎 | `jieba_fast`（sdist-only） | `jieba`（纯 Python，已有多平台 wheel） | 消除编译依赖 |
| 韵律模块 posseg | `jieba_fast.posseg` | `jieba.posseg` | 同步替换 |
| onnxruntime 版本 | `==1.22.1`（已下架） | `>=1.16,<2`（宽松） | 兼容当前 PyPI 可用版本 |
| g2pM 可选降级 | `g2pM` | `g2pM>=0.1.2` 保留 | 已有 wheel，非阻塞 |
| sounddevice 可选降级 | `sounddevice` | 保留（try/except in adapter） | 缺 PortAudio 不阻塞合成 |

### Fork 命名与 PyPI 发布
- PyPI 包名：`genie-tts-unix`（从 PRD 建议的 `-linux` 改为 `-unix`，同时覆盖 Linux + macOS）
- import 名：`genie_tts`（零代码改动，adapter.py 直接 `import genie_tts`）
- 版本号：保持 `2.0.2`（与上游对齐）
- genie-term 的依赖声明：`genie-tts-unix==2.0.2`（而非 `genie-tts==2.0.2`）

### 同步策略
- 仅做**必要的依赖与兼容性修改**，不改动任何 TTS 核心逻辑
- 上游 genie-tts 发新版本时，评估是否需要跟进 fork
- fork 仓库 README 明确标注：本 fork 仅解决 Unix-like 安装问题，不改动模型/合成逻辑

---

## 3. M0 DoD 达成判定

| DoD 项 | 状态 | 证据 |
|--------|------|------|
| M0 决策门有明确结论 | ✅ | 方案 B：受控 fork genie-tts-unix |
| jieba-fast 安装路径已证实 | ✅ | 无 gcc 必然失败；有 gcc 可成功 |
| 额外发现 onnxruntime 硬钉问题 | ✅ | 需要在 fork 中同步解决 |
| 上游六陷阱全部 spike 验证 | ✅ | 6/6 位置与对策已明确 |
| GitHub Actions workflow 已创建 | ✅ | `.github/workflows/M0-install-feasibility.yml` |

**M0 里程碑：放行 → 进入 M1**

实施顺序：先创建 genie-tts-unix fork → 发布 PyPI → genie-term 的 pyproject.toml 改用 fork 依赖 → 进入 M1 脚手架开发。
