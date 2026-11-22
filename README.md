# genie-term

Unix-like 原生 GenieTTS 命令行封装。**一条命令装好，一行命令出声**。

```bash
pipx install genie-term && genie-term init && genie-term say -c feibi "你好，世界"
```

支持 Linux（Ubuntu/Debian/Fedora/Arch）与 macOS（Apple Silicon/Intel）。基于受控 fork `genie-tts-unix==2.0.2`，解决了上游 `jieba-fast` 无预编译 wheel 和 `onnxruntime==1.22.1` 硬钉已下架的两个安装阻塞。

---

## 快速开始

### 1. 系统准备

**Ubuntu / Debian**
```bash
sudo apt install pipx libportaudio2
pipx ensurepath && exec $SHELL -l
```

**Fedora**
```bash
sudo dnf install pipx portaudio-devel
pipx ensurepath && exec $SHELL -l
```

**Arch**
```bash
sudo pacman -S pipx portaudio
pipx ensurepath && exec $SHELL -l
```

**macOS**
```bash
brew install pipx
pipx ensurepath && exec $SHELL -l
```

> **macOS 无 Xcode CLT 也能装**。受控 fork 已把 `jieba_fast` 替换为纯 Python `jieba`，不需要 gcc/clang。

### 2. 安装与初始化

```bash
pipx install genie-term       # 安装（< 400ms 冷启动）
genie-term init               # 下载 GenieData（391MB，首次约 3-5 分钟）
genie-term doctor             # 环境自检（12 项，有 ✘ → 码 10）
```

### 3. 第一声

```bash
genie-term download character feibi       # 下载预置角色（约 230MB）
genie-term say -c feibi "你好，世界" -o hello.wav
genie-term play hello.wav                 # 或直接：genie-term say -c feibi "你好" --play
```

---

## 常见问题

| 场景 | 症状 | 一键修复 |
|------|------|----------|
| 无音频设备 | `genie-term say` 只出 wav，不播放 | 正常现象——缺声卡不影响合成；装播放器：`sudo apt install ffmpeg` |
| HF 下载慢/超时 | `init` 或 `download` 退出码 11 | `genie-term config set network.hf_endpoint https://hf-mirror.com` |
| pipx 找不到命令 | `exec $SHELL -l` 后仍不行 | `pipx install genie-term` 看路径是否在 `$PATH` 里 |
| macOS 首次 init 慢 | 正常 | 391MB + 230MB 在百兆带宽下约 10 分钟内完成 |
| 需要注册自己的 GPT-SoVITS 模型 | 退出码 21（缺 torch） | `pipx inject genie-term torch --index-url https://download.pytorch.org/whl/cpu` |

---

## 命令速查

### 基础

```bash
genie-term init                                   # 一次性准备（下载 GenieData + 写 config）
genie-term doctor                                 # 环境自检（12 项，带 --no-network 跳过网络检查）
genie-term version                                # 打印版本（--json 输出 JSON）
```

### 角色

```bash
genie-term characters list                        # 列出已注册角色
genie-term characters show feibi                  # 查看角色详情
genie-term download character feibi               # 下载预置角色（feibi/mika/thirtyseven）
genie-term characters add my --model-dir ./tts_models --lang zh \
  --prompt-wav ref.wav --prompt-text "参考文本"   # 注册本地模型
genie-term characters remove my --purge           # 移除角色并删模型目录
```

### 合成

```bash
genie-term say -c feibi "你好" -o a.wav           # 指定输出路径
echo "管道输入" | genie-term say -c feibi         # stdin 输入
genie-term say -c feibi -f lines.txt              # 从文件读文本
genie-term say -c feibi "你好" --json             # stdout 仅 {"output": "..."}
genie-term say -c feibi "你好" --play             # 合成后自动播放
genie-term say -c feibi "你好" -o dir/ --if-exists timestamp  # 重名自动加时间戳
```

### 高级

```bash
genie-term convert --pth a.pth --ckpt a.ckpt --name myvoice --register \
  --prompt-wav ref.wav --prompt-text "参考文本"    # GPT-SoVITS → ONNX + 自动注册
genie-term serve --port 8000                      # 启动本地 HTTP API（默认 127.0.0.1）
genie-term serve --host 0.0.0.0 --allow-public     # 公开监听（⚠ 上游无鉴权，小心）
genie-term config show                            # 查看配置
genie-term config set general.default_character feibi
genie-term completion bash > /etc/bash_completion.d/genie-term  # 自动补全
```

