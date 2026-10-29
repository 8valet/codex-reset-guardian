from __future__ import annotations

import json
import os
import queue
import shutil
import subprocess
import threading
import time
from typing import Any


class RPCError(RuntimeError):
    def __init__(self, error: Any):
        self.error = error
        super().__init__(json.dumps(error, separators=(",", ":"), default=str))


def resolve_codex_path(codex_path: str | None = None) -> str | None:
    """Resolve the Codex CLI path for interactive and background-service use."""
    return (
        codex_path
        or os.environ.get("CODEX_RESET_GUARDIAN_CODEX")
        or shutil.which("codex")
    )


class CodexAppServer:
    """Synchronous JSON-RPC client for the local Codex App Server."""

    def __init__(
        self,
        codex_path: str | None = None,
        command: list[str] | None = None,
    ) -> None:
        if command is None:
            codex = resolve_codex_path(codex_path)
            if not codex:
                raise RuntimeError(
                    "codex CLI not found; install Codex or set "
                    "CODEX_RESET_GUARDIAN_CODEX"
                )
            command = [codex, "app-server", "--stdio"]

        self.proc = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            bufsize=1,
        )
        self.next_id = 1
        self._messages: queue.Queue[dict[str, Any] | None] = queue.Queue()
        self._backlog: dict[int, dict[str, Any]] = {}
        self._reader = threading.Thread(
            target=self._read_stdout,
            name="codex-appserver-reader",
            daemon=True,
        )
        self._reader.start()

        init = self.request(
            "initialize",
            {
                "clientInfo": {
                    "name": "codex-reset-guardian",
                    "version": "0.1.0",
                },
                "capabilities": {"experimentalApi": False},
            },
            timeout=15,
        )
        if not isinstance(init, dict):
            raise RuntimeError("unexpected initialize response")
        self.notify("initialized", {})

    def _read_stdout(self) -> None:
        assert self.proc.stdout is not None
        try:
            for line in self.proc.stdout:
                try:
                    message = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(message, dict):
                    self._messages.put(message)
        finally:
            self._messages.put(None)

    def _send(self, payload: dict[str, Any]) -> None:
        assert self.proc.stdin is not None
        self.proc.stdin.write(json.dumps(payload, separators=(",", ":")) + "\n")
        self.proc.stdin.flush()

    def notify(self, method: str, params: Any | None = None) -> None:
        message: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            message["params"] = params
        self._send(message)

    def request(
        self,
        method: str,
        params: Any | None = None,
        timeout: float = 25,
    ) -> Any:
        request_id = self.next_id
        self.next_id += 1

        message: dict[str, Any] = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
        }
        if params is not None:
            message["params"] = params

        self._send(message)
        deadline = time.monotonic() + timeout

        while True:
            reply = self._backlog.pop(request_id, None)
            if reply is None:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError(f"{method} timed out")
                try:
                    reply = self._messages.get(timeout=remaining)
                except queue.Empty:
                    raise TimeoutError(f"{method} timed out") from None
                if reply is None:
                    raise RuntimeError(
                        f"app-server exited while waiting for {method}"
                    )

            reply_id = reply.get("id")
            if reply_id != request_id:
                if isinstance(reply_id, int):
                    self._backlog[reply_id] = reply
                continue

            if "error" in reply:
                raise RPCError(reply["error"])
            return reply.get("result")

    def close(self) -> None:
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(timeout=2)

        for stream in (self.proc.stdin, self.proc.stdout):
            try:
                if stream is not None:
                    stream.close()
            except Exception:
                pass

        if self._reader.is_alive():
            self._reader.join(timeout=1)

    def __enter__(self) -> "CodexAppServer":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


def read_limits() -> dict[str, Any]:
    with CodexAppServer() as rpc:
        result = rpc.request(
            "account/rateLimits/read",
            {"excludeResetCreditDetails": False},
            timeout=25,
        )
    if not isinstance(result, dict):
        raise RuntimeError("account/rateLimits/read returned a non-object")
    return result
