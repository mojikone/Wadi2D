# Wadi2D QGIS plugin. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""A depth-area study as the dock follows it: the study's own progress file, and the progress file of the run it is
on, which the study names in its ``run`` event. No Qt, no QGIS."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .progress import ProgressTail, RunState
from .protocol import EXIT_FINISHED, EXIT_STOPPED, PROGRESS_FILE, exit_message


def _runs(n: int) -> str:
    return f"{n} run" if n == 1 else f"{n} runs"


@dataclass
class StudyState:
    """Everything the dock shows about a study. The fields below the line are the ones ``EngineRun`` reads and sets."""

    base: Path | None = None
    areas: list[float] = field(default_factory=list)
    table_type: str = ""
    index: int = 0
    of: int = 0
    area_km2: float | None = None
    run: RunState | None = None
    done_runs: int = 0
    failed_area: float | None = None
    rows: int | None = None
    warnings: list[str] = field(default_factory=list)
    _folder: str | None = None
    _tail: ProgressTail | None = field(default=None, repr=False)
    # ---
    t_end: float | None = None
    error: str | None = None
    error_xy: tuple[float, float] | None = None
    finished: bool = False
    exit_code: int | None = None
    message: str = ""

    def apply(self, event: dict) -> None:
        kind = event.get("ev")
        if kind == "start":
            self.areas = [float(a) for a in event.get("areas_km2") or []]
            self.of = len(self.areas)
            self.table_type = str(event.get("arf_table_type") or "")
        elif kind == "run":
            self.poll_run()  # what the last run still had to say
            self.index, self.of = int(event.get("index", self.index + 1)), int(event.get("of", self.of))
            self.area_km2 = event.get("area_km2")
            self._folder = event.get("folder")
            self._tail = None
            self.run = RunState()
        elif kind == "output" and event.get("kind") == "run":
            self.poll_run()
            if event.get("code") == EXIT_FINISHED:
                self.done_runs += 1
        elif kind == "warn":
            self._warn(event)
        elif kind == "error":
            self.poll_run()
            self.error = str(event.get("message", ""))
            self.exit_code = event.get("code", self.exit_code)
            self.failed_area = event.get("area_km2")
            if self.run is not None and self.failed_area is not None:
                self.error_xy = self.run.error_xy
        elif kind == "done":
            self.poll_run()
            self.exit_code = event.get("code", self.exit_code)
            self.rows = event.get("rows", self.rows)
            self.finished = True

    def _warn(self, event: dict) -> None:
        self.warnings.append(str(event.get("message", "")))

    def poll_run(self) -> None:
        """Fold what the run in progress wrote since the last poll; its warnings count for the study."""
        if self.run is None or not self._folder or self.base is None:
            return
        if self._tail is None:
            self._tail = ProgressTail(Path(self.base) / self._folder / PROGRESS_FILE)
        for event in self._tail.poll():
            self.run.apply(event)
            if event.get("ev") == "warn":
                self._warn(event)

    @property
    def percent(self) -> int:
        if not self.of:
            return 0
        part = self.run.percent / 100.0 if self.run is not None and self.index > self.done_runs else 0.0
        return max(0, min(100, int(100 * (self.done_runs + part) / self.of)))

    @property
    def status(self) -> str:
        """Which run of how many, how many are left, and the run's own line."""
        if not self.of:
            return "Building the grid, which every run of the study shares..."
        if not self.index:
            return f"{_runs(self.of)} to go."
        after = self.of - self.index
        rest = "the last run" if not after else f"{_runs(after)} left after it"
        head = f"Run {self.index} of {self.of}, storm area {self.area_km2:.4g} km2; {rest}."
        return f"{head} {self.run.status}" if self.run is not None else head

    @property
    def succeeded(self) -> bool:
        return self.exit_code == EXIT_FINISHED

    def outcome(self) -> str:
        """The plain end-of-study message: what happened, the engine's words, and the runs' warnings."""
        if self.succeeded:
            flows = "design flow" if self.rows == 1 else "design flows"
            words = [f"Finished: {_runs(self.of)}, {self.rows} {flows}, for design lines and lumped elements."]
        elif self.exit_code == EXIT_STOPPED and not self.message:
            words = [
                f"Stopped after {self.done_runs} of {_runs(self.of)}. A stopped study writes no design table, because "
                "it needs every storm area; the finished runs stay in its runs folder."
            ]
        else:
            words = [self.message or exit_message(self.exit_code)]
            if self.error:
                words.append(self.error.rstrip(". ") + ".")
            if self.failed_area is not None:
                words.append(f"In the run at a storm area of {self.failed_area:.4g} km2.")
        words.extend(warning.rstrip(". ") + "." for warning in dict.fromkeys(self.warnings))
        return " ".join(words)
