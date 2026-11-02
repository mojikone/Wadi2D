# Wadi2D QGIS plugin. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""5. Boundaries: one line layer holds them all. A table gives each line its kind and value, with no fields in the layer.

A layer with fields "kind" and "value" fills the table by itself. Kind and Value set every line the table has not pinned.
"""

from __future__ import annotations

from dataclasses import replace
from functools import partial

from qgis.core import QgsMapLayerProxyModel
from qgis.PyQt.QtCore import QSignalBlocker, Qt
from qgis.PyQt.QtWidgets import QComboBox, QHeaderView, QLabel, QTableWidget, QTableWidgetItem

from ..boundary_rows import (
    VALUE_KINDS,
    Row,
    follow,
    job_properties,
    line_label,
    merge_rows,
    set_kind,
    set_value,
)
from ..job_builder import BOUNDARY_KIND, BOUNDARY_SLOPE, BOUNDARY_STAGE, layer_features
from .common import Section, bind, layer_combo, number_box

VALUE_FIELDS = {"stage": (BOUNDARY_STAGE, "Stage, m"), "normal": (BOUNDARY_SLOPE, "Energy slope")}
COLUMNS = ["Line", "Kind", "Stage, m, or energy slope"]
LINE_COLUMN, KIND_COLUMN, VALUE_COLUMN = range(3)
SHOWN_ROWS = 6


class BoundariesSection(Section):
    heading = "5. Boundaries"
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
            own = {key: feature[names[key]] for key in ("kind", "value") if key in names}
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
        high = self.table.horizontalHeader().height() + self.table.verticalHeader().defaultSectionSize() * SHOWN_ROWS
        self.table.setMaximumHeight(high + 2 * self.table.frameWidth())
        self._show_rows()

    def _show_rows(self) -> None:
        for number, row in enumerate(self.rows):
            kind = self.table.cellWidget(number, KIND_COLUMN)
            value = self.table.cellWidget(number, VALUE_COLUMN)
            if kind is None or value is None:
                continue
            with QSignalBlocker(kind), QSignalBlocker(value):
                kind.setCurrentText(row.kind)
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
