# Wadi2D QGIS plugin. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""6. Boundaries: one line layer holds them all. A table gives each line its kind and value, with no fields in the layer.

A layer with fields "kind" and "value" fills the table by itself. Kind and Value set every line the table has not pinned.
"""

from __future__ import annotations

from dataclasses import replace
from functools import partial

from qgis.core import QgsMapLayerProxyModel
from qgis.gui import QgsFileWidget
from qgis.PyQt.QtCore import QSignalBlocker, Qt
from qgis.PyQt.QtWidgets import QCheckBox, QComboBox, QHeaderView, QLabel, QTableWidget, QTableWidgetItem

from ..boundary_rows import (
    DIRECTIONS,
    FILE_KINDS,
    VALUE_KINDS,
    Row,
    follow,
    job_properties,
    line_label,
    merge_rows,
    set_direction,
    set_file,
    set_kind,
    set_momentum,
    set_value,
)
from ..job_builder import BOUNDARY_KIND, BOUNDARY_SLOPE, BOUNDARY_STAGE, layer_features
from .common import Section, bind, layer_combo, number_box

VALUE_FIELDS = {"stage": (BOUNDARY_STAGE, "Stage, m"), "normal": (BOUNDARY_SLOPE, "Energy slope")}
COLUMNS = ["Line", "Kind", "Stage, m, or energy slope", "Hydrograph file", "Enters moving", "Flows to"]
LINE_COLUMN, KIND_COLUMN, VALUE_COLUMN, FILE_COLUMN, MOMENTUM_COLUMN, DIRECTION_COLUMN = range(6)
HYDROGRAPH_FILTER = "Flow records (*.csv *.txt *.dss);;All files (*)"
FILE_TIP = (
    "A flow line's hydrograph, HEC-RAS's Flow Hydrograph boundary: a CSV of time (minutes from the run's start) and "
    "m3/s, or a DSS flow record such as an HMS run's. It enters the line's cells, shared by conveyance under the "
    "normal-depth surface at the line's energy slope (0.005 unless the job sets flow.slope); nothing leaves there."
)
MOMENTUM_TIP = (
    "A flow line's water enters moving (W70): each cell's share Q brings Q U of momentum normal to the line, as "
    "HEC-RAS's and TUFLOW's line boundaries do. Untick: it enters at rest, as a volume source (W61). The quadtree and "
    "local time stepping take it at rest whatever the tick, with a warning; unticked, it is written into the job."
)
DIRECTION_WORDS = {
    "auto": "auto: the side with more domain, else the lower ground",
    "left": "left of the line as drawn",
    "right": "right of the line as drawn",
}
SHOWN_ROWS = 6


class BoundariesSection(Section):
    heading = "6. Boundaries"
    start_collapsed = True

    def build(self) -> None:
        self.layer = layer_combo(QgsMapLayerProxyModel.LineLayer, "None: all edges are walls")
        self.kind = QComboBox()
        self.value = number_box(5)
        self.value_label = QLabel()
        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.verticalHeader().hide()
        self.table.setToolTip("Each line of the layer. Click a line to flash it on the map; a row you edit stays as you set it.")
        self.form.addRow("Lines", self.layer)
        self.form.addRow("Kind, for every line", self.kind)
        self.form.addRow(self.value_label, self.value)
        self.form.addRow(self.table)
        self._schema = None
        self._watched = None
        self.rows: list[Row] = []
        self.kind.currentTextChanged.connect(self._kind_changed)
        self.value.valueChanged.connect(self._follow)
        self.layer.layerChanged.connect(self._layer_changed)
        self.table.currentCellChanged.connect(self._flash)

    def apply_schema(self, schema) -> None:
        self._schema = schema
        self.kind.clear()
        self.kind.addItems(schema.enum(BOUNDARY_KIND))
        self.kind.setToolTip(schema.tip(BOUNDARY_KIND))
        self._kind_changed(self.kind.currentText())
        self._fill()

    def _kind_changed(self, kind: str) -> None:
        path, label = VALUE_FIELDS.get(kind, (None, ""))
        self.value.setVisible(path is not None)
        self.value_label.setVisible(path is not None)
        self.value_label.setText(f"{label}, for every line" if label else "")
        if path and self._schema:
            with QSignalBlocker(self.value):
                bind(self.value, self._schema, path)
        self._follow()

    def _shared_value(self) -> float | None:
        return self.value.value() if self.kind.currentText() in VALUE_KINDS else None

    def _follow(self, *_) -> None:
        follow(self.rows, self.kind.currentText(), self._shared_value())
        self._show_rows()

    def _defaults(self) -> dict[str, float]:
        if self._schema is None:
            return {}
        return {kind: self._schema.default(path) for kind, (path, _) in VALUE_FIELDS.items()}

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
            own = {key: feature[names[key]] for key in ("kind", "value", "file", "momentum", "direction") if key in names}
            label = line_label(number, feature[names["name"]] if "name" in names else None)
            lines.append({"fid": feature.id(), "label": label, **own})
        return lines

    def _fill(self, *_) -> None:
        layer = self.layer.currentLayer()
        lines = self._lines(layer) if layer is not None else []
        self.rows = merge_rows(lines, self.rows, self.kind.currentText(), self._shared_value(), self._defaults())
        self.table.setRowCount(len(self.rows))
        kinds = [self.kind.itemText(i) for i in range(self.kind.count())]
        for number, row in enumerate(self.rows):
            name = QTableWidgetItem(row.label)
            name.setFlags(name.flags() & ~Qt.ItemIsEditable)  # the name is the layer's
            self.table.setItem(number, LINE_COLUMN, name)
            kind = QComboBox()
            kind.addItems(kinds)
            if row.kind not in kinds:  # a field with a word the engine does not know: the job says so, not this table
                kind.addItem(row.kind)
            kind.currentTextChanged.connect(partial(self._row_kind, row))
            self.table.setCellWidget(number, KIND_COLUMN, kind)
            value = number_box(5)
            value.valueChanged.connect(partial(self._row_value, row))
            self.table.setCellWidget(number, VALUE_COLUMN, value)
            chooser = QgsFileWidget()
            chooser.setFilter(HYDROGRAPH_FILTER)
            chooser.setToolTip(FILE_TIP)
            chooser.fileChanged.connect(partial(self._row_file, row))
            self.table.setCellWidget(number, FILE_COLUMN, chooser)
            moving = QCheckBox()
            moving.setToolTip(MOMENTUM_TIP)
            moving.toggled.connect(partial(self._row_momentum, row))
            self.table.setCellWidget(number, MOMENTUM_COLUMN, moving)
            side = QComboBox()
            for key in DIRECTIONS:
                side.addItem(DIRECTION_WORDS[key], key)
            side.setToolTip("Which side of the line the water flows to, seen along the line as drawn (W70)")
            side.currentIndexChanged.connect(partial(self._row_direction, row, side))
            self.table.setCellWidget(number, DIRECTION_COLUMN, side)
        high = self.table.horizontalHeader().height() + self.table.verticalHeader().defaultSectionSize() * SHOWN_ROWS
        self.table.setMaximumHeight(high + 2 * self.table.frameWidth())
        self._show_rows()

    def _show_rows(self) -> None:
        for number, row in enumerate(self.rows):
            kind = self.table.cellWidget(number, KIND_COLUMN)
            value = self.table.cellWidget(number, VALUE_COLUMN)
            chooser = self.table.cellWidget(number, FILE_COLUMN)
            moving = self.table.cellWidget(number, MOMENTUM_COLUMN)
            side = self.table.cellWidget(number, DIRECTION_COLUMN)
            if None in (kind, value, chooser, moving, side):
                continue
            with (
                QSignalBlocker(kind), QSignalBlocker(value), QSignalBlocker(chooser), QSignalBlocker(moving),
                QSignalBlocker(side),
            ):
                kind.setCurrentText(row.kind)
                chooser.setEnabled(row.kind in FILE_KINDS)
                chooser.setFilePath(row.file or "")
                moving.setEnabled(row.kind in FILE_KINDS)
                moving.setChecked(row.momentum)
                side.setEnabled(row.kind in FILE_KINDS)
                side.setCurrentIndex(max(side.findData(row.direction), 0))
                path = VALUE_FIELDS.get(row.kind, (None, ""))[0]
                value.setEnabled(path is not None)
                if path and self._schema:
                    bind(value, self._schema, path, default=row.value)
                else:
                    value.clear()

    def _row_kind(self, row: Row, kind: str) -> None:
        set_kind(row, kind, self._defaults())
        self._show_rows()

    def _row_value(self, row: Row, value: float) -> None:
        set_value(row, value)

    def _row_file(self, row: Row, path: str) -> None:
        set_file(row, path)

    def _row_momentum(self, row: Row, on: bool) -> None:
        set_momentum(row, on)

    def _row_direction(self, row: Row, side, _index: int) -> None:
        set_direction(row, side.currentData())

    def _flash(self, number: int, *_) -> None:
        layer = self.layer.currentLayer()
        if layer is not None and self.canvas is not None and 0 <= number < len(self.rows):
            self.canvas.flashFeatureIds(layer, [self.rows[number].fid])

    def values(self, crs) -> dict:
        layer = self.layer.currentLayer()
        if layer is None:
            return {"boundaries": []}
        self._fill()
        by_id = {row.fid: row for row in self.rows}
        lines = []
        for feature in layer_features(layer, crs, with_id=True):
            row = by_id[feature.properties["fid"]]
            lines.append(replace(feature, properties=job_properties(row)))
        return {"boundaries": lines}
