# Wadi2D QGIS plugin. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""The engine as a process.

``EngineQuery`` runs one short command. ``EngineRun`` starts or re-attaches to a run; the progress file is its
only source of events, so both cases share one code path. No thread and no ``QgsTask``: the engine is already
another process and these signals arrive on the GUI thread.

Qt starts a console program with no window when QGIS has no console of its own, which is why ``QProcess`` is used
and ``startDetached`` is not: that one opens a console. Output goes to files, not pipes, so the engine keeps
running if QGIS closes.
"""

from __future__ import annotations

import os
import signal
from pathlib import Path

from qgis.PyQt.QtCore import QObject, QProcess, QProcessEnvironment, QTimer, pyqtSignal

from .progress import ProgressTail, RunState
from .protocol import (
    EXIT_FINISHED,
    EXIT_STOPPED,
    POLL_MS,
    PROGRESS_FILE,
    QUERY_TIMEOUT_S,
    STDERR_FILE,
    STDOUT_FILE,
    STOP_FILE,
    STOP_GRACE_S,
    clean_env,
    engine_error_text,
    parse_engine,
    pid_alive,
    read_run_info,
    run_args,
    write_run_info,
)

MILLISECONDS = 1000


def engine_environment() -> QProcessEnvironment:
    """The system environment without what QGIS added for its own interpreter."""
    system = QProcessEnvironment.systemEnvironment()
    names = system.keys()
    clean = QProcessEnvironment()
    for key, value in clean_env({name: system.value(name) for name in names}).items():
        clean.insert(key, value)
    return clean


class EngineQuery(QObject):
    """One short command. ``done`` carries the exit code (-1 if it never ran), stdout and stderr."""

    done = pyqtSignal(int, str, str)

    def __init__(self, engine_text: str, parent=None) -> None:
        super().__init__(parent)
        self._engine_text = engine_text
        self._process: QProcess | None = None
        self._timeout = QTimer(self)
        self._timeout.setSingleShot(True)
        self._timeout.timeout.connect(self._give_up)

    def start(self, args: list[str]) -> None:
        try:
            program, *base = parse_engine(self._engine_text)
        except ValueError as problem:
            reason = str(problem)
            QTimer.singleShot(0, lambda: self.done.emit(-1, "", reason))
            return
        self._process = QProcess(self)
        self._process.setProcessEnvironment(engine_environment())
        self._process.finished.connect(self._finished)
        self._process.errorOccurred.connect(self._failed)
        self._timeout.start(QUERY_TIMEOUT_S * MILLISECONDS)
        self._process.start(program, [*base, *args])

    def _text(self, data) -> str:
        return bytes(data).decode("utf-8", "replace")

    def _finished(self, code: int, _status=None) -> None:
        self._timeout.stop()
        process = self._process
        out = self._text(process.readAllStandardOutput())
        err = self._text(process.readAllStandardError())
        self.done.emit(code, out, err)

    def _failed(self, error) -> None:
        if error == QProcess.FailedToStart:
            self._timeout.stop()
            self.done.emit(-1, "", self._process.errorString())

    def _give_up(self) -> None:
        if self._process is not None:
            self._process.kill()


class _ReleasableProcess(QProcess):
    def forget(self) -> None:
        """Drop the child without killing it; a QProcess destroyed while running would kill it."""
        self.setProcessState(QProcess.NotRunning)


class EngineRun(QObject):
    """One run folder. ``updated`` carries the state on every poll with news, ``ended`` the final state."""

    received = pyqtSignal(dict)
    updated = pyqtSignal(object)
    ended = pyqtSignal(object)

    def __init__(self, engine_text: str = "", parent=None) -> None:
        super().__init__(parent)
        self._engine_text = engine_text
        self.out_dir: Path | None = None
        self.state = RunState()
        self.crs = ""
        self.pid: int | None = None
        self.stop_grace_ms = STOP_GRACE_S * MILLISECONDS
        self._process: _ReleasableProcess | None = None
        self._tail: ProgressTail | None = None
        self._closed = False
        self._killed = False
        self._poll_timer = QTimer(self)
        self._poll_timer.timeout.connect(self._poll)
        self._kill_timer = QTimer(self)
        self._kill_timer.setSingleShot(True)
        self._kill_timer.timeout.connect(self._kill)

    def _watch(self, out_dir: Path | str) -> None:
        self.out_dir = Path(out_dir)
        self._tail = ProgressTail(self.out_dir / PROGRESS_FILE)
        self._poll_timer.start(POLL_MS)

    def start(
        self, job: Path | str, out_dir: Path | str, crs: str, t_end: float, resume: bool = False
    ) -> None:
        program, *base = parse_engine(self._engine_text)
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        (out / STOP_FILE).unlink(missing_ok=True)
        self.crs = crs
        self.state = RunState(t_end=t_end)
        process = _ReleasableProcess(self)
        process.setProcessEnvironment(engine_environment())
        process.setStandardOutputFile(str(out / STDOUT_FILE))
        process.setStandardErrorFile(str(out / STDERR_FILE))
        process.started.connect(self._started)
        process.finished.connect(self._exited)
        process.errorOccurred.connect(self._failed)
        self._process = process
        self._watch(out)
        process.start(program, [*base, *run_args(job, out, resume=resume)])

    def attach(self, out_dir: Path | str) -> None:
        """Follow a run this object did not start; the events replay from the top of the file."""
        info = read_run_info(out_dir)
        self.crs = info.get("crs", "")
        self.pid = info.get("pid")
        self.state = RunState(t_end=info.get("t_end"))
        self._watch(out_dir)
        self._poll()

    def _started(self) -> None:
        self.pid = int(self._process.processId())
        write_run_info(self.out_dir, self.pid, self.crs, self.state.t_end)

    def _drain(self) -> None:
        for event in self._tail.poll():
            self.state.apply(event)
            self.received.emit(event)
        self.updated.emit(self.state)

    def _poll(self) -> None:
        self._drain()
        if self._process is not None:
            if self.state.finished and not self._kill_timer.isActive():
                self._kill_timer.start(self.stop_grace_ms)  # said done, so it must exit
            return
        gone = not pid_alive(self.pid) if self.pid else bool(self.state.error)
        if self.state.finished or gone:
            self._drain()
            self._close(self.state.exit_code)

    def stop(self) -> None:
        """Ask for a stop: the engine finishes the step, writes its maps and exits; killed if it does not."""
        if self.out_dir is None or self._closed:
            return
        (self.out_dir / STOP_FILE).touch()
        if not self._kill_timer.isActive():
            self._kill_timer.start(self.stop_grace_ms)

    def _kill(self) -> None:
        self._killed = True
        if self._process is not None:
            self._process.kill()  # the exit signal closes the run
            return
        if self.pid and pid_alive(self.pid):
            os.kill(self.pid, signal.SIGTERM)  # TerminateProcess on Windows
        self._close(self.state.exit_code)

    def _exited(self, code: int, _status=None) -> None:
        self._poll_timer.stop()
        self._drain()
        self._close(self.state.exit_code if self.state.exit_code is not None else code)

    def _failed(self, error) -> None:
        if error == QProcess.FailedToStart:
            self.state.message = f"The engine could not be started: {self._process.errorString()}"
            self._close(None)

    def _close(self, code: int | None) -> None:
        if self._closed:
            return
        self._closed = True
        self._poll_timer.stop()
        self._kill_timer.stop()
        self.state.exit_code = code
        if self._killed and not self.state.finished:
            self.state.message = "The engine did not stop in time and was killed."
        elif not self.state.error and code not in (EXIT_FINISHED, EXIT_STOPPED, None):
            self.state.error = self._stderr_text()  # stderr of a clean end is only library chatter
        self.state.finished = True
        self.ended.emit(self.state)

    def _stderr_text(self) -> str | None:
        try:
            text = (self.out_dir / STDERR_FILE).read_text(encoding="utf-8", errors="replace")
        except OSError:
            return None
        return engine_error_text(text) or None

    def release(self) -> None:
        """QGIS is closing or the plugin is unloading: leave the engine running, re-attach later."""
        self._poll_timer.stop()
        self._kill_timer.stop()
        self._closed = True
        if self._process is not None:
            self._process.finished.disconnect(self._exited)
            self._process.errorOccurred.disconnect(self._failed)
            self._process.forget()
            self._process = None
