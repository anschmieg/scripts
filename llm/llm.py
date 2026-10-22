#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["rich>=13,<15"]
# ///
"""Stateless gateway client. HTTP transport is provided by xh."""

import argparse
import contextlib
import json
import math
import os
import shlex
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import urlsplit

DEFAULT_BASE = "https://code.nothing.pink/v1"
DEFAULT_SYSTEM = (
    "Answer directly and clearly. Match the level of detail to the request; "
    "avoid filler, unnecessary repetition, and stock AI phrasing.\n\n"
    "Use Markdown with language-tagged code fences. Avoid HTML and wide tables. "
    "Follow explicitly requested output formats exactly, without added commentary."
)
ENDPOINTS = {
    "chat": "chat/completions",
    "responses": "responses",
    "messages": "messages",
}
NU_HELP = """Nushell examples (run `nu` from zsh to enter your configured companion shell):

  ^llm --json 'Hello' | from json
  ^llm --json 'Hello' | from json | get choices.0.message.content
  ^llm -a responses --json 'Hello' | from json | get output
    | where type == message | get content | flatten
    | where type == output_text | get text | str join
  ^llm -a messages --json 'Hello' | from json | get content
    | where type == text | get text | str join
  open --raw /tmp/prompt | ^llm -
  ^llm --api-key $env.NOTHING_API_KEY 'Hello'

The multiline pipelines above are single commands; join their lines when pasting.
Your `cat` is a bat wrapper: use `open --raw` for exact file contents.
Your configured PATH includes ~/.local/bin. ^ explicitly selects external commands.
Unlike zsh's $VAR, Nushell accesses environment variables with $env.VAR.
--json is non-streaming. Normal output is already extracted text.
--xh prints zsh/POSIX syntax; run the printed command in zsh, not directly in Nu.
"""


