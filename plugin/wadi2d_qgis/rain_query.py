# Wadi2D QGIS plugin. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""The Storm section's questions to the rest of the dock and to the engine (W65).

Preview rain writes the job a run would write, in a scratch folder, through the HMS import when there is one, and asks
``wadi2d rain-preview`` what each lumped subbasin and the 2D area take; the plugin computes none of it. The study's
storm areas are read from that section here, so the Storm section never knows another section.
"""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

from qgis.PyQt.QtCore import QObject

from . import settings
from .engine_process import EngineQuery
from .job_builder import LayerError, problems
from .protocol import engine_error_text, exit_message
from .storm_rows import preview_args

PREVIEW_FILE = "rain_preview.json"


class StormLinks(QObject):
    """Answers the Storm section's signals for the dock."""

    def __init__(self, dock) -> None:
        super().__init__(dock)
        self.dock = dock
        self.storm = dock.storm
        self._query: EngineQuery | None = None
        self._scratch: str | None = None
        self.storm.preview_requested.connect(self.preview)
        self.storm.study_areas_requested.connect(self.show_study_areas)

    def show_study_areas(self) -> None:
        study = self.dock.study
        study._refresh_areas()
        self.storm.show_study_areas(study.areas_label.text())

    # Preview rain

    def preview(self) -> None:
        say = self.storm.say_preview
        if self.dock.schema is None:
            say("The engine is not ready yet.")
            return
        try:
            values = self.dock._collect()
        except LayerError as error:
            say(str(error))
            return
        self._drop()
        self._scratch = tempfile.mkdtemp(prefix="wadi2d_rain_")
        values["output"] = self._scratch  # no output folder is needed to look at the rain
        found = problems(values)
        if found:
            self._drop()
            say(" ".join(found))
            return
        self.storm.set_previewing(True)
        self.dock._safely(values, Path(self._scratch), self._ask, self._failed, say)

    def _ask(self, job: Path) -> None:
        self._query = EngineQuery(settings.engine_text(), self)
        self._query.done.connect(self._answered)
        self._query.start(preview_args(job, Path(self._scratch) / PREVIEW_FILE))

    def _answered(self, code: int, _out: str, err: str) -> None:
        self.storm.set_previewing(False)
        try:
            if code != 0:
                raise ValueError(f"{exit_message(code)} {engine_error_text(err)}".strip())
            preview = json.loads((Path(self._scratch) / PREVIEW_FILE).read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError) as problem:
            self.storm.say_preview(f"The rain could not be previewed. {problem}")
        else:
            self.storm.show_preview(preview)
        finally:
            self._drop()

    def _failed(self, text: str) -> None:
        self.storm.set_previewing(False)
        self.storm.say_preview(text)
        self._drop()

    def _drop(self) -> None:
        if self._scratch:
            shutil.rmtree(self._scratch, ignore_errors=True)
            self._scratch = None
