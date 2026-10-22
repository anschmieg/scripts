"""Run with python3 -m unittest discover -s llm/tests -v from the scripts repo."""

import contextlib
import io
import json
import os
import pty
import runpy
import select
import subprocess
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import ClassVar
from unittest.mock import patch

CLI = Path(__file__).resolve().parents[1] / "llm.py"
M = runpy.run_path(str(CLI))


class UnitTests(unittest.TestCase):
    def test_order_and_overrides(self):
        args = M["parse_args"](
            [
                "first",
                "--prompt",
                "second",
                "--file",
                "third",
                "-mbeam-free",
                "fourth",
                "--",
                "--literal",
            ]
        )
        self.assertEqual(args.model, "beam-free")
        self.assertEqual(
            args.inputs,
            [
                ("auto", "first"),
                ("prompt", "second"),
                ("file", "third"),
                ("auto", "fourth"),
                ("auto", "--literal"),
            ],
        )

    def test_input(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory) / "input"
            p.write_text("file\n")
            with patch("sys.stdin", io.StringIO("stdin")):
                self.assertEqual(
                    M["read_inputs"](
                        [("prompt", str(p)), ("file", str(p)), ("auto", "-")]
                    ),
                    str(p) + "\n\nfile\n\n\nstdin",
                )
            with self.assertRaises(ValueError), patch("sys.stdin", io.StringIO("x")):
                M["read_inputs"]([("auto", "-"), ("auto", "-")])
        self.assertFalse(M["is_file"]("a" * 10000))

    def test_defaults(self):
        for api in ("chat", "responses", "messages"):
            args = M["parse_args"](["-a", api])
            with patch("sys.stdout.isatty", return_value=True):
                body = M["payload"](args, "hello")
            system = (
                body["messages"][0]["content"]
                if api == "chat"
                else body["instructions" if api == "responses" else "system"]
            )
            self.assertEqual(system, M["DEFAULT_SYSTEM"])
            with patch("sys.stdout.isatty", return_value=False):
                body = M["payload"](args, "hello")
            self.assertNotIn("system", body)
            self.assertNotIn("instructions", body)
            if api == "chat":
                self.assertEqual(body["messages"][0]["role"], "user")
        args = M["parse_args"](["-s", ""])
        with patch("sys.stdout.isatty", return_value=True):
            self.assertEqual(len(M["payload"](args, "hello")["messages"]), 1)

    def test_validation(self):
        for argv in (
            ["--stream", "--json"],
            ["--timeout", "nan"],
            ["--max-tokens", "0"],
            ["--temperature", "-1"],
            ["--base-url", "https://user:pass@example.com"],
            ["--base-url", "http://[bad"],
            ["--base-url", "http://localhost:bad"],
        ):
            with (
                self.subTest(argv=argv),
                contextlib.redirect_stderr(io.StringIO()),
                self.assertRaises(SystemExit),
            ):
                M["parse_args"](argv)

    def test_credentials(self):
        with patch.dict(os.environ, {"NOTHING_API_KEY": "dummy"}, clear=True):
            self.assertEqual(M["credential"](M["parse_args"]([]))[0], "dummy")
            args = M["parse_args"](["--base-url", "https://other.example/v1"])
            self.assertIsNone(M["credential"](args)[0])

    def test_streams(self):
        events = {
            "chat": [{"choices": [{"delta": {"content": "hello"}}]}, "[DONE]"],
            "responses": [
                {"type": "response.output_text.delta", "delta": "hello"},
                {"type": "response.completed", "response": {"status": "completed"}},
            ],
            "messages": [
                {
                    "type": "content_block_delta",
                    "delta": {"type": "text_delta", "text": "hello"},
                },
                {"type": "message_stop"},
            ],
        }
        for api, items in events.items():
            lines = []
            for item in items:
                lines += [
                    "data: " + (item if isinstance(item, str) else json.dumps(item)),
                    "",
                ]
            self.assertEqual("".join(M["stream_text"](api, lines)), "hello")
            with self.assertRaises(ValueError):
                list(M["stream_text"](api, lines[:2]))
        with self.assertRaises(ValueError):
            list(M["stream_text"]("chat", ['data: {"error":{"message":"oops"}}', ""]))


