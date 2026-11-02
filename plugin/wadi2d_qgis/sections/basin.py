# Wadi2D QGIS plugin. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""The widgets of section 3 that the generated basin, the hand-back lines and the transmission loss need.

``BasinBox`` generates the basin from the DEM through ``wadi2d basin`` (the dock runs the engine; this box holds the
settings, the result and the junctions table). ``HandbackBox`` is a line layer with an element per line. ``LossRow``
is the dry-bed transmission loss, off by default. The Hydrology section holds all three.
"""

from __future__ import annotations

from functools import partial
from pathlib import Path

from qgis.core import QgsMapLayerProxyModel
from qgis.PyQt.QtCore import QSignalBlocker, Qt, pyqtSignal
from qgis.PyQt.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QWidget,
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
)
from .common import bind, layer_combo, number_box

SHOWN_ROWS = 8
NAME_FIELDS = ("name", "Name", "NAME")


def _fit(table: QTableWidget, rows: int = SHOWN_ROWS) -> None:
    high = table.horizontalHeader().height() + table.verticalHeader().defaultSectionSize() * rows
    table.setMaximumHeight(high + 2 * table.frameWidth())


def _name_field(layer) -> str | None:
    names = layer.fields().names()
    return next((name for name in NAME_FIELDS if name in names), None)


class BasinBox(QGroupBox):
    """Generate the basin from the DEM. Checked, the job runs on the generated basin; an HMS project switches it off."""

    generate_requested = pyqtSignal()
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
        form.addRow("Stream threshold, km2", self.threshold)
        form.addRow("Pour points", self.pour)
        form.addRow("Lag method", self.lag)
        form.addRow(self.generate_button)
        form.addRow(self.summary)
        form.addRow(self.table)
        self.generate_button.clicked.connect(self.generate_requested)

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
            for column, text in enumerate(route_words(row)):
                item = QTableWidgetItem(text)
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                self.table.setItem(number, column, item)
        _fit(self.table)

    def element_choices(self) -> list[str]:
        return element_choices(self.model) if self.model is not None else []

    def settings(self) -> dict:
        return {"stream_threshold_km2": self.threshold.value(), "lag_method": self.lag.currentData()}

    def values(self, crs) -> dict:
        """What the job takes: the file, the settings that made it, the pour points as the dock saw them."""
        pour = self.pour.currentLayer()
        points = []
        if pour is not None:
            field = _name_field(pour)
            points = layer_features(pour, crs, {"name": field} if field else None)
        return {"json": self.json_path, "settings": self.settings(), "pour_points": points}


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