class InputAction(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        inputs = list(getattr(namespace, "inputs", None) or [])
        kind = {"--prompt": "prompt", "--file": "file"}.get(option_string, "auto")
        inputs.append((kind, values))
        namespace.inputs = inputs


def parser():
    p = argparse.ArgumentParser(
        allow_abbrev=False,
        description="Gateway LLM client: existing file arguments are read; other arguments are text.",
        epilog="Inputs are combined in order with blank lines. '-' reads stdin once. "
        "Use --prompt/--file to override detection. No inputs reads stdin. "
        "Credentials: LLM_API_KEY, then NOTHING_API_KEY/NOTHING_GATEWAY_API_KEY "
        "(gateway only). --xh never prints a key. No history or automatic retries. "
        "Exit codes: 0 success; 1 failure; 2 usage error; 3 incomplete/truncated answer.",
    )
    p.add_argument(
        "inputs", nargs="*", action=InputAction, help="prompt text, file path, or -"
    )
    p.add_argument("--prompt", action=InputAction, help="literal text (repeatable)")
    p.add_argument(
        "--file",
        action=InputAction,
        help="required UTF-8 file (repeatable; - for stdin)",
    )
    p.add_argument("-m", "--model", default="big-pickle")
    p.add_argument("-a", "--api", choices=ENDPOINTS, default="chat")
    p.add_argument(
        "--base-url",
        default=os.environ.get("LLM_API_BASE")
        or os.environ.get("NOTHING_API_BASE")
        or DEFAULT_BASE,
    )
    p.add_argument(
        "--api-key",
        help="direct key; prefer environment variables (argv may be visible)",
    )
    p.add_argument(
        "-s",
        "--system",
        help="replace interactive default system prompt ('' disables it)",
    )
    p.add_argument("--timeout", type=float, default=90)
    p.add_argument("--max-tokens", type=int)
    p.add_argument("--temperature", type=float)
    p.add_argument("--json", action="store_true", help="print complete JSON response")
    p.add_argument(
        "-o",
        "--output",
        type=Path,
        help="save plain text/JSON (refuses existing files)",
    )
    p.add_argument("--stream", action="store_true", help="stream generated text")
    p.add_argument(
        "-x",
        "--xh",
        action="store_true",
        help="print runnable zsh xh command; do not send",
    )
    p.add_argument(
        "--nu", action="store_true", help="show Nushell response-parsing examples"
    )
    p.add_argument(
        "--plain", action="store_true", help="disable terminal Markdown rendering"
    )
    return p


def parse_args(argv=None):
    p = parser()
    tokens = list(sys.argv[1:] if argv is None else argv)
    inputs = []
    options = []
    i = 0
    literal = False
    while i < len(tokens):
        token = tokens[i]
        if literal:
            inputs.append(("auto", token))
        elif token == "--":
            literal = True
        elif token == "-" or not token.startswith("-"):
            inputs.append(("auto", token))
        else:
            name, sep, value = token.partition("=")
            action = p._option_string_actions.get(name)
            if action is None and token[:2] in p._option_string_actions:
                name = token[:2]
                action = p._option_string_actions[name]
                value, sep = token[2:], "="
            if action is None:
                p.error(f"unrecognized argument: {token}")
            if action and action.nargs != 0:
                if not sep:
                    i += 1
                    if i >= len(tokens):
                        p.error(f"{name} requires a value")
                    value = tokens[i]
                if name in ("--prompt", "--file"):
                    inputs.append((name[2:], value))
                else:
                    options.append(name + "=" + value)
            else:
                options.append(token)
        i += 1
    args = p.parse_args(options)
    args.inputs = inputs
    if args.nu:
        return args
    if args.json and args.stream:
        p.error("--json and --stream cannot be combined")
    if not math.isfinite(args.timeout) or args.timeout <= 0:
        p.error("--timeout must be positive and finite")
    if args.max_tokens is not None and args.max_tokens <= 0:
        p.error("--max-tokens must be positive")
    if args.temperature is not None and (
        not math.isfinite(args.temperature) or args.temperature < 0
    ):
        p.error("--temperature must be nonnegative and finite")
    try:
        url = urlsplit(args.base_url)
        _ = url.port  # Validate malformed ports as well as IPv6 brackets.
    except ValueError:
        p.error("--base-url is malformed")
    if (
        url.scheme not in ("http", "https")
        or not url.netloc
        or url.username
        or url.password
    ):
        p.error("--base-url must be an HTTP(S) URL without embedded credentials")
    if url.query or url.fragment:
        p.error("--base-url cannot include a query or fragment")
    if args.output and args.output.exists():
        p.error(f"output already exists: {args.output}")
    return args


def read_inputs(inputs):
    if not inputs:
        if sys.stdin.isatty():
            raise ValueError("provide a prompt, file, or stdin")
        inputs = [("auto", "-")]
    parts = []
    stdin_used = False
    for kind, value in inputs:
        if value == "-" and kind != "prompt":
            if stdin_used:
                raise ValueError("stdin '-' can only be used once")
            stdin_used = True
            parts.append(sys.stdin.read())
        elif kind == "file" or (kind == "auto" and is_file(value)):
            parts.append(Path(value).read_text(encoding="utf-8"))
        else:
            parts.append(value)
    text = "\n\n".join(parts)
    if not text.strip():
        raise ValueError("input is empty")
    return text


def is_file(value):
    try:
        return Path(value).is_file()
    except OSError:
        return False  # Long prompts need not be valid filesystem paths.


def render_markdown(args):
    return sys.stdout.isatty() and not args.plain and not args.json


def payload(args, text):
    body = {"model": args.model, "stream": args.stream}
    system = args.system
    if system is None and render_markdown(args):
        system = DEFAULT_SYSTEM
    if args.api == "responses":
        body["input"] = text
        if system:
            body["instructions"] = system
    else:
        messages = [{"role": "user", "content": text}]
        if system:
            if args.api == "messages":
                body["system"] = system
            else:
                messages.insert(0, {"role": "system", "content": system})
        body["messages"] = messages
    if args.max_tokens is not None:
        body["max_output_tokens" if args.api == "responses" else "max_tokens"] = (
            args.max_tokens
        )
    elif args.api == "messages":
        body["max_tokens"] = 4096  # Required by the Messages API.
    if args.temperature is not None:
        body["temperature"] = args.temperature
    return body


def credential(args):
    if args.api_key:
        return args.api_key, None
    names = ["LLM_API_KEY"]
    if (urlsplit(args.base_url).scheme, urlsplit(args.base_url).netloc) == (
        "https",
        urlsplit(DEFAULT_BASE).netloc,
    ):
        names += ["NOTHING_API_KEY", "NOTHING_GATEWAY_API_KEY"]
    for name in names:
        if os.environ.get(name):
            return os.environ[name], name
    return None, "LLM_API_KEY"


def command(args):
    result = [
        "xh",
        "--ignore-stdin",
        "--check-status",
        "--pretty=none",
        "--print=b",
        "--timeout",
        str(args.timeout),
    ]
    if args.stream:
        result.append("--stream")
    result += [
        "POST",
        args.base_url.rstrip("/") + "/" + ENDPOINTS[args.api],
        "Content-Type:application/json",
    ]
    if args.api == "messages":
        result.append("anthropic-version:2023-06-01")
    return result


def print_xh(args, body, key_env):
    # Body goes through stdin, not shell interpolation or xh request-item syntax.
    cmd = [x for x in command(args) if x != "--ignore-stdin"]
    header = "x-api-key:" if args.api == "messages" else "Authorization:Bearer "
    key_env = key_env or "LLM_API_KEY"
    print(
        "# zsh/POSIX shell; set "
        + key_env
        + " before running (key intentionally omitted)"
    )
    print(
        "printf '%s' "
        + shlex.quote(json.dumps(body, ensure_ascii=False))
        + " | "
        + shlex.join(cmd)
        + ' "'
        + header
        + "${"
        + key_env
        + ":?Set "
        + key_env
        + '}"'
    )


class ProtocolError(ValueError):
    """Malformed data received from the API."""


def object_value(value):
    if not isinstance(value, dict):
        raise ProtocolError("expected a JSON object in API response")
    return value


def object_list(value):
    if not isinstance(value, list):
        raise ProtocolError("expected a JSON array in API response")
    return [object_value(item) for item in value]


def text_value(value):
    if not isinstance(value, str):
        raise ProtocolError("expected text in API response")
    return value


def response_status(api, data):
    object_value(data)
    if data.get("error") or data.get("status") in ("failed", "cancelled"):
        return 1, "API failure: " + json.dumps(data.get("error") or data["status"])
    if api == "responses" and data.get("status") == "incomplete":
        return 3, "incomplete answer: " + json.dumps(data.get("incomplete_details"))
    if api == "chat":
        choices = object_list(data.get("choices", []))
        reason = choices[0].get("finish_reason") if choices else None
    else:
        reason = data.get("stop_reason")
    if reason in ("length", "max_tokens", "content_filter", "pause_turn"):
        return 3, f"incomplete answer ({reason})"
    return 0, ""


def extract_text(api, data):
    object_value(data)
    if api == "chat":
        choices = object_list(data.get("choices", []))
        if not choices:
            return ""
        value = object_value(choices[0].get("message", {})).get("content")
        if isinstance(value, str):
            return value
        return "".join(text_value(x.get("text", "")) for x in object_list(value or []))
    if api == "responses":
        return "".join(
            text_value(c.get("text", ""))
            for item in object_list(data.get("output", []))
            if item.get("type") == "message"
            for c in object_list(item.get("content", []))
            if c.get("type") == "output_text"
        )
    return "".join(
        text_value(x.get("text", ""))
        for x in object_list(data.get("content", []))
        if x.get("type") == "text"
    )


def sse_events(lines):
    data = []
    for line in lines:
        line = line.rstrip("\r\n")
        if not line:
            if data:
                yield "\n".join(data)
                data = []
        elif line.startswith("data:"):
            data.append(line[5:].removeprefix(" "))
    if data:
        yield "\n".join(data)


def stream_text(api, lines, status=None):
    if status is None:
        status = {}
    complete = False
    for raw in sse_events(lines):
        if raw == "[DONE]" and api == "chat":
            complete = True
            continue
        data = object_value(json.loads(raw))
        kind = data.get("type", "")
        if data.get("error") or kind in (
            "error",
            "response.failed",
        ):
            raise ValueError("stream error: " + json.dumps(data))
        text = ""
        if api == "chat":
            for choice in object_list(data.get("choices", [])):
                if choice.get("index", 0) == 0:
                    text += text_value(
                        object_value(choice.get("delta", {})).get("content") or ""
                    )
                    if choice.get("finish_reason") is not None:
                        complete = True
                        status["result"] = response_status(api, {"choices": [choice]})
        elif api == "responses":
            if kind == "response.output_text.delta":
                text = text_value(data.get("delta", ""))
            if kind in ("response.completed", "response.incomplete"):
                response = object_value(data.get("response", {}))
                if kind == "response.incomplete":
                    response = {**response, "status": "incomplete"}
                status["result"] = response_status(api, response)
                complete = True
        else:
            if kind == "content_block_delta":
                delta = object_value(data.get("delta", {}))
                if delta.get("type") == "text_delta":
                    text = text_value(delta.get("text", ""))
            if kind == "message_delta":
                status["result"] = response_status(
                    api, object_value(data.get("delta", {}))
                )
            if kind == "message_stop":
                complete = True
        if text:
            yield text
    if not complete:
        raise ValueError(
            "stream ended without a completion event (response may be partial)"
        )


def display(chunks, markdown):
    text = ""
    if markdown:
        from rich.console import Console
        from rich.live import Live
        from rich.markdown import Markdown

        with Live(
            "",
            console=Console(),
            refresh_per_second=8,
            vertical_overflow="ellipsis",
            transient=True,
        ) as live:
            last_update = 0.0
            for chunk in chunks:
                text += chunk
                if time.monotonic() - last_update >= 0.125:
                    live.update(Markdown(text))
                    last_update = time.monotonic()
            # Rich switches to visible overflow during stop(), even for a
            # transient display. Clear first to avoid an extra full-height copy.
            live.update("", refresh=True)
        # The transient preview stays within the viewport; print the full answer
        # once at completion so long answers remain available in scrollback.
        Console().print(Markdown(text))
    else:
        for chunk in chunks:
            text += chunk
            print(chunk, end="", flush=True)
        if text and not text.endswith("\n"):
            print()
    return text


def stop_process(proc):
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=1)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=1)


