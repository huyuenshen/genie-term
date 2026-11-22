# genie-term

[简体中文](README.md) | English

A native Unix-like CLI wrapper for GenieTTS. **Install with one command, speak with one line.**

```bash
pipx install genie-term && genie-term init && genie-term say -c feibi "Hello, world"
```

Supports Linux (Ubuntu/Debian/Fedora/Arch) and macOS (Apple Silicon/Intel). Built on the controlled fork `genie-tts-unix==2.0.2`, which removes two upstream installation blockers: `jieba-fast` has no prebuilt wheels, and the pinned `onnxruntime==1.22.1` has been yanked.

---

## Quick Start

### 1. System Preparation

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

> **macOS works without Xcode CLT.** The controlled fork replaces `jieba_fast` with pure-Python `jieba`, so no gcc/clang is required.

### 2. Install and Initialize

```bash
pipx install genie-term       # install
genie-term init               # download GenieData (391MB, ~3-5 min on first run)
genie-term doctor             # environment check (12 items; any ✘ → exit code 10)
```

### 3. First Sound

```bash
genie-term download character feibi       # download a preset character (~230MB)
genie-term say -c feibi "Hello, world" -o hello.wav
# To play it directly, add --play (requires a system player or PortAudio)
genie-term say -c feibi "Hello" --play
```

---

## FAQ

| Scenario | Symptom | One-step Fix |
|----------|---------|--------------|
| No audio device | `genie-term say` writes a wav but does not play it | Expected — no sound card does not affect synthesis; install a player: `sudo apt install ffmpeg` |
| Slow or timed-out HF downloads | `init` or `download` exits with code 11 | `genie-term config set network.hf_endpoint https://hf-mirror.com` |
| pipx cannot find the command | Still missing after `exec $SHELL -l` | Check whether the `pipx install genie-term` path is in `$PATH` |
| Slow first `init` on macOS | Normal | 391MB + 230MB completes within about 10 minutes on a 100Mbps link |
| Register your own GPT-SoVITS model | Exit code 21 (torch missing) | `pipx inject genie-term torch --index-url https://download.pytorch.org/whl/cpu` |

---

## Command Reference

### Basics

```bash
genie-term init                                   # one-time setup (download GenieData + write config)
genie-term doctor                                 # environment check (12 items; --no-network skips network checks)
genie-term version                                # print versions (--json for JSON output)
```

### Characters

```bash
genie-term characters list                        # list registered characters
genie-term characters show feibi                  # show character details
genie-term download character feibi               # download a preset character (feibi/mika/thirtyseven)
genie-term characters add my --model-dir ./tts_models --lang zh \
  --prompt-wav ref.wav --prompt-text "reference text"   # register a local model
genie-term characters remove my --purge           # remove a character and delete its model directory
```

### Synthesis

```bash
genie-term say -c feibi "Hello" -o a.wav          # write to a specific path
echo "piped text" | genie-term say -c feibi       # read from stdin
genie-term say -c feibi -f lines.txt              # read from a file
genie-term say -c feibi "Hello" --json            # stdout contains only {"output": "..."}
genie-term say -c feibi "Hello" --play            # synthesize and play
genie-term say -c feibi "Hello" -o dir/ --if-exists timestamp  # append a timestamp on name conflicts
```

### Advanced

```bash
genie-term convert --pth a.pth --ckpt a.ckpt --name myvoice --register \
  --prompt-wav ref.wav --prompt-text "reference text" --lang zh  # → ONNX + auto-register
genie-term serve --port 8000                      # start a local HTTP API (127.0.0.1 by default)
genie-term serve --port 8000 --json               # print {"host","port","docs"} to stdout on start
genie-term serve --host 0.0.0.0 --allow-public    # public listening (⚠ upstream has no auth; use with care)
genie-term config show                            # show configuration
genie-term config set general.default_character feibi
genie-term completion bash > /etc/bash_completion.d/genie-term  # shell completion
```

### Global Options (PRD §4.1)

