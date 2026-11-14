# Wadi2D QGIS plugin. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""The engine's drawing process for one finished run (``wadi2d render``), kept open, asked one drawing at a time.

No Qt and no QGIS here. QGIS draws a layer on its own threads and wants the picture back before the call returns, so the
question and the answer are plain pipes behind one lock, not a ``QProcess``, which belongs to the thread that made it.
The program, its arguments and its environment come from the same place as every other engine command
(:func:`protocol.parse_engine`, :func:`protocol.clean_env`), and the process starts with no window, as ``QProcess`` does.
One process serves every layer and every Identify on its run, and ends when its input closes, so it never outlives QGIS.
"""

from __future__ import annotations

import contextlib
import json
import os
import subprocess
import tempfile
import threading
from pathlib import Path

from .protocol import clean_env, engine_error_text, parse_engine, render_args

READY_TIMEOUT_S = 600.0
"""A run whose tables are gone has them built again first: as long as before its run."""
QUIT_WAIT_S = 3.0


class RenderError(RuntimeError):
    """The process is not there, or not ready, or said something that is not the protocol."""


class RenderClient:
    def __init__(self, engine_text: str, run: Path | str, backend: str | None = None) -> None:
        self.engine_text = engine_text
        self.run = Path(run)
        self.backend = backend
        self.ready: dict | None = None
        """What the process said first: frames, extent, CRS, how fine the run can be drawn."""
        self.error: str | None = None
        self.waiting = ""
        """The last thing the process said while it got ready."""
        self._process: subprocess.Popen | None = None
        self._lock = threading.Lock()
        self._said = threading.Event()
        self._stderr_path: Path | None = None

    # Starting.

    def start(self) -> RenderClient:
        program, *base = parse_engine(self.engine_text)
        handle, name = tempfile.mkstemp(prefix="wadi2d_render_", suffix=".err")
        self._stderr_path = Path(name)
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            with os.fdopen(handle, "wb") as stderr:
                self._process = subprocess.Popen(
                    [program, *base, *render_args(self.run, self.backend)],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=stderr,
                    env=clean_env(dict(os.environ)),
                    creationflags=flags,
                )
        except OSError as problem:
            self.error = f"The engine could not be started: {problem}"
            self._said.set()
            return self
        threading.Thread(target=self._read_ready, name="wadi2d-render-ready", daemon=True).start()
        return self

    def _read_ready(self) -> None:
        try:
            while True:
                line = self._process.stdout.readline()
                if not line:
                    self.error = self._ended_text()
                    return
                head = json.loads(line)
                if head.get("ev") == "wait":
                    self.waiting = str(head.get("message", ""))
                elif head.get("ev") == "ready":
                    self.ready = head
                    return
                elif head.get("ev") == "error":
                    self.error = str(head.get("message", "The drawing process refused this run."))
                    return
        except (OSError, ValueError) as problem:
            self.error = f"The drawing process said something unreadable: {problem}"
        finally:
            self._said.set()

    def _ended_text(self) -> str:
        try:
            text = self._stderr_path.read_text(encoding="utf-8", errors="replace") if self._stderr_path else ""
        except OSError:
            text = ""
        return engine_error_text(text) or "The drawing process ended before it was ready."

    def wait_ready(self, timeout_s: float = READY_TIMEOUT_S) -> bool:
        """Block until the process is ready or has failed; True when ready."""
        self._said.wait(timeout_s)
        return self.ready is not None

    @property
    def settled(self) -> bool:
        """Ready, or failed: either way there is nothing more to wait for."""
        return self._said.is_set()

    @property
    def alive(self) -> bool:
        return self._process is not None and self._process.poll() is None and self.error is None

    # Asking.

    def ask(self, request: dict) -> tuple[dict, bytes]:
        """One request and its answer: the head as a dict and the bytes after it. Safe from any thread."""
        if self.ready is None:
            raise RenderError(self.error or "The drawing process is not ready yet.")
        with self._lock:
            if not self.alive:
                raise RenderError(self.error or self._ended_text())
            try:
                self._process.stdin.write(json.dumps(request).encode("utf-8") + b"\n")
                self._process.stdin.flush()
                line = self._process.stdout.readline()
                if not line:
                    raise OSError("no answer")
                head = json.loads(line)
                size = int(head.get("bytes", 0))
                payload = self._read_exactly(size)
            except (OSError, ValueError) as problem:
                self.error = f"The drawing process stopped answering ({problem}). {self._ended_text()}"
                raise RenderError(self.error) from problem
        return head, payload

    def _read_exactly(self, size: int) -> bytes:
        parts, left = [], size
        while left > 0:
            part = self._process.stdout.read(left)
            if not part:
                raise OSError("the answer was cut short")
            parts.append(part)
            left -= len(part)
        return b"".join(parts)

    def close(self) -> None:
        process, self._process = self._process, None
        if process is None:
            return
        try:
            if process.poll() is None:
                with self._lock:
                    process.stdin.write(b'{"op": "quit"}\n')
                    process.stdin.flush()
                    process.stdin.close()
                process.wait(QUIT_WAIT_S)
        except (OSError, ValueError, subprocess.TimeoutExpired):
            process.kill()
        if self._stderr_path is not None:
            with contextlib.suppress(OSError):
                self._stderr_path.unlink(missing_ok=True)
        self.error = self.error or "The drawing process was closed."


_clients: dict[str, RenderClient] = {}


def _key(run: Path | str) -> str:
    return os.path.normcase(os.path.abspath(str(run)))


def client_for(run: Path | str, engine_text: str, backend: str | None = None) -> RenderClient:
    """The open process of this run, or a new one started; a failed or closed one is replaced."""
    key = _key(run)
    held = _clients.get(key)
    if held is not None and (held.alive or not held.settled):
        return held
    if held is not None:
        held.close()
    made = RenderClient(engine_text, run, backend).start()
    _clients[key] = made
    return made


def existing(run: Path | str) -> RenderClient | None:
    return _clients.get(_key(run))


def close_all() -> None:
    for client in list(_clients.values()):
        client.close()
    _clients.clear()
