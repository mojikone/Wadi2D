# Wadi2D QGIS plugin. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""The result-line panel: choose or draw a line, ask the engine, and follow the time slider.

The engine reads the run: QGIS must not load a second HDF5 library. Each answer holds every saved frame, so moving the
slider asks nothing of the engine and only repaints. The panel works alone with its own slider, and when the Time slider
button has set up the Temporal Controller the two move together.
"""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsMapLayerProxyModel,
    QgsPointXY,
    QgsProject,
    QgsTemporalNavigationObject,
)
from qgis.gui import QgsDockWidget
from qgis.PyQt.QtCore import QDate, QDateTime, Qt, QTime
from qgis.PyQt.QtWidgets import QComboBox, QHBoxLayout, QLabel, QPushButton, QSlider, QVBoxLayout, QWidget

from . import settings
from .engine_process import EngineQuery
from .job_builder import LayerError, layer_features
from .line_plot import LinePlot
from .line_tool import DrawLine, add_line, remove_line, scratch_layer
from .line_view import (
    TEMPORARY,
    UPFRONT_LINE,
    UPFRONT_POINT,
    Entry,
    clock,
    entries,
    frame_at,
    line_view,
    point_view,
    record_view,
    step_showing,
)
from .protocol import (
    FRAMES_EPOCH,
    LINE_REQUEST,
    LINE_RESULT,
    LINES_LIST,
    engine_error_text,
    exit_message,
    lines_args,
)
from .sections.common import layer_combo

TITLE = "Wadi2D result lines"
OBJECT_NAME = "Wadi2DResultLines"
DRAW_NOTE = "Click along the line on the map, right-click to end it, Escape to drop it. Cross the flow."
TIME_NOTE = "The map moves with this slider once Time slider has been pressed in the dock."
FEATURE_NAME = "name"
MILLISECONDS = 1000.0


class ResultLinesPanel(QgsDockWidget):
    def __init__(self, iface, parent=None) -> None:
        super().__init__(TITLE, parent)
        self.setObjectName(OBJECT_NAME)
        self.iface = iface
        self.canvas = iface.mapCanvas()
        self.run: Path | None = None
        self.crs = QgsProject.instance().crs()
        self.frames_s: list[float] = []
        self.read: dict[int, dict] = {}
        self.items: list[Entry] = []
        self.picked: list = []
        self.query: EngineQuery | None = None
        self.waiting = False
        self.layer_id: str | None = None
        self.drawn_count = 0
        self.asked = 0
        self.frame = 0
        self.pushing = False
        self.folder = tempfile.mkdtemp(prefix="wadi2d_lines_")
        self.tool = DrawLine(self.canvas)
        self.old_tool = None
        self._build()
        self.tool.drawn.connect(self._drawn)
        self.tool.dropped.connect(self._draw_over)
        self.controller = self.canvas.temporalController()
        self.controller.updateTemporalRange.connect(self._range_moved)
        iface.addDockWidget(Qt.BottomDockWidgetArea, self)

    def _build(self) -> None:
        self.choice = QComboBox()
        self.choice.setMinimumWidth(260)
        self.draw_button = QPushButton("Draw a line")
        self.remove_button = QPushButton("Remove")
        self.remove_button.setEnabled(False)
        self.layer = layer_combo(QgsMapLayerProxyModel.LineLayer, "Line layer")
        self.feature = QComboBox()
        self.use_button = QPushButton("Use this line")
        self.use_button.setEnabled(False)
        self.plot = LinePlot()
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setEnabled(False)
        self.time_label = QLabel()
        self.message = QLabel()
        self.message.setWordWrap(True)
        top = QHBoxLayout()
        top.addWidget(self.choice, 2)
        top.addWidget(self.draw_button)
        top.addWidget(self.remove_button)
        top.addWidget(self.layer, 1)
        top.addWidget(self.feature, 1)
        top.addWidget(self.use_button)
        bottom = QHBoxLayout()
        bottom.addWidget(self.slider, 1)
        bottom.addWidget(self.time_label)
        body = QWidget()
        column = QVBoxLayout(body)
        column.addLayout(top)
        column.addWidget(self.plot, 1)
        column.addLayout(bottom)
        column.addWidget(self.message)
        self.setWidget(body)
        self.choice.currentIndexChanged.connect(self._chosen)
        self.draw_button.clicked.connect(self._draw)
        self.remove_button.clicked.connect(self._remove)
        self.layer.layerChanged.connect(self._layer_chosen)
        self.use_button.clicked.connect(self._use_feature)
        self.slider.valueChanged.connect(self._slid)

    def say(self, text: str) -> None:
        self.message.setText(text)

    # The run.

    def open_run(self, run: Path | str) -> None:
        self.run = Path(run)
        self.read = {}
        self.show()
        self.raise_()
        self.say("Reading what the run holds...")
        self._ask(lines_args(self.run, self._file(LINES_LIST)), self._listed)

    def _file(self, name: str) -> str:
        return str(Path(self.folder) / name)

    def _ask(self, args: list[str], then) -> None:
        query = EngineQuery(settings.engine_text(), self)
        query.done.connect(lambda code, _out, err: self._answered(query, code, err, then))
        self.query = query
        query.start(args)

    def _answered(self, query: EngineQuery, code: int, err: str, then) -> None:
        query.deleteLater()
        if query is self.query:
            self.query = None
        if code == 0:
            then()
        else:
            self._failed(engine_error_text(err) or exit_message(code))
        if self.waiting:
            self.waiting = False
            self._chosen(self.choice.currentIndex())

    def _failed(self, text: str) -> None:
        self.say(text)
        entry = self._current()
        upfront = entry is not None and entry.kind == UPFRONT_LINE
        self.plot.show_view(record_view(entry, self.frames_s) if upfront else None, self.frame)

    def _listed(self) -> None:
        listing = json.loads(Path(self._file(LINES_LIST)).read_text(encoding="utf-8"))
        crs = QgsCoordinateReferenceSystem.fromWkt(listing.get("crs", ""))
        self.crs = crs if crs.isValid() else QgsProject.instance().crs()
        self.frames_s = listing["frames_s"]
        self.slider.blockSignals(True)
        self.slider.setRange(0, max(len(self.frames_s) - 1, 0))
        self.slider.setValue(0)
        self.slider.blockSignals(False)
        self.slider.setEnabled(len(self.frames_s) > 1)
        self.frame = 0
        self._show_time()
        self.items = entries(listing) + [item for item in self.items if item.kind == TEMPORARY]
        self._fill_choice(0)
        self.say("" if self.items else "This run has no upfront lines or points. Draw a line, or pick one from a layer.")

    def _fill_choice(self, index: int) -> None:
        self.choice.blockSignals(True)
        self.choice.clear()
        self.choice.addItems([item.label for item in self.items])
        self.choice.setCurrentIndex(index)
        self.choice.blockSignals(False)
        self._chosen(index)

    def _current(self) -> Entry | None:
        index = self.choice.currentIndex()
        return self.items[index] if 0 <= index < len(self.items) else None

    # One line.

    def _chosen(self, _index: int) -> None:
        entry = self._current()
        self.remove_button.setEnabled(entry is not None and entry.kind == TEMPORARY)
        if entry is None:
            self.plot.show_view(None)
            return
        self._show(entry)

    def _show(self, entry: Entry) -> None:
        if entry.kind == UPFRONT_POINT:
            self.plot.show_view(point_view(entry, self.frames_s), self.frame)
            self.say("")
            return
        known = self.read.get(id(entry))
        if known is not None:
            self.plot.show_view(line_view(entry, known), self.frame)
            self.say("")
            return
        if self.query is not None:
            self.waiting = True
            return
        self.say("Reading the line from the saved frames...")
        self.asked += 1  # a file of its own: a new run can arrive while an answer is on its way
        request = Path(self._file(f"{self.asked}_{LINE_REQUEST}"))
        request.write_text(json.dumps({"name": entry.name, "coordinates": entry.coordinates}), encoding="utf-8")
        answer = self._file(f"{self.asked}_{LINE_RESULT}")
        self._ask(lines_args(self.run, answer, request), lambda: self._line_read(entry, answer))

    def _line_read(self, entry: Entry, answer: str) -> None:
        self.read[id(entry)] = json.loads(Path(answer).read_text(encoding="utf-8"))
        self.say("")
        if entry is self._current():
            self.plot.show_view(line_view(entry, self.read[id(entry)]), self.frame)

    def _add(self, entry: Entry) -> None:
        self.items.append(entry)
        self._fill_choice(len(self.items) - 1)

    # Drawing, and picking from a layer.

    def _draw(self) -> None:
        if self.canvas.mapTool() is not self.tool:
            self.old_tool = self.canvas.mapTool()
        self.canvas.setMapTool(self.tool)
        self.say(DRAW_NOTE)

    def _draw_over(self) -> None:
        self.canvas.unsetMapTool(self.tool)
        if self.old_tool is not None:
            self.canvas.setMapTool(self.old_tool)
        self.say("")

    def _scratch(self):
        project = QgsProject.instance()
        layer = project.mapLayer(self.layer_id) if self.layer_id else None
        if layer is None:
            layer = scratch_layer(self.crs, self.run.name if self.run else "")
            self.layer_id = layer.id()
            self.layer.setExceptedLayerList([layer])
        return layer

    def _drawn(self, points: list) -> None:
        self._draw_over()
        if self.run is None:
            return
        transform = QgsCoordinateTransform(self.canvas.mapSettings().destinationCrs(), self.crs, QgsProject.instance())
        run_points = [QgsPointXY(transform.transform(point)) for point in points]
        self.drawn_count += 1
        name = f"Line {self.drawn_count}"
        feature = add_line(self._scratch(), name, run_points)
        self._add(Entry(TEMPORARY, name, [[p.x(), p.y()] for p in run_points], feature_id=feature))

    def _remove(self) -> None:
        entry = self._current()
        if entry is None or entry.kind != TEMPORARY:
            return
        layer = QgsProject.instance().mapLayer(self.layer_id) if self.layer_id else None
        if layer is not None and entry.feature_id is not None and entry.feature_id >= 0:
            remove_line(layer, entry.feature_id)
        self.read.pop(id(entry), None)
        self.items.remove(entry)
        self._fill_choice(0 if self.items else -1)

    def _layer_chosen(self, layer) -> None:
        self.feature.clear()
        self.picked = []
        self.use_button.setEnabled(False)
        if layer is None:
            return
        names = {FEATURE_NAME: FEATURE_NAME} if layer.fields().indexOf(FEATURE_NAME) >= 0 else {}
        try:
            self.picked = [item for item in layer_features(layer, self.crs, names) if item.kind == "LineString"]
        except LayerError as error:
            self.say(str(error))
            return
        self.feature.addItems([self._feature_name(layer, n) for n in range(len(self.picked))])
        self.use_button.setEnabled(bool(self.picked))

    def _feature_name(self, layer, index: int) -> str:
        return str(self.picked[index].properties.get(FEATURE_NAME) or f"{layer.name()} {index + 1}")

    def _use_feature(self) -> None:
        layer = self.layer.currentLayer()
        index = self.feature.currentIndex()
        if layer is None or not 0 <= index < len(self.picked):
            return
        name = self._feature_name(layer, index)
        self._add(Entry(TEMPORARY, f"{name}, from {layer.name()}", self.picked[index].xy()))

    # Time.

    def _show_time(self) -> None:
        if not self.frames_s:
            self.time_label.setText("No saved frames")
            return
        t_s = self.frames_s[min(self.frame, len(self.frames_s) - 1)]
        self.time_label.setText(f"{clock(t_s)}, frame {self.frame + 1} of {len(self.frames_s)}")

    def _set_frame(self, frame: int) -> None:
        self.frame = frame
        self.plot.set_frame(frame)
        self._show_time()

    def _slid(self, frame: int) -> None:
        self._set_frame(frame)
        if self.pushing:
            return
        if self.controller.navigationMode() != QgsTemporalNavigationObject.Animated:
            self.say(TIME_NOTE)
            return
        start = self._epoch().msecsTo(self.controller.temporalExtents().begin()) / MILLISECONDS
        step = self.controller.frameDuration().seconds()
        self.pushing = True
        number = step_showing(self.frames_s[frame], start, step, self.controller.totalFrameCount())
        self.controller.setCurrentFrameNumber(number)
        self.pushing = False

    @staticmethod
    def _epoch() -> QDateTime:
        return QDateTime(QDate(*FRAMES_EPOCH), QTime(0, 0), Qt.UTC)

    def _range_moved(self, moved) -> None:
        if self.pushing or not self.frames_s or not moved.begin().isValid():
            return
        frame = frame_at(self.frames_s, self._epoch().msecsTo(moved.begin()) / MILLISECONDS)
        self.pushing = True
        self.slider.setValue(frame)
        self.pushing = False

    def release(self) -> None:
        """QGIS is closing or the plugin is going away: leave nothing behind but the scratch layer."""
        self.controller.updateTemporalRange.disconnect(self._range_moved)
        self.canvas.unsetMapTool(self.tool)
        shutil.rmtree(self.folder, ignore_errors=True)
        self.iface.removeDockWidget(self)
        self.deleteLater()