```bash
genie-term --quiet say -c feibi "Hello"       # suppress progress, keep errors only
genie-term --no-color doctor                 # disable color (respects NO_COLOR / TERM=dumb)
genie-term --offline say -c feibi "Hello"    # disable all network requests
genie-term init --offline --yes              # validate existing resources only and print manual placement paths
```

### Scripting (CI/Batch)

```bash
while IFS= read -r line; do
  genie-term say -c feibi --json "$line" | jq -r .output
done < lines.txt
```

> **Do not run multiple `say` processes in parallel** — upstream is single-process and competes for CPU. Use `genie-term serve` for concurrency.

---

## Offline / Air-gapped Environments

1. On a networked machine, run `init` and `download character feibi`
2. Archive the data directory (default `~/.local/share/genie-term/`; on macOS `~/Library/Application Support/genie-term/`)
3. On the target machine, extract it and run:

```bash
genie-term config set engine.data_dir /path/to/data
genie-term init --offline --yes                   # validate only, no downloads
genie-term say -c feibi "Hello"                   # offline synthesis
```

---

## Exit Codes

| Code | Meaning | Common Trigger |
|------|---------|----------------|
| 0 | Success | — |
| 2 | Usage/argument error, or confirmation needed in non-interactive mode | Empty input, unknown character, missing `--yes` |
| 10 | Missing environment | Missing data dir, model dir, reference audio, or onnxruntime |
| 11 | Network failure | HF unreachable, download timeout |
| 12 | Playback failure (`--play` only) | No player found; **does not affect synthesis** |
| 20 | Engine internal error | Output validation failed (tts produced an empty file) |
| 21 | torch missing | Running `convert` without torch |
| 130 | Ctrl-C | Interrupted |

---

## Data Layout

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
  genie-term.log (daily rotation, 7 days)   genie-term.log
~/.cache/genie-term/tmp/                  ~/Library/Caches/genie-term/
```

All paths are resolved through `platformdirs`; **hard-coded paths are forbidden**.

---

## Architecture

```
genie-term/
├── cli.py                 main entry + exception handling chain (exit code contract)
├── context.py             global options (--quiet/--no-color/--offline)
├── errors.py              7 GenieTermError types + exit code mapping
├── core/
│   ├── paths.py           platformdirs directory resolution
│   ├── config.py          config.toml read/write (atomic write + .bak)
│   ├── registry.py        character registry + required file list
│   ├── audio.py           audio validation + output >1KB check
│   ├── log.py             file logging (daily rotation, 7 days; text redaction)
│   └── player.py          playback strategy chain
├── engine/
│   ├── bootstrap.py       GENIE_DATA_DIR / HF_ENDPOINT injection
│   └── adapter.py         ⚠ the only place that imports genie_tts
├── download/
│   ├── genie_data.py      absolute-directory snapshot_download
│   ├── presets.py         preset character metadata + auto-registration
│   └── verify.py          required file validation
└── commands/              9 typer command groups
```

**Core invariants** (every review must pass):
- Only `engine/adapter.py` may `import genie_tts`
- GENIE_DATA_DIR / HF_ENDPOINT must be injected before `import genie_tts`
- Synthesis must validate the output file is **>1KB** (upstream tts only logs and returns when reference audio is missing)
- In `--json` mode, stdout contains **exactly one JSON object**; progress/warnings go to stderr
- `shell=True` is forbidden; all external players use argument lists

---

## Development

```bash
pip install -e ".[dev]"          # install with dev dependencies
pytest -m "not network"          # run offline tests (81 tests, all green)
ruff check src tests             # lint (enforced in CI)
pipx install --editable .        # verify the local pipx path
```

Testing constraints: **no real network access and no real model loading**. Use engine_stub to assert the call order `load → set_ref → tts → output validation`.

---

## Uninstall and Cleanup

```bash
pipx uninstall genie-term
rm -rf ~/.config/genie-term ~/.local/share/genie-term
rm -rf ~/.local/state/genie-term ~/.cache/genie-term
# macOS:
rm -rf ~/Library/Application\ Support/genie-term ~/Library/Logs/genie-term ~/Library/Caches/genie-term
```

---

## License

MIT, consistent with upstream GenieTTS. See `LICENSE` in the repository root and `vendor/genie-tts-unix/LICENSE`.
