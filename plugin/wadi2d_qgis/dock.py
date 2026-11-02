# Wadi2D QGIS plugin. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""The one dock: seven sections, top to bottom, and the wiring between them and the engine."""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

from qgis.core import Qgis, QgsMessageLog, QgsProject
from qgis.gui import QgsDockWidget
from qgis.PyQt.QtCore import Qt, QUrl
from qgis.PyQt.QtGui import QDesktopServices
from qgis.PyQt.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from . import settings
from .engine_process import EngineQuery, EngineRun
from .job_builder import (
    LayerError,
    SchemaView,
    build_job,
    hms_import_args,
    merge_hms,
    merge_notes,
    notes,
    problems,
    write_job,
)
from .live_layer import LiveLayer, load_maps, mark_cell, remove_marker, show_mesh
from .map_sheets import build_book, export_pdf, sheets_file
from .preview import TerrainPreview
from .profile_view import ProfileDialog
from .progress import run_is_live
from .protocol import (
    EXIT_STOPPED,
    FRAMES_TIMEOUT_S,
    engine_error_text,
    estimate_text,
    exit_message,
    mesh_args,
    mesh_text,
    next_run_dir,
    parse_estimate,
    parse_mesh,
    run_args,
)
from .result_layers import has_products, load_cell_grid, load_products
from .time_layer import has_results, load_frames
from .sections.boundaries import BoundariesSection
from .sections.hydrology import HydrologySection
from .sections.mesh import MeshSection
from .sections.points import PointsSection
from .sections.run import RunSection
from .sections.structures import StructuresSection
from .sections.terrain import TerrainSection

LOG_TAG = "Wadi2D"
HMS_JOB = "hms_import.json"