class Handler(BaseHTTPRequestHandler):
    requests: ClassVar[list] = []

    def log_message(self, *_):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self.requests.append((self.path, dict(self.headers), body))
        if body["model"] == "fail":
            self.send_response(429)
            self.end_headers()
            self.wfile.write(b'{"error":{"message":"rate limited"}}')
            return
        api = self.path.rsplit("/", 1)[-1]
        if body["model"] in ("array", "badshape", "tool", "incomplete"):
            response = {
                "array": [],
                "badshape": {"choices": [None]},
                "tool": {"choices": [{"message": {"content": None, "tool_calls": []}}]},
                "incomplete": {
                    "status": "incomplete",
                    "output": [
                        {
                            "type": "message",
                            "content": [{"type": "output_text", "text": "partial"}],
                        }
                    ],
                    "incomplete_details": {"reason": "max_output_tokens"},
                },
            }[body["model"]]
            self.send_response(200)
            self.end_headers()
            self.wfile.write(json.dumps(response).encode())
            return
        if body["model"] == "flood":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            try:
                self.wfile.write(b"data: not-json\n\n")
                self.wfile.flush()
                self.wfile.write(b":" + b"x" * (8 * 1024 * 1024) + b"\n\n")
            except (BrokenPipeError, ConnectionResetError):
                pass
            return
        if body.get("stream"):
            events = {
                "completions": [
                    {"choices": [{"delta": {"content": "**hello**"}}]},
                    "[DONE]",
                ],
                "responses": [
                    {"type": "response.output_text.delta", "delta": "**hello**"},
                    {"type": "response.completed", "response": {"status": "completed"}},
                ],
                "messages": [
                    {
                        "type": "content_block_delta",
                        "delta": {"type": "text_delta", "text": "**hello**"},
                    },
                    {"type": "message_stop"},
                ],
            }[api]
            if body["model"] == "truncated":
                if api == "completions":
                    events[0]["choices"][0]["finish_reason"] = "length"
                elif api == "responses":
                    events[-1] = {
                        "type": "response.incomplete",
                        "response": {"status": "incomplete"},
                    }
                else:
                    events.insert(
                        -1,
                        {
                            "type": "message_delta",
                            "delta": {"stop_reason": "max_tokens"},
                        },
                    )
            result = "".join(
                "data: " + (x if isinstance(x, str) else json.dumps(x)) + "\n\n"
                for x in events
            )
        else:
            result = json.dumps(
                {
                    "completions": {"choices": [{"message": {"content": "**hello**"}}]},
                    "responses": {
                        "output": [
                            {
                                "type": "message",
                                "content": [
                                    {"type": "output_text", "text": "**hello**"}
                                ],
                            }
                        ]
                    },
                    "messages": {"content": [{"type": "text", "text": "**hello**"}]},
                }[api]
            )
            if body["model"] == "truncated":
                response = json.loads(result)
                if api == "completions":
                    response["choices"][0]["finish_reason"] = "length"
                elif api == "responses":
                    response["status"] = "incomplete"
                else:
                    response["stop_reason"] = "max_tokens"
                result = json.dumps(response)
        if body["model"] == "long":
            text = "hello\n\n" + "\n\n".join(f"line-{n:03}" for n in range(120))
            result = result.replace("**hello**", json.dumps(text)[1:-1])
        self.send_response(200)
        self.send_header(
            "Content-Type",
            "text/event-stream" if body.get("stream") else "application/json",
        )
        self.end_headers()
        self.wfile.write(result.encode())


class IntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.server.server_port}/v1"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def invoke(self, *args):
        env = {
            **os.environ,
            "LLM_API_KEY": "dummy-local-test",
            "NO_PROXY": "127.0.0.1",
            "no_proxy": "127.0.0.1",
        }
        return subprocess.run(
            [str(CLI), "--base-url", self.base, *args],
            check=False,
            input="",
            capture_output=True,
            text=True,
            env=env,
            timeout=20,
        )

    def test_all_apis_real_xh(self):
        for api in ("chat", "responses", "messages"):
            for stream in (False, True):
                with self.subTest(api=api, stream=stream):
                    args = ["-a", api, "hello"]
                    if stream:
                        args.append("--stream")
                    result = self.invoke(*args)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(result.stdout, "**hello**\n")
                    _, received_headers, body = Handler.requests[-1]
                    headers = {
                        key.lower(): value for key, value in received_headers.items()
                    }
                    self.assertEqual(body["model"], "big-pickle")
                    self.assertEqual(
                        headers.get(
                            "x-api-key" if api == "messages" else "authorization"
                        ),
                        "dummy-local-test"
                        if api == "messages"
                        else "Bearer dummy-local-test",
                    )

    def test_failure(self):
        for options in ([], ["--stream"]):
            result = self.invoke("-m", "fail", "hello", *options)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("429", result.stderr)

    def test_raw_json_nontext_and_incomplete(self):
        for model, api, code in (
            ("tool", "chat", 0),
            ("badshape", "chat", 0),
            ("incomplete", "responses", 3),
            ("fail", "chat", 1),
        ):
            result = self.invoke("--json", "-m", model, "-a", api, "hello")
            self.assertEqual(result.returncode, code, result.stderr)
            self.assertIsInstance(json.loads(result.stdout), dict)
            self.assertNotIn("Traceback", result.stderr)

    def test_malformed_shapes(self):
        for model in ("array", "badshape"):
            result = self.invoke("-m", model, "hello")
            self.assertEqual(result.returncode, 1, result.stderr)
            self.assertIn("expected a JSON object", result.stderr)
            self.assertNotIn("Traceback", result.stderr)

    def test_truncated_answers_are_saved(self):
        with tempfile.TemporaryDirectory() as directory:
            for api in ("chat", "responses", "messages"):
                for stream in (False, True):
                    dest = Path(directory) / f"{api}-{stream}"
                    args = ["-a", api, "-m", "truncated", "-o", str(dest), "hello"]
                    if stream:
                        args.append("--stream")
                    result = self.invoke(*args)
                    self.assertEqual(result.returncode, 3, result.stderr)
                    self.assertIn("incomplete", result.stderr)
                    self.assertIn("hello", result.stdout)
                    self.assertEqual(dest.read_text(), result.stdout)

    def test_bad_stream_followed_by_large_output_exits_promptly(self):
        start = time.monotonic()
        result = self.invoke("--stream", "-m", "flood", "hello")
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertLess(time.monotonic() - start, 5)
        self.assertNotIn("Traceback", result.stderr)

    def test_output_preflight_and_cleanup(self):
        with tempfile.TemporaryDirectory() as directory:
            dest = Path(directory) / "missing-parent" / "answer"
            before = len(Handler.requests)
            result = self.invoke("-o", str(dest), "hello")
            self.assertEqual(result.returncode, 1)
            self.assertEqual(len(Handler.requests), before)
            dest = Path(directory) / "answer"
            result = self.invoke("-m", "fail", "-o", str(dest), "hello")
            self.assertEqual(result.returncode, 1)
            self.assertFalse(dest.exists())
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_xh_preview_is_runnable(self):
        result = self.invoke("-x", "--prompt", "quotes ' \" $(false)\nUnicode: café")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("dummy-local-test", result.stdout)
        env = {**os.environ, "LLM_API_KEY": "dummy-local-test", "NO_PROXY": "127.0.0.1"}
        executed = subprocess.run(
            ["/bin/zsh", "-c", result.stdout],
            check=False,
            env=env,
            capture_output=True,
            text=True,
            timeout=20,
        )
        self.assertEqual(executed.returncode, 0, executed.stderr)
        self.assertIn("hello", executed.stdout)
        self.assertEqual(
            Handler.requests[-1][2]["messages"][-1]["content"],
            "quotes ' \" $(false)\nUnicode: café",
        )

    def terminal_output(self, model="big-pickle"):
        master, slave = pty.openpty()
        env = {
            **os.environ,
            "LLM_API_KEY": "dummy-local-test",
            "NO_PROXY": "localhost",
            "TERM": "xterm-256color",
        }
        try:
            with subprocess.Popen(
                [str(CLI), "--base-url", self.base, "--stream", "-m", model, "hello"],
                stdin=subprocess.DEVNULL,
                stdout=slave,
                stderr=subprocess.PIPE,
                env=env,
            ) as proc:
                os.close(slave)
                slave = None
                output = b""
                deadline = time.monotonic() + 10
                while proc.poll() is None:
                    if time.monotonic() >= deadline:
                        proc.kill()
                        proc.communicate(timeout=3)
                        self.fail("terminal CLI did not exit within 10 seconds")
                    if select.select([master], [], [], 5)[0]:
                        try:
                            output += os.read(master, 65536)
                        except OSError:
                            break
                _, errors = proc.communicate(timeout=10)
                self.assertEqual(proc.returncode, 0, errors.decode())
                self.assertIn(b"hello", output)
            body = Handler.requests[-1][2]
            self.assertEqual(body["messages"][0]["content"], M["DEFAULT_SYSTEM"])
            return output
        finally:
            os.close(master)
            if slave is not None:
                os.close(slave)

    def test_real_terminal_streaming(self):
        self.terminal_output()

    def test_long_terminal_preview_does_not_duplicate_scrollback(self):
        output = self.terminal_output("long")
        self.assertEqual(output.count(b"line-119"), 1)
        self.assertIn(b"line-000", output)

    def test_output_and_json(self):
        with tempfile.TemporaryDirectory() as directory:
            dest = Path(directory) / "result"
            result = self.invoke("--json", "-o", str(dest), "hello")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(dest.read_text()), json.loads(result.stdout))
            self.assertNotEqual(self.invoke("-o", str(dest), "hello").returncode, 0)


if __name__ == "__main__":
    unittest.main()
