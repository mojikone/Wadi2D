# Wadi2D QGIS plugin. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""The one dock: six sections, top to bottom, and the wiring between them and the engine."""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

from qgis.core import Qgis, QgsMessageLog
from qgis.gui import QgsDockWidget
from qgis.PyQt.QtCore import QUrl
from qgis.PyQt.QtGui import QDesktopServices
from qgis.PyQt.QtWidgets import QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget

from . import settings
from .engine_process import EngineQuery, EngineRun
from .job_builder import (
    SchemaView,
    build_job,
    hms_import_args,
    merge_hms,
    merge_notes,
    notes,
    problems,
    write_job,
)
from .live_layer import LiveLayer, load_maps, mark_cell, remove_marker
from .progress import run_is_live
from .protocol import (
    EXIT_STOPPED,
    engine_error_text,
    estimate_text,
    exit_message,
    next_run_dir,
    parse_estimate,
    run_args,
)
from .sections.boundaries import BoundariesSection
from .sections.hydrology import HydrologySection
from .sections.points import PointsSection
from .sections.run import RunSection
from .sections.structures import StructuresSection
from .sections.terrain import TerrainSection

LOG_TAG = "Wadi2D"
HMS_JOB = "hms_import.json"


class Wadi2DDock(QgsDockWidget):
    def __init__(self, iface, parent=None) -> None:
        super().__init__("Wadi2D", parent)
        self.setObjectName("Wadi2DDock")
        self.iface = iface
        self.schema: SchemaView | None = None
        self.run: EngineRun | None = None
        self.live = LiveLayer()
        self.marker = None
        self.results_dir: Path | None = None
        self._crs = ""
        self._query: EngineQuery | None = None
        self._schema_query: EngineQuery | None = None
        self._scratch: str | None = None

        self.terrain = TerrainSection(iface.mapCanvas())
        self.hydrology = HydrologySection()
        self.structures = StructuresSection()
        self.boundaries = BoundariesSection()
        self.points = PointsSection()
        self.panel = RunSection()
        self.sections = (
            self.terrain, self.hydrology, self.structures, self.boundaries, self.points, self.panel,
        )  # fmt: skip

        self.engine_label = QLabel("Looking for the engine...")
        self.engine_label.setWordWrap(True)
        self.engine_button = QPushButton("Engine...")
        top = QHBoxLayout()
        top.addWidget(self.engine_label, 1)
        top.addWidget(self.engine_button)
        body = QWidget()
        column = QVBoxLayout(body)
        column.addLayout(top)
        for section in self.sections:
            column.addWidget(section)
        column.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(body)
        self.setWidget(scroll)

        self.engine_button.clicked.connect(self.open_settings)
        self.panel.estimate_button.clicked.connect(self.estimate)
        self.panel.run_button.clicked.connect(self.start_run)
        self.panel.stop_button.clicked.connect(self.stop_run)
        self.panel.open_button.clicked.connect(self.open_results)
        self.panel.folder.fileChanged.connect(self._folder_chosen)
        self.panel.folder.setFilePath(settings.last_folder())

        self.load_engine()
        self.attach_if_live(settings.last_run())

    # The engine: defaults come from its schema, and nothing runs without them.

    def load_engine(self) -> None:
        self._set_ready(False)
        self.engine_label.setText("Looking for the engine...")
        self._schema_query = EngineQuery(settings.engine_text(), self)
        self._schema_query.done.connect(self._schema_read)
        self._schema_query.start(["schema"])

    def _schema_read(self, code: int, out: str, err: str) -> None:
        try:
            schema = SchemaView(json.loads(out))
        except ValueError:
            schema = None
        if code != 0 or schema is None:
            self.engine_label.setText("Engine not found. Press Engine... to set its path.")
            QgsMessageLog.logMessage(f"wadi2d schema: exit {code}. {err}", LOG_TAG, Qgis.Warning)
            return
        self.schema = schema
        for section in self.sections:
            section.apply_schema(schema)
        self.engine_label.setText("Engine ready.")
        self._set_ready(True)

    def _set_ready(self, ready: bool) -> None:
        idle = self.run is None
        self.panel.run_button.setEnabled(ready and idle)
        self.panel.estimate_button.setEnabled(ready and idle)

    def open_settings(self) -> None:
        dialog = settings.EngineDialog(self)
        if dialog.exec_():
            self.load_engine()

    # From the widgets to a job.

    def _collect(self) -> dict:
        dem = self.terrain.dem_layer()
        if dem is None:
            return {}
        crs = dem.crs()
        values: dict = {}
        for section in self.sections:
            values.update(section.values(crs))
        return values

    def _checked_values(self) -> dict | None:
        values = self._collect()
        found = problems(values)
        if found:
            self.panel.say(" ".join(found), "bad")
            return None
        return values

    def _prepare(self, values: dict, out: Path, then) -> None:
        """Write the job in ``out``, through ``hms-import`` for an HMS project, then call ``then(job_path)``."""
        job = build_job(values, out)
        hms = values.get("hms")
        if not hms:
            then(write_job(job, out))
            return
        imported = out / HMS_JOB
        out.mkdir(parents=True, exist_ok=True)

        def merged(code: int, _out: str, err: str) -> None:
            if code != 0:
                self._job_failed(f"The HMS project could not be read. {engine_error_text(err)}")
                return
            data = json.loads(imported.read_text(encoding="utf-8"))
            complete = merge_hms(job, data, hms)
            for note in merge_notes(job, complete):
                self.panel.say(note, "note")
            then(write_job(complete, out))

        self._query = EngineQuery(settings.engine_text(), self)
        self._query.done.connect(merged)
        self._query.start(hms_import_args(hms, imported))

    def _safely(self, values: dict, out: Path, then) -> None:
        try:
            self._prepare(values, out, then)
        except OSError as problem:
            self._job_failed(f"The job could not be written: {problem}")

    def _job_failed(self, text: str) -> None:
        self.panel.set_running(False)
        self._set_ready(self.schema is not None)
        self.panel.estimate_label.clear()
        self.panel.say(text, "bad")
        self._drop_scratch()

    # Estimate.

    def estimate(self) -> None:
        values = self._checked_values()
        if values is None:
            return
        self.panel.estimate_label.setText("Estimating...")
        self.panel.estimate_button.setEnabled(False)
        self._scratch = tempfile.mkdtemp(prefix="wadi2d_estimate_")
        values["output"] = self._scratch
        self._safely(values, Path(self._scratch), self._run_dry)

    def _run_dry(self, job: Path) -> None:
        self._query = EngineQuery(settings.engine_text(), self)
        self._query.done.connect(self._estimated)
        self._query.start(run_args(job, self._scratch, dry_run=True))

    def _estimated(self, code: int, out: str, err: str) -> None:
        self.panel.estimate_button.setEnabled(self.schema is not None)
        estimate = parse_estimate(out) if code == 0 else None
        if estimate is None:
            self.panel.estimate_label.setText(f"{exit_message(code)} {engine_error_text(err)}")
        else:
            self.panel.estimate_label.setText(estimate_text(estimate))
        self._drop_scratch()

    def _drop_scratch(self) -> None:
        if self._scratch:
            shutil.rmtree(self._scratch, ignore_errors=True)
            self._scratch = None

    # Run.

    def start_run(self) -> None:
        values = self._checked_values()
        if values is None:
            return
        self._clear_last_run()
        chosen = Path(values["output"])
        out = next_run_dir(chosen)
        values["name"] = out.name
        settings.set_last_folder(str(chosen))
        self.panel.set_running(True)
        messages = list(notes(values))
        if out != chosen:
            messages.insert(0, f"That folder already holds a run; this one goes to {out.name}.")
        self.panel.say(" ".join(messages) or "Starting...", "note" if messages else "info")
        self._crs = values["crs"]
        self._safely(values, out, lambda job: self._launch(job, out))

    def _launch(self, job: Path, out: Path) -> None:
        duration = json.loads(job.read_text(encoding="utf-8"))["run"]["duration_s"]
        self.run = EngineRun(settings.engine_text(), self)
        self._follow(self.run)
        settings.set_last_run(str(out))
        self.run.start(job, out, self._crs, duration)

    def attach_if_live(self, folder: str) -> bool:
        """Pick up a run already going in ``folder``, for instance after QGIS was restarted."""
        if self.run is not None or not folder or not run_is_live(folder):
            return False
        self.run = EngineRun("", self)
        self._follow(self.run)
        self.panel.set_running(True)
        self.panel.say(f"Following the run in {Path(folder).name}.", "note")
        settings.set_last_run(folder)
        self.run.attach(folder)
        return True

    def _follow(self, run: EngineRun) -> None:
        run.updated.connect(self._updated)
        run.received.connect(self._received)
        run.ended.connect(self._ended)

    def _folder_chosen(self, folder: str) -> None:
        self.attach_if_live(folder)

    def _updated(self, state) -> None:
        self.panel.show_state(state)
        if self.run is not None:
            self.live.update(self.run.out_dir)

    def _received(self, event: dict) -> None:
        if event.get("ev") == "warn":
            self.panel.say(str(event.get("message", "")), "note")

    def stop_run(self) -> None:
        if self.run is not None:
            self.panel.stop_button.setEnabled(False)
            self.panel.say("Stopping: the engine finishes the step and writes its maps.")
            self.run.stop()

    def _ended(self, state) -> None:
        run, self.run = self.run, None
        self.panel.set_running(False)
        self._set_ready(self.schema is not None)
        self.panel.show_state(state)
        self.live.clear()
        self.results_dir = run.out_dir
        loaded = load_maps(run.out_dir, run.out_dir.name)
        self.panel.open_button.setVisible(True)
        if state.succeeded:
            self.panel.bar.setValue(100)
        tone = "good" if state.succeeded else ("note" if state.exit_code == EXIT_STOPPED else "bad")
        self.panel.say(state.outcome(), tone)
        if state.error_xy:
            self.marker = mark_cell(self.iface.mapCanvas(), state.error_xy, run.crs)
        QgsMessageLog.logMessage(f"{run.out_dir}: {state.outcome()} ({len(loaded)} maps)", LOG_TAG, Qgis.Info)

    def _clear_last_run(self) -> None:
        remove_marker(self.iface.mapCanvas(), self.marker)
        self.marker = None
        self.panel.estimate_label.clear()

    def open_results(self) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.results_dir)))

    def release(self) -> None:
        """Leave a running engine alone: QGIS is closing or the plugin is being reloaded."""
        if self.run is not None:
            self.run.release()
            self.run = None
        self.live.clear()
        self._clear_last_run()
