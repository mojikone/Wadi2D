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
from .layer_groups import model_name
from .protocol import engine_error_text, exit_message
from .rain_layers import load_rain_map
from .storm_rows import preview_args

PREVIEW_FILE = "rain_preview.json"
MAP_PREFIX = "wadi2d_storm_map_"


class StormLinks(QObject):
    """Answers the Storm section's signals for the dock."""

    def __init__(self, dock) -> None:
        super().__init__(dock)
        self.dock = dock
        self.storm = dock.storm
        self._query: EngineQuery | None = None
        self._scratch: str | None = None
        self._map_dir: str | None = None
        self._map_shown: str | None = None
        self.storm.preview_requested.connect(self.preview)
        dock.reduction.study_areas_requested.connect(self.show_study_areas)  # the 2D part's study (W101)

    def show_study_areas(self) -> None:
        study = self.dock.study
        study._refresh_areas()
        self.dock.reduction.show_study_areas(study.areas_label.text())

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
        self._map_dir = tempfile.mkdtemp(prefix=MAP_PREFIX)  # kept while its layers are on the map
        self._query.start(preview_args(job, Path(self._scratch) / PREVIEW_FILE, self._map_dir))

    def _draw_map(self) -> None:
        """The storm map into Inputs > Hydrology, in place of the last; the last one's files go with it."""
        shown, self._map_shown = self._map_shown, self._map_dir
        try:
            load_rain_map(self._map_dir, model_name(self.dock.panel.folder.filePath() or None))
        except (OSError, ValueError, KeyError) as problem:
            self.storm.say_preview(f"{self.storm.preview_label.text()} The storm map could not be drawn: {problem}")
        if shown and shown != self._map_dir:
            shutil.rmtree(shown, ignore_errors=True)

    def _answered(self, code: int, _out: str, err: str) -> None:
        self.storm.set_previewing(False)
        try:
            if code != 0:
                raise ValueError(f"{exit_message(code)} {engine_error_text(err)}".strip())
            preview = json.loads((Path(self._scratch) / PREVIEW_FILE).read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError) as problem:
            self.storm.say_preview(f"The rain could not be previewed. {problem}")
            if self._map_dir != self._map_shown:
                shutil.rmtree(self._map_dir, ignore_errors=True)
        else:
            self.storm.show_preview(preview)
            self._draw_map()
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
