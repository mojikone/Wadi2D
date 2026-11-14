# Wadi2D QGIS plugin. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""The widgets of section 3 that the generated basin, the hand-back lines and the transmission loss need.

``BasinBox`` generates the basin from the DEM through ``wadi2d basin`` (the dock runs the engine; this box holds the
settings, the result and the junctions table). ``HandbackBox`` is a line layer with an element per line. ``LossRow``
is the dry-bed transmission loss, off by default. The Hydrology section holds all three.
"""

from __future__ import annotations

import contextlib
from functools import partial
from pathlib import Path

from qgis.core import QgsMapLayerProxyModel
from qgis.PyQt.QtCore import QSignalBlocker, Qt, pyqtSignal
from qgis.PyQt.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QWidget,
)

from ..basin_point_rows import (
    DELINEATE_DEFAULT,
    DELINEATE_KINDS,
    DELINEATE_WORDS,
    DIVERSION_COLUMNS,
    DIVERSION_EDITS,
    DIVERSION_METHODS,
    KIND_WORDS,
    POINT_KINDS,
    absolute_files,
    diversion_rows,
    needs_words,
    point_fields,
)
from ..job_builder import layer_features
from .basin_rows import (
    JUNCTION_COLUMNS,
    LAG_METHOD,
    LAG_WORDS,
    STREAM_THRESHOLD,
    TRANSMISSION_ON,
    TRANSMISSION_RATE,
    HandbackRow,
    SubbasinRow,
    element_choices,
    handback_properties,
    junction_rows,
    line_label,
    merge_event,
    merge_handbacks,
    read_basin,
    route_words,
    set_element,
    subbasin_rows,
    summary_text,
    tc_words,
)
from .common import bind, layer_combo, number_box

SHOWN_ROWS = 8


def _fit(table: QTableWidget, rows: int = SHOWN_ROWS) -> None:
    high = table.horizontalHeader().height() + table.verticalHeader().defaultSectionSize() * rows
    table.setMaximumHeight(high + 2 * table.frameWidth())


class BasinBox(QGroupBox):
    """Generate the basin from the DEM. Checked, the job runs on the generated basin; an HMS project switches it off."""

    generate_requested = pyqtSignal()
    new_points_requested = pyqtSignal()
    """A new Basin points layer is wanted (W73)."""
    place_requested = pyqtSignal(str)
    """The next map click adds a point of this kind."""
    place_stopped = pyqtSignal()
    subbasins_changed = pyqtSignal(list)
    """The subbasin rows of the last generation, for the section's table."""

    def __init__(self) -> None:
        super().__init__("Generate the basin from the DEM")
        self.setCheckable(True)
        self.setChecked(False)
        self.model: dict | None = None
        self.json_path: str | None = None
        self.rows: list[dict] = []
        form = QFormLayout(self)
        form.setRowWrapPolicy(QFormLayout.WrapLongRows)
        self.threshold = number_box(2)
        self.threshold.setToolTip("Drainage area that starts a stream, km2; 0 breaks at the pour points only")
        self.pour = layer_combo(QgsMapLayerProxyModel.PointLayer, "None: the dams and the design lines")
        self.lag = QComboBox()
        self.generate_button = QPushButton("Generate basin")
        self.summary = QLabel("")
        self.summary.setWordWrap(True)
        self.table = QTableWidget(0, len(JUNCTION_COLUMNS))
        self.table.setHorizontalHeaderLabels(JUNCTION_COLUMNS)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.verticalHeader().hide()
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setToolTip(
            "Each junction: routed through its reach, or its water enters the 2D grid and runs over the ground to the "
            "next junction. The last column fills in when a run starts."
        )
        self.pour.setToolTip(
            "The Basin points layer: a point layer whose kind field says what each point is (outfall, design_point, dam, "
            "diversion, source, junction, remove_junction, join_subbasins). A layer with no kind field gives plain break "
            "points. Every edit is a point, so Generate basin replays them all."
        )
        self.new_points_button = QPushButton("New layer")
        self.new_points_button.setToolTip("An empty Basin points layer in Inputs > Hydrology, with every field; save it to keep it")
        points_row = QWidget()
        points_line = QHBoxLayout(points_row)
        points_line.setContentsMargins(0, 0, 0, 0)
        points_line.addWidget(self.pour, 1)
        points_line.addWidget(self.new_points_button)
        self.point_kind = QComboBox()
        for kind in POINT_KINDS:
            self.point_kind.addItem(KIND_WORDS[kind], kind)
        self.place_button = QPushButton("Click on the map")
        self.place_button.setCheckable(True)
        self.place_button.setToolTip("One click adds a point of this kind to the Basin points layer; Generate basin applies it")
        place_row = QWidget()
        place_line = QHBoxLayout(place_row)
        place_line.setContentsMargins(0, 0, 0, 0)
        place_line.addWidget(self.point_kind, 1)
        place_line.addWidget(self.place_button)
        self.diversions = QTableWidget(0, len(DIVERSION_COLUMNS))
        self.diversions.setHorizontalHeaderLabels(DIVERSION_COLUMNS)
        self.diversions.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.diversions.verticalHeader().hide()
        self.diversions.setToolTip(
            "The diversion points of the Basin points layer (W75): HMS's five methods and two limits. An edit here is "
            "written into the layer's fields; Generate basin reads them, checks them in the engine's words, and the "
            "junction runs as a diversion. Tables: a CSV beside the layer or inline [[x, y], ...]; parameters and limits "
            'are JSON, e.g. {"rate_m3s": 20} and {"max_m3s": 50}.'
        )
        self.diversions.hide()
        self.diversion_rows: list[dict] = []
        self._watched = None
        self.ticks = {kind: QCheckBox(DELINEATE_WORDS[kind]) for kind in DELINEATE_KINDS}
        tick_row = QWidget()
        tick_grid = QGridLayout(tick_row)
        tick_grid.setContentsMargins(0, 0, 0, 0)
        for number, (kind, box) in enumerate(self.ticks.items()):
            box.setChecked(kind in DELINEATE_DEFAULT)
            box.setToolTip(
                "The Structures layer of this kind edits the ground the basin is delineated on, as HEC-HMS's wall and "
                "burn tools do: walls and crests raise it, burn lines and channels cut it. A layer's own delineate field "
                "outranks this tick. The 2D run is not affected."
            )
            tick_grid.addWidget(box, number // 3, number % 3)
        form.addRow("Stream threshold, km2", self.threshold)
        form.addRow("Basin points", points_row)
        form.addRow("Add a point", place_row)
        form.addRow(self.diversions)
        form.addRow("Delineate on", tick_row)
        form.addRow("Lag method", self.lag)
        form.addRow(self.generate_button)
        form.addRow(self.summary)
        form.addRow(self.table)
        self.generate_button.clicked.connect(self.generate_requested)
        self.new_points_button.clicked.connect(self.new_points_requested)
        self.place_button.toggled.connect(self._place_toggled)
        self.pour.layerChanged.connect(self._points_layer_changed)
        self.diversions.cellChanged.connect(self._diversion_edited)

    # The diversion points (W75): the layer holds them, the table edits its fields.

    def _points_layer_changed(self, layer) -> None:
        if self._watched is not None:
            with contextlib.suppress(TypeError, RuntimeError):  # already gone with its layer
                self._watched.dataChanged.disconnect(self.fill_diversions)
        self._watched = layer
        if layer is not None:
            layer.dataChanged.connect(self.fill_diversions)
        self.fill_diversions()

    def fill_diversions(self, *_) -> None:
        """The layer's diversion points as rows; nothing shown when it has none."""
        layer = self.pour.currentLayer()
        features = []
        if layer is not None:
            fields = point_fields(layer.fields().names())
            for feature in layer.getFeatures():
                features.append({"fid": feature.id(), **{key: feature[name] for key, name in fields.items()}})
        self.diversion_rows = diversion_rows(features)
        with QSignalBlocker(self.diversions):
            self.diversions.setRowCount(len(self.diversion_rows))
            for number, row in enumerate(self.diversion_rows):
                name = QTableWidgetItem(row["name"])
                name.setFlags(name.flags() & ~Qt.ItemIsEditable)
                self.diversions.setItem(number, 0, name)
                method = QComboBox()
                method.addItem("")
                method.addItems(DIVERSION_METHODS)
                method.setEditable(True)  # a name the engine does not know is its to refuse, in words
                method.setCurrentText(row["method"])
                method.currentTextChanged.connect(partial(self._method_chosen, row["fid"]))
                self.diversions.setCellWidget(number, 1, method)
                for column, key in enumerate(DIVERSION_EDITS[1:], start=2):
                    self.diversions.setItem(number, column, QTableWidgetItem(row[key]))
                needs = QTableWidgetItem(needs_words(row["method"]))
                needs.setFlags(needs.flags() & ~Qt.ItemIsEditable)
                needs.setToolTip(needs.text())
                self.diversions.setItem(number, len(DIVERSION_COLUMNS) - 1, needs)
        _fit(self.diversions, 4)
        self.diversions.setVisible(bool(self.diversion_rows))

    def _method_chosen(self, fid: int, method: str) -> None:
        self._write_field(fid, "method", method)
        number = next(i for i, row in enumerate(self.diversion_rows) if row["fid"] == fid)
        with QSignalBlocker(self.diversions):
            self.diversions.item(number, len(DIVERSION_COLUMNS) - 1).setText(needs_words(method))

    def _diversion_edited(self, number: int, column: int) -> None:
        if not 2 <= column < len(DIVERSION_COLUMNS) - 1 or number >= len(self.diversion_rows):
            return
        key = DIVERSION_EDITS[column - 1]
        self._write_field(self.diversion_rows[number]["fid"], key, self.diversions.item(number, column).text())

    def _write_field(self, fid: int, key: str, text: str) -> None:
        """One field of one point, in the layer; a layer without the field is said, not changed."""
        layer = self.pour.currentLayer()
        if layer is None:
            return
        name = point_fields(layer.fields().names()).get(key)
        if name is None:
            self.say(f'Layer "{layer.name()}" has no {key} field: add it, or make a new Basin points layer.')
            return
        index = layer.fields().indexOf(name)
        value = text.strip() or None
        for row in self.diversion_rows:
            if row["fid"] == fid:
                row[key] = text.strip()
        if layer.isEditable():
            layer.changeAttributeValue(fid, index, value)
        else:
            layer.dataProvider().changeAttributeValues({fid: {index: value}})
            layer.triggerRepaint()

    def _place_toggled(self, on: bool) -> None:
        if on:
            self.place_requested.emit(self.point_kind.currentData())
        else:
            self.place_stopped.emit()

    def point_placed(self, text: str) -> None:
        """The dock's word after a click: the button comes back up."""
        with QSignalBlocker(self.place_button):
            self.place_button.setChecked(False)
        self.fill_diversions()
        self.say(text)

    def apply_schema(self, schema) -> None:
        bind(self.threshold, schema, STREAM_THRESHOLD)
        self.threshold.setMinimum(0.0)
        self.lag.clear()
        for key in schema.enum(LAG_METHOD):
            self.lag.addItem(LAG_WORDS.get(key, key), key)
        self.lag.setToolTip(schema.tip(LAG_METHOD))
        default = schema.default(LAG_METHOD)
        if default is not None:
            self.lag.setCurrentIndex(max(self.lag.findData(default), 0))

    def in_use(self) -> bool:
        return self.isChecked() and self.model is not None

    def say(self, text: str) -> None:
        self.summary.setText(text)

    def set_busy(self, busy: bool) -> None:
        self.generate_button.setEnabled(not busy)

    def take(self, event: dict) -> list[SubbasinRow]:
        """The result of ``wadi2d basin``: read the file, fill the tables, hand the subbasin rows out."""
        self.json_path = event["basin"]
        self.model = read_basin(self.json_path)
        rows = subbasin_rows(self.model)
        self.rows = junction_rows(self.model)
        self._show_rows()
        self.say(summary_text(self.model, rows))
        self.subbasins_changed.emit(rows)
        return rows

    def show_routes(self, event: dict) -> None:
        """The run's own word on each junction."""
        self.rows = merge_event(self.rows, event)
        self._show_rows()

    def _show_rows(self) -> None:
        self.table.setRowCount(len(self.rows))
        for number, row in enumerate(self.rows):
            for column, text in enumerate([*route_words(row), tc_words(row)]):
                item = QTableWidgetItem(text)
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                self.table.setItem(number, column, item)
        _fit(self.table)

    def element_choices(self) -> list[str]:
        return element_choices(self.model) if self.model is not None else []

    def settings(self) -> dict:
        return {"stream_threshold_km2": self.threshold.value(), "lag_method": self.lag.currentData()}

    def values(self, crs) -> dict:
        """What the job takes: the file, the settings that made it, the Basin points as the dock saw them (every field
        of the W73 kinds the layer has, a source's relative file made absolute), the delineation ticks."""
        pour = self.pour.currentLayer()
        points = []
        if pour is not None:
            fields = point_fields(pour.fields().names())
            source = pour.source().split("|")[0]
            folder = Path(source).parent if pour.providerType() == "ogr" and source else None
            points = absolute_files(layer_features(pour, crs, fields or None), folder)
        ticks = {kind: box.isChecked() for kind, box in self.ticks.items()}
        return {"json": self.json_path, "settings": self.settings(), "pour_points": points, "delineate": ticks}


class HandbackBox(QWidget):
    """Hand-back lines: one line layer, an element per line. A field ``element`` pins a row; a chosen one stays."""

    def __init__(self) -> None:
        super().__init__()
        self.rows: list[HandbackRow] = []
        self.choices: list[str] = []
        self._watched = None
        form = QFormLayout(self)
        form.setContentsMargins(0, 0, 0, 0)
        self.layer = layer_combo(QgsMapLayerProxyModel.LineLayer, "None")
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["Line", "Enters element"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.verticalHeader().hide()
        self.table.setToolTip(
            "2D flow that crosses a line leaves the grid and enters the lumped element, whose route runs during the "
            "run and comes back at the inflow below it (D6c). The lines of a generated basin are built by the run."
        )
        form.addRow("Hand-back lines", self.layer)
        form.addRow(self.table)
        self.layer.layerChanged.connect(self._layer_changed)

    def set_choices(self, choices: list[str]) -> None:
        self.choices = list(choices)
        self._fill()

    def _layer_changed(self, layer) -> None:
        if self._watched is not None:
            self._watched.dataChanged.disconnect(self._fill)
        self._watched = layer
        if layer is not None:
            layer.dataChanged.connect(self._fill)
        self.rows = []
        self._fill()

    def _lines(self, layer) -> list[dict]:
        names = {name.lower(): name for name in layer.fields().names()}
        lines = []
        for number, feature in enumerate(layer.getFeatures(), start=1):
            own = {"element": feature[names["element"]]} if "element" in names else {}
            label = line_label(number, feature[names["name"]] if "name" in names else None)
            lines.append({"fid": feature.id(), "label": label, **own})
        return lines

    def _fill(self, *_) -> None:
        layer = self.layer.currentLayer()
        lines = self._lines(layer) if layer is not None else []
        self.rows = merge_handbacks(lines, self.rows, self.choices)
        self.table.setRowCount(len(self.rows))
        for number, row in enumerate(self.rows):
            name = QTableWidgetItem(row.label)
            name.setFlags(name.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(number, 0, name)
            element = QComboBox()
            element.setEditable(True)
            element.addItems(self.choices)
            with QSignalBlocker(element):
                element.setCurrentText(row.element)
            element.currentTextChanged.connect(partial(set_element, row))
            self.table.setCellWidget(number, 1, element)
        _fit(self.table, 4)

    def features(self, crs) -> list:
        from dataclasses import replace

        layer = self.layer.currentLayer()
        if layer is None:
            return []
        self._fill()
        by_id = {row.fid: row for row in self.rows}
        return [
            replace(feature, properties=handback_properties(by_id[feature.properties["fid"]]))
            for feature in layer_features(layer, crs, with_id=True)
        ]


class LossRow(QWidget):
    """Dry-bed transmission loss (D6d): a rate over the wetted bed of channel cells, off by default."""

    def __init__(self) -> None:
        super().__init__()
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        self.enabled = QCheckBox("Transmission loss on dry beds, mm/h")
        self.rate = number_box(1)
        self.rate.setEnabled(False)
        row.addWidget(self.enabled)
        row.addWidget(self.rate)
        self.enabled.toggled.connect(self.rate.setEnabled)

    def apply_schema(self, schema) -> None:
        bind(self.rate, schema, TRANSMISSION_RATE)
        self.enabled.setToolTip(schema.tip(TRANSMISSION_ON))
        self.enabled.setChecked(bool(schema.default(TRANSMISSION_ON)))

    def values(self) -> dict | None:
        return {"rate_mm_h": self.rate.value()} if self.enabled.isChecked() else None


def basin_folder(output: str | Path, name: str) -> Path:
    return Path(output) / name
