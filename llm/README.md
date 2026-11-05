# `llm` — Gateway LLM client

`llm` is a stateless CLI client for OpenAI-style chat/responses/messages gateways. It streams Markdown-rendered answers to the terminal, supports multiple input files and prompts, image attachments, shell-command suggestion mode, and an `xh`-preview mode that prints a runnable command without sending anything.

## Requirements

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) (runs the script via its PEP 723 inline metadata)
- [xh](https://github.com/ducaale/xh) (HTTP transport)
- `rich` (terminal Markdown rendering; installed automatically by uv)

## Installation

The script is executable and self-contained:

```sh
chmod +x llm/llm.py
# Optionally symlink into ~/.local/bin
ln -s "$PWD/llm/llm.py" ~/.local/bin/llm
```

## Configuration

### Default model

The default model is read from `~/.config/llm/config.toml`:

```toml
model = "coding:free"
```

Falls back to `coding:free` when the file is missing or unreadable. Override per invocation with `-m/--model`. The config directory/file are defined by `CONFIG_DIR` / `CONFIG_FILE` in `llm.py`.

### Base URL & credentials

- Base URL defaults to `https://code.nothing.pink/v1`; override with `--base-url` or `LLM_API_BASE` / `NOTHING_API_BASE`.
- API key resolution: `--api-key` → `LLM_API_KEY` → (for the default gateway) `NOTHING_API_KEY` / `NOTHING_GATEWAY_API_KEY`.

## Usage

```sh
llm [inputs...] [options]
```

Inputs are combined in order with blank lines. Existing file paths are read; other arguments are treated as prompt text. `-` reads stdin. Use `--prompt` / `--file` to force interpretation.

### Flags

| Flag | Description |
|------|-------------|
| `-m, --model NAME` | Model name (default from config) |
| `-a, --api {chat,responses,messages}` | API style (default `chat`) |
| `--base-url URL` | Gateway base URL |
| `--api-key KEY` | Direct key (prefer env vars) |
| `-S, --system TEXT` | Replace default system prompt (`''` disables) |
| `-s, --shell` | Shell command suggestion mode (command + explanation) |
| `-i, --image FILE` | Attach image file (repeatable; chat API only) |
| `--timeout SECONDS` | Request timeout (default 90) |
| `--max-tokens N` | Max output tokens |
| `--temperature F` | Sampling temperature |
| `--timings` | Report client timings to stderr |
| `--json` | Print complete JSON response |
| `-o, --output PATH` | Save output (refuses existing files) |
| `--stream` / `--no-stream` | Streaming toggle (default: stream when TTY) |
| `-x, --xh` | Print runnable zsh xh command, do not send |
| `--nu` | Show Nushell parsing examples |
| `--plain` | Disable Markdown rendering |

### Examples

```sh
llm 'Explain this code' < file.py
llm --prompt 'Summarize' --file notes.md
llm -s 'list files larger than 1MB'
llm -i screenshot.png 'What is in this image?'
llm --json -a responses 'Hello'
llm -x 'Hello'   # print runnable xh command only
```

## Exit codes

- `0` success
- `1` failure
- `2` usage error
- `3` incomplete/truncated answer

## Tests

```sh
make test-llm          # run tests
make check-llm         # lint + format check + tests
```

Tests live in `llm/tests/test_llm.py` and use a local mock HTTP server plus `xh`.

## Notes

- Stateless: no history, no automatic retries.
- `--xh` never prints a key.
- Credentials may appear in argv when passed via `--api-key`; prefer environment variables.