FIRST_START_NOTE = "The first estimate can take a minute while the engine starts."
FRAMES_NOTE = (
    "Use the Temporal Controller to step through the flood. These are cells; the pixel rasters stay the numbers of record. "
    "The date on the slider is a stand-in: 1 January 2000, 00:00, is the start of the run."
)


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
        self._mesh_layer: str | None = None
        self._mesh_folder: str | None = None
        self._mesh_folder_next = ""
        self._book = None

        self.terrain = TerrainSection(iface.mapCanvas())
        self.mesh = MeshSection()
        self.hydrology = HydrologySection()
        self.structures = StructuresSection()
        self.boundaries = BoundariesSection()
        self.points = PointsSection()
        self.panel = RunSection()
        self.sections = (
            self.terrain, self.mesh, self.hydrology, self.structures, self.boundaries, self.points, self.panel,
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
        self.mesh.preview_button.clicked.connect(self.preview_mesh)
        self.panel.run_button.clicked.connect(self.start_run)
        self.panel.stop_button.clicked.connect(self.stop_run)
        self.panel.open_button.clicked.connect(self.open_results)
        self.panel.map_button.clicked.connect(self.make_map)
        self.panel.frames_button.clicked.connect(self.time_slider)
        self.panel.folder.fileChanged.connect(self._folder_chosen)
        self.panel.folder.setFilePath(settings.last_folder())
        self.preview = TerrainPreview(iface.mapCanvas(), self)
        self.preview.finished.connect(self._previewed)
        self.structures.preview_button.clicked.connect(self.preview_terrain)
        self.structures.profile_button.clicked.connect(self.show_profile)

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
            self.engine_label.setText("Engine not found. Run install_wadi2d.bat from the release, or press Engine... to set its path.")
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
        self.mesh.preview_button.setEnabled(ready and idle and self.mesh.enabled.isChecked())

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
        try:
            values = self._collect()
        except LayerError as error:
            self.panel.say(str(error), "bad")
            return None
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
        self.panel.status.clear()
        self.panel.say(text, "bad")
        self._drop_scratch()

    # Estimate.

    def estimate(self) -> None:
        values = self._checked_values()
        if values is None:
            return
        self.panel.estimate_label.setText("Estimating...")
        self.panel.status.setText(FIRST_START_NOTE)
        self.panel.estimate_button.setEnabled(False)
        self._scratch = tempfile.mkdtemp(prefix="wadi2d_estimate_")
        values["output"] = self._scratch
        self._safely(values, Path(self._scratch), self._run_dry)

    def _run_dry(self, job: Path) -> None:
        self._query = EngineQuery(settings.engine_text(), self)
        self._query.done.connect(self._estimated)
        self._query.start(run_args(job, self._scratch, dry_run=True))

    def _estimated(self, code: int, out: str, err: str) -> None:
        self.panel.status.clear()
        self.panel.estimate_button.setEnabled(self.schema is not None)
        estimate = parse_estimate(out) if code == 0 else None
        if estimate is None:
            self.panel.estimate_label.setText(f"{exit_message(code)} {engine_error_text(err)}")
        else:
            self.panel.estimate_label.setText(estimate_text(estimate))
        self._drop_scratch()

    # Mesh preview.

    def preview_mesh(self) -> None:
        values = self._checked_values()
        if values is None:
            return
        if not values.get("mesh"):
            self.mesh.summary.setText("Tick the mesh first.")
            return
        self.mesh.preview_button.setEnabled(False)
        self.mesh.summary.setText("Reading the ground and the streams...")
        self._scratch = tempfile.mkdtemp(prefix="wadi2d_estimate_")
        values["output"] = self._scratch
        self._safely(values, Path(self._scratch), self._run_mesh)

    def _run_mesh(self, job: Path) -> None:
        folder = tempfile.mkdtemp(prefix="wadi2d_mesh_")
        self._mesh_folder_next = folder
        self._query = EngineQuery(settings.engine_text(), self)
        self._query.done.connect(self._meshed)
        self._query.start(mesh_args(job, folder))

    def _meshed(self, code: int, out: str, err: str) -> None:
        self.mesh.preview_button.setEnabled(self.schema is not None and self.mesh.enabled.isChecked())
        self._drop_scratch()
        event = parse_mesh(out) if code == 0 else None
        if event is None:
            self.mesh.summary.setText(f"{exit_message(code)} {engine_error_text(err)}")
            shutil.rmtree(self._mesh_folder_next, ignore_errors=True)
            return
        summary = json.loads(Path(event["summary"]).read_text(encoding="utf-8"))
        sizes = [float(size.split()[0]) for size in summary["tiles_by_size"]]
        self._mesh_layer = show_mesh(event["raster"], sizes, self._mesh_layer)
        if self._mesh_folder:
            shutil.rmtree(self._mesh_folder, ignore_errors=True)
        self._mesh_folder = self._mesh_folder_next
        self.mesh.summary.setText(mesh_text(summary))

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
        if self.attach_if_live(folder) or self.run is not None:
            return
        if folder and has_products(folder):  # a finished run: its sheets can be made at any time
            self.results_dir = Path(folder)
            self.panel.map_button.setEnabled(True)
        if folder and has_results(folder):
            self.results_dir = Path(folder)
            self.panel.frames_button.setEnabled(True)

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

    # Preview: the terrain as the objects leave it, with no run.

    def preview_terrain(self) -> None:
        box = self.structures
        try:
            values = self._collect()
        except LayerError as error:
            box.preview_label.setText(str(error))
            return
        box.preview_button.setEnabled(False)
        box.profile_button.hide()
        box.preview_label.setText("Working out the terrain...")
        self.preview.start(values)

    def _previewed(self, text: str, worked: bool) -> None:
        box = self.structures
        box.preview_button.setEnabled(True)
        box.preview_label.setText(text)
        box.profile_button.setVisible(worked and bool(self.preview.data))

    def show_profile(self) -> None:
        ProfileDialog(self.preview.data, self).exec_()

    def _ended(self, state) -> None:
        run, self.run = self.run, None
        self.panel.set_running(False)
        self._set_ready(self.schema is not None)
        self.panel.show_state(state)
        self.live.clear()
        self.results_dir = run.out_dir
        products = has_products(run.out_dir)
        loaded = load_maps(run.out_dir, run.out_dir.name, tucked=products)
        if products:
            load_products(run.out_dir, run.out_dir.name)
        load_cell_grid(run.out_dir, run.out_dir.name)
        self.panel.open_button.setVisible(bool(loaded))
        self.panel.map_button.setEnabled(products)
        self.panel.frames_button.setEnabled(has_results(run.out_dir))
        if state.succeeded:
            self.panel.bar.setValue(100)
        calm = state.succeeded and not state.warnings
        tone = "good" if calm else ("note" if state.succeeded or state.exit_code == EXIT_STOPPED else "bad")
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

    # The map sheets. QGIS's layout export belongs to the main thread, so this waits: seconds on a small run, about
    # 2 min on 15,000 km2.

    def make_map(self) -> None:
        if self.results_dir is None:
            return
        self.panel.say("Making the map...")
        QApplication.setOverrideCursor(Qt.WaitCursor)
        QApplication.processEvents()
        try:
            self._drop_book()
            self._book = build_book(
                self.results_dir, self.panel.map_title.text(), self.panel.background.currentData()
            )
            path = export_pdf(self._book, sheets_file(self.results_dir))
            self._book.layout.setName(f"Wadi2D {self.results_dir.name}")
            QgsProject.instance().layoutManager().addLayout(self._book.layout)
        except (OSError, ValueError, RuntimeError, KeyError) as problem:
            self.panel.say(f"The map could not be made: {problem}", "bad")
        else:
            self.panel.say(f"Map written: {path}", "good")
        finally:
            QApplication.restoreOverrideCursor()

    # The time slider: the engine writes the file, QGIS reads it. Reading a large mesh holds QGIS up, so that says so first.

    def time_slider(self) -> None:
        if self.results_dir is None:
            return
        self.panel.frames_button.setEnabled(False)
        self.panel.say("Writing the saved frames to one file...")
        self._query = EngineQuery(settings.engine_text(), self)
        self._query.done.connect(self._frames_written)
        self._query.start(["frames", str(self.results_dir)], FRAMES_TIMEOUT_S)

    def _frames_written(self, code: int, _out: str, err: str) -> None:
        self.panel.frames_button.setEnabled(True)
        if code != 0:
            self.panel.say(f"{exit_message(code)} {engine_error_text(err)}", "bad")
            return
        self.panel.say("Reading the frames into QGIS. A large run takes minutes, and QGIS waits meanwhile.")
        QApplication.setOverrideCursor(Qt.WaitCursor)
        QApplication.processEvents()
        try:
            layer = load_frames(self.results_dir, self.iface.mapCanvas(), self.iface.mainWindow())
        finally:
            QApplication.restoreOverrideCursor()
        if layer is None:
            self.panel.say("QGIS could not read the frames file.", "bad")
        else:
            self.panel.say(FRAMES_NOTE, "good")

    def _drop_book(self) -> None:
        """The last sheets and the layers that only they use; layouts of the same name go too."""
        if self._book is None:
            return
        project = QgsProject.instance()
        manager = project.layoutManager()
        for layout in manager.printLayouts():
            if layout is self._book.layout or layout.name() == self._book.layout.name():
                manager.removeLayout(layout)
        project.removeMapLayers([layer.id() for layer in self._book.layers])
        self._book = None

    def release(self) -> None:
        """Leave a running engine alone: QGIS is closing or the plugin is being reloaded."""
        if self.run is not None:
            self.run.release()
            self.run = None
        self.live.clear()
        self._clear_last_run()
        self._drop_book()