### 脚本化（CI/批处理）

```bash
while IFS= read -r line; do
  genie-term say -c feibi --json "$line" | jq -r .output
done < lines.txt
```

> **不要并行跑多个 `say`**——上游单进程，CPU 争抢。并发请走 `genie-term serve`。

---

## 离线 / 内网

1. 有网机器上 `init` + `download character feibi`
2. 打包数据目录（默认 `~/.local/share/genie-term/`，macOS 在 `~/Library/Application Support/genie-term/`）
3. 目标机解压后：

```bash
genie-term config set engine.data_dir /path/to/data
genie-term init --offline --yes                   # 仅校验，不下载
genie-term say -c feibi "你好"                     # 离线合成
```

---

## 退出码

| 码 | 含义 | 常见触发 |
|----|------|----------|
| 0 | 成功 | — |
| 2 | 用法/参数错/非交互需确认 | 空输入、未知角色、`--yes` 缺失 |
| 10 | 环境缺失 | 数据目录/模型目录/参考音频/onnxruntime 缺 |
| 11 | 网络失败 | HF 不通、下载超时 |
| 12 | 播放失败（仅 `--play`） | 找不到播放器；**不影响合成** |
| 20 | 引擎内部错误 | 产物校验失败（tts 返回空文件） |
| 21 | 缺 torch | 跑 `convert` 但没装 |
| 130 | Ctrl-C | 中断 |

---

## 数据布局

```
Linux (XDG)                              macOS
─────────────                            ─────
~/.config/genie-term/                    ~/Library/Application Support/genie-term/
  config.toml                              config.toml
~/.local/share/genie-term/                ~/Library/Application Support/genie-term/
  registry.toml                           registry.toml
  GenieData/                              GenieData/           (~391MB)
  CharacterModels/                        CharacterModels/
~/.local/state/genie-term/logs/           ~/Library/Logs/genie-term/
  genie-term.log (按天轮转，7 天)            genie-term.log
~/.cache/genie-term/tmp/                  ~/Library/Caches/genie-term/
```

所有路径经 `platformdirs` 解析，**禁止硬编码**。

---

## 架构

```
genie-term/
├── cli.py                 主入口 + 异常处理链（退出码契约）
├── errors.py              7 种 GenieTermError + 退出码映射
├── core/
│   ├── paths.py           platformdirs 目录解析
│   ├── config.py          config.toml 读写（原子写 + .bak）
│   ├── registry.py        角色注册表 + 必需文件清单
│   ├── audio.py           音频校验 + 产物 >1KB 验证
│   └── player.py          播放策略链
├── engine/
│   ├── bootstrap.py       GENIE_DATA_DIR / HF_ENDPOINT 注入
│   └── adapter.py         ⚠ 唯一 import genie_tts 的地方
├── download/
│   ├── genie_data.py      绝对目录 snapshot_download
│   └── verify.py          必需文件校验
└── commands/              9 个 typer 子命令组
```

**核心红线**（任何评审必须过）：
- 只有 `engine/adapter.py` 可以 `import genie_tts`
- GENIE_DATA_DIR / HF_ENDPOINT 必须在 `import genie_tts` 之前注入
- 合成后必须校验产物 **>1KB**（上游 tts 无参考音频时只打日志 return）
- `--json` 模式 stdout **只有一个 JSON 对象**，进度/警告全走 stderr
- 禁止 `shell=True`，所有外部播放器用列表参数

---

## 开发

```bash
pip install -e ".[dev]"          # 安装 + 开发依赖
pytest -m "not network"          # 跑离线测试（67 个，全绿）
ruff check src                   # lint（CI 强制通过）
pipx install --editable .        # 本地 pipx 链路验证
```

测试约束：**不得真实联网、不得真实加载模型**。用 engine_stub 断言调用顺序 `load → set_ref → tts → 产物校验`。

---

## 卸载与清理

```bash
pipx uninstall genie-term
rm -rf ~/.config/genie-term ~/.local/share/genie-term
rm -rf ~/.local/state/genie-term ~/.cache/genie-term
# macOS:
rm -rf ~/Library/Application\ Support/genie-term ~/Library/Logs/genie-term ~/Library/Caches/genie-term
```

---

## License

与上游 GenieTTS 保持一致，见 `vendor/genie-tts-unix/LICENSE`。
