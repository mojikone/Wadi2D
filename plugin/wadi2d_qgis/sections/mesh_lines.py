# Wadi2D QGIS plugin. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""The refinement lines of section 2: a layer, a table of near size, rows and far size, and what each size becomes.

Its widgets go into the section's form one by one, so anything else can sit between them. To fill the table from a layer
made by code, as Suggest breaklines will, set ``layer``; fields ``near_dx``, ``rows`` and ``far_dx`` are read by themselves.
"""

from __future__ import annotations

from contextlib import suppress
from dataclasses import replace
from functools import partial

from qgis.core import NULL, QgsMapLayerProxyModel
from qgis.PyQt.QtCore import QSignalBlocker, Qt
from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtWidgets import QAbstractSpinBox, QHeaderView, QLabel, QTableWidget, QTableWidgetItem

from ..boundary_rows import line_label
from ..job_builder import LINES_NOTE, MESH_LINE_FAR, MESH_LINE_NEAR, MESH_LINE_ROWS, layer_features
from ..mesh_rows import (
    LINE_FIELDS,
    LineRow,
    follow,
    job_properties,
    merge_rows,
    rounded_note,
    rung_size,
    set_far,
    set_near,
    set_rows,
)
from .common import bind, layer_combo, number_box

COLUMNS = ["Line", "Near,\nm", "Rows", "Far,\nm", "Actual\nnear, m", "Actual\nfar, m"]
LINE_COLUMN, NEAR_COLUMN, ROWS_COLUMN, FAR_COLUMN, ACTUAL_NEAR_COLUMN, ACTUAL_FAR_COLUMN = range(6)
HEADER_TIPS = {
    NEAR_COLUMN: "The cell size you ask for beside the line.",
    ROWS_COLUMN: "Rows of near cells each side of the line. Each doubling out to Far holds as many rows.",
    FAR_COLUMN: "The cell size the band grades out to, 2:1. Past it the other rules apply. The band reaches rows x (2 far - near).",
    ACTUAL_NEAR_COLUMN: "What the mesh gives: Near, down to the finest cell times 1, 2, 4 or 8.",
    ACTUAL_FAR_COLUMN: "What the mesh gives: Far, down to the finest cell times 1, 2, 4 or 8.",
}
SHOWN_ROWS = 5
ROUNDED_COLOUR = "#a06000"
"""The dock's note colour: a size that moved must not read like one that did not."""