@contextlib.contextmanager
def output_file(path):
    if path is None:
        yield None
        return
    # Create in the destination directory before sending a request. The final
    # hard link publishes atomically and refuses even a raced-in existing file.
    if os.path.lexists(path):
        raise ValueError(f"output already exists: {path}")
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=path.parent, prefix=".llm-"
    ) as dest:
        yield dest


def run(args, body, key):
    if "\n" in key or "\r" in key:
        raise ValueError("API key cannot contain newlines")
    # xh reads sensitive headers from a mode-0600 temporary file; the key never
    # appears in process argv or in the generated command.
    with tempfile.TemporaryDirectory(prefix="llm-") as directory:
        headers = Path(directory) / "headers"
        headers.write_text(
            json.dumps(
                {
                    "__meta__": {"about": "xh session file", "xh": "0.25.3"},
                    "headers": [
                        {
                            "name": "x-api-key"
                            if args.api == "messages"
                            else "Authorization",
                            "value": key if args.api == "messages" else "Bearer " + key,
                        }
                    ],
                    "cookies": [],
                    "auth": {"type": None, "raw_auth": None},
                }
            ),
            encoding="utf-8",
        )
        headers.chmod(0o600)
        body_file = Path(directory) / "body"
        body_file.write_text(json.dumps(body, ensure_ascii=False), encoding="utf-8")
        body_file.chmod(0o600)
        cmd = command(args) + ["--session-read-only=" + str(headers)]
        cmd.remove("--ignore-stdin")
        with (
            body_file.open("rb") as source,
            tempfile.TemporaryFile(mode="w+") as errors,
            subprocess.Popen(
                cmd,
                stdin=source,
                stdout=subprocess.PIPE,
                stderr=errors,
                text=True,
                encoding="utf-8",
            ) as proc,
        ):
            try:
                markdown = render_markdown(args)
                if proc.stdout is None:
                    raise ValueError("xh stdout pipe unavailable")
                stream_error = None
                status = {}
                if args.stream:
                    try:
                        result = display(
                            stream_text(args.api, proc.stdout, status), markdown
                        )
                    except ValueError as exc:
                        stream_error = exc
                        # Never wait with unread stdout: a full pipe would keep
                        # xh alive forever. Preserve a natural HTTP error if it
                        # has already exited; otherwise stop it promptly.
                        stop_process(proc)
                else:
                    raw = proc.stdout.read()
                code = proc.wait()
                if code and (stream_error is None or code > 0):
                    errors.seek(0)
                    if args.json and not args.stream:
                        try:
                            data = json.loads(raw)
                        except ValueError:
                            pass
                        else:
                            result = json.dumps(data, indent=2, ensure_ascii=False)
                            display([result], False)
                            return result, (
                                1,
                                f"HTTP/transport failure (xh exit {code})",
                            )
                    raise ValueError(
                        f"xh failed (exit {code}): {errors.read().strip()}"
                        + (f"\n{raw.strip()}" if not args.stream else "")
                    )
                if stream_error:
                    raise stream_error
                if not args.stream:
                    data = object_value(json.loads(raw))
                    if args.json:
                        result = json.dumps(data, indent=2, ensure_ascii=False)
                        # Do not require text or a particular nested schema to
                        # inspect raw JSON, including tool-only responses.
                        status["result"] = (0, "")
                        with contextlib.suppress(ProtocolError):
                            status["result"] = response_status(args.api, data)
                    else:
                        status["result"] = response_status(args.api, data)
                        if status["result"][0] == 1:
                            raise ValueError(status["result"][1])
                        result = extract_text(args.api, data)
                    if not args.json and not result and status["result"][0] == 0:
                        raise ValueError(
                            "API returned no generated text; use --json to inspect"
                        )
                    display([result], markdown)
                elif not result and status.get("result", (0, ""))[0] == 0:
                    raise ValueError("API returned no generated text")
                return result, status.get("result", (0, ""))
            finally:
                stop_process(proc)


def main(argv=None):
    args = parse_args(argv)
    if args.nu:
        print(NU_HELP)
        return 0
    try:
        body = payload(args, read_inputs(args.inputs))
        key, key_env = credential(args)
        if args.xh:
            print_xh(args, body, key_env)
            return 0
        if not key:
            raise ValueError(
                "set LLM_API_KEY (or gateway NOTHING_API_KEY), or use --api-key"
            )
        with output_file(args.output) as dest:
            result, (code, message) = run(args, body, key)
            if dest is not None:
                dest.write(result)
                if not result.endswith("\n"):
                    dest.write("\n")
                dest.flush()
                os.link(dest.name, args.output)
        if message:
            print("llm: " + message.replace(key, "[REDACTED]"), file=sys.stderr)
        return code
    except (OSError, ValueError, KeyError, IndexError, TypeError) as exc:
        # Never repeat an explicitly supplied credential in diagnostics.
        message = str(exc)
        if "key" in locals() and key:
            message = message.replace(key, "[REDACTED]")
        print("llm: " + message, file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