class LineTable:
    """Not a widget: three widgets and the rows behind them."""

    def __init__(self, canvas=None) -> None:
        self.canvas = canvas
        self.layer = layer_combo(QgsMapLayerProxyModel.LineLayer, "No refinement lines")
        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.verticalHeader().hide()
        self.table.setToolTip("Each line of the layer. Click a line to flash it on the map; a size you set stays as you set it.")
        for column, tip in HEADER_TIPS.items():
            self.table.horizontalHeaderItem(column).setToolTip(tip)
        self.note = QLabel(LINES_NOTE)
        self.note.setWordWrap(True)
        self.rounded = QLabel()
        self.rounded.setWordWrap(True)
        self.rounded.setStyleSheet(f"color: {ROUNDED_COLOUR}")
        self.rounded.hide()
        self.rows: list[LineRow] = []
        self.finest = 0.0
        self.coarsest = 0.0
        self._schema = None
        self._watched = None
        self.layer.layerChanged.connect(self._layer_changed)
        self.table.currentCellChanged.connect(self._flash)

    def apply_schema(self, schema) -> None:
        self._schema = schema
        self._fill()

    def set_enabled(self, on: bool) -> None:
        for widget in (self.layer, self.table, self.note, self.rounded):
            widget.setEnabled(on)

    def set_sizes(self, finest: float, coarsest: float) -> None:
        """The two ends of the ladder: rows nobody set follow them, and every Actual is read again."""
        self.finest, self.coarsest = finest, coarsest
        follow(self.rows, finest, coarsest)
        self._show_rows()

    def _default_rows(self) -> int:
        return int(self._schema.default(MESH_LINE_ROWS, 1)) if self._schema else 1

    def _layer_changed(self, layer) -> None:
        if self._watched is not None:
            with suppress(RuntimeError):  # the layer may have left the project, and its signal with it
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
            own = {key: feature[names[key]] for key in LINE_FIELDS if key in names}
            name = feature[names["name"]] if "name" in names else None
            label = line_label(number, None if name == NULL else name)  # QGIS's NULL is not a Python None
            lines.append({"fid": feature.id(), "label": label, **own})
        return lines

    def _size_box(self, path: str):
        box = number_box(2)
        box.setButtonSymbols(QAbstractSpinBox.NoButtons)
        if self._schema:
            bind(box, self._schema, path)
        return box

    def _fill(self, *_) -> None:
        layer = self.layer.currentLayer()
        lines = self._lines(layer) if layer is not None else []
        self.rows = merge_rows(lines, self.rows, self.finest, self.coarsest, self._default_rows())
        self.table.setRowCount(len(self.rows))
        for number, row in enumerate(self.rows):
            name = QTableWidgetItem(row.label)
            name.setFlags(name.flags() & ~Qt.ItemIsEditable)  # the name is the layer's
            self.table.setItem(number, LINE_COLUMN, name)
            near = self._size_box(MESH_LINE_NEAR)
            near.valueChanged.connect(partial(self._edited, row, set_near))
            self.table.setCellWidget(number, NEAR_COLUMN, near)
            count = number_box(0)
            count.setButtonSymbols(QAbstractSpinBox.NoButtons)
            if self._schema:
                bind(count, self._schema, MESH_LINE_ROWS)
            count.valueChanged.connect(partial(self._edited, row, set_rows))
            self.table.setCellWidget(number, ROWS_COLUMN, count)
            far = self._size_box(MESH_LINE_FAR)
            far.valueChanged.connect(partial(self._edited, row, set_far))
            self.table.setCellWidget(number, FAR_COLUMN, far)
            for column in (ACTUAL_NEAR_COLUMN, ACTUAL_FAR_COLUMN):
                actual = QTableWidgetItem()
                actual.setFlags(actual.flags() & ~Qt.ItemIsEditable)  # the mesh's answer, not an input
                self.table.setItem(number, column, actual)
        high = self.table.horizontalHeader().sizeHint().height() + self.table.verticalHeader().defaultSectionSize() * SHOWN_ROWS
        self.table.setMaximumHeight(high + 2 * self.table.frameWidth())
        self._show_rows()

    def _edited(self, row: LineRow, setter, value: float) -> None:
        setter(row, value)
        self._show_answers()  # not the boxes: the one being typed in must keep its text and its cursor

    def _show_rows(self) -> None:
        for number, row in enumerate(self.rows):
            near = self.table.cellWidget(number, NEAR_COLUMN)
            count = self.table.cellWidget(number, ROWS_COLUMN)
            far = self.table.cellWidget(number, FAR_COLUMN)
            if near is None or count is None or far is None:
                continue
            with QSignalBlocker(near), QSignalBlocker(count), QSignalBlocker(far):
                near.setValue(row.near)
                count.setValue(row.rows)
                far.setValue(row.far)
        self._show_answers()

    def _show_answers(self) -> None:
        for number, row in enumerate(self.rows):
            if self.table.item(number, ACTUAL_NEAR_COLUMN) is None:
                continue
            self._show_actual(number, ACTUAL_NEAR_COLUMN, row.near)
            self._show_actual(number, ACTUAL_FAR_COLUMN, row.far)
        words = [rounded_note(row.label, row.near, row.far, self.finest, self.coarsest) for row in self.rows]
        text = " ".join(word for word in words if word)
        self.rounded.setText(text)
        self.rounded.setVisible(bool(text))

    def _show_actual(self, number: int, column: int, asked: float) -> None:
        got = rung_size(asked, self.finest, self.coarsest)
        item = self.table.item(number, column)
        item.setText(f"{got:g}")
        moved = got != asked
        font = item.font()
        font.setBold(moved)
        item.setFont(font)
        colour = QColor(ROUNDED_COLOUR) if moved else self.table.palette().text().color()
        item.setForeground(colour)
        item.setToolTip(f"Asked {asked:g} m, gets {got:g} m." if moved else "On the ladder: no change.")

    def _flash(self, number: int, *_) -> None:
        layer = self.layer.currentLayer()
        if layer is not None and self.canvas is not None and 0 <= number < len(self.rows):
            self.canvas.flashFeatureIds(layer, [self.rows[number].fid])

    def features(self, crs) -> list:
        """The lines for the job, each with what its row asks."""
        layer = self.layer.currentLayer()
        if layer is None:
            return []
        self._fill()
        by_id = {row.fid: row for row in self.rows}
        return [
            replace(feature, properties=job_properties(by_id[feature.properties["fid"]]))
            for feature in layer_features(layer, crs, with_id=True)
        ]
