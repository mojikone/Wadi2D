# Wadi2D QGIS plugin. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""A table of gauges: the Storm section's rain gauges and the Gauges section's flow and level gauges (W77).

W54 held all three kinds in one table of the Gauges section; his word of 2026-11-14 put the rain in one place, the
Storm section. The rows are ``gauge_rows.GaugeRow`` as before, so what each table writes is what that one table wrote.
A point layer, offered on the rain table only, fills it with a row per point at its position.
"""

from __future__ import annotations

from functools import partial

from qgis.core import QgsMapLayerProxyModel
from qgis.gui import QgsFileWidget
from qgis.PyQt.QtCore import QSignalBlocker, Qt
from qgis.PyQt.QtWidgets import (
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QWidget,
)

from ..gauge_rows import KIND_WORDS, RAIN, GaugeRow, merge_rows, position_text, read_position
from ..job_builder import layer_features
from .common import field_combo, layer_combo

RECORD_FILES = "Station records (*.csv *.txt *.tsv *.dat *.dss);;All files (*)"
SHOWN_ROWS = 6
SERIES_TIP = "The column heading in a CSV, or the DSS pathname or its B/C parts; empty takes the only one."


class GaugeTable(QWidget):
    """Rows of gauges of the given kinds; ``points`` offers a point layer whose points become rows."""

    def __init__(self, kinds: tuple[str, ...], at_heading: str, at_tip: str, points: bool = False) -> None:
        super().__init__()
        self.kinds = kinds
        self.rows: list[GaugeRow] = []
        self._watched = None
        headings = ["Name", *(["Gauge"] if len(kinds) > 1 else []), "Record", "Series", at_heading]
        self.name_column = 0
        self.kind_column = 1 if len(kinds) > 1 else None
        self.file_column, self.series_column, self.at_column = range(len(headings) - 3, len(headings))
        self.table = QTableWidget(0, len(headings))
        self.table.setHorizontalHeaderLabels(headings)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.verticalHeader().hide()
        self.table.horizontalHeaderItem(self.series_column).setToolTip(SERIES_TIP)
        self.table.horizontalHeaderItem(self.at_column).setToolTip(at_tip)
        self.add_buttons = {kind: QPushButton(f"Add {KIND_WORDS[kind].lower()} gauge") for kind in kinds}
        self.remove_button = QPushButton("Remove gauge")
        buttons = QHBoxLayout()
        for button in (*self.add_buttons.values(), self.remove_button):
            buttons.addWidget(button)
        form = QFormLayout(self)
        form.setContentsMargins(0, 0, 0, 0)
        self.layer = self.name_field = None
        if points:
            self.layer = layer_combo(QgsMapLayerProxyModel.PointLayer, "None")
            self.layer.setToolTip(
                "A point layer of rain gauges: each point a row of the table, at its position."
            )
            self.name_field = field_combo(self.layer)
            form.addRow("Rain gauge points", self.layer)
            form.addRow("Name field", self.name_field)
            self.layer.layerChanged.connect(self._layer_changed)
            self.name_field.fieldChanged.connect(self._fill)
        form.addRow(self.table)
        form.addRow(buttons)
        for kind, button in self.add_buttons.items():
            button.clicked.connect(partial(self.add_row, kind))
        self.remove_button.clicked.connect(self._remove)
        self.table.itemChanged.connect(self._edited)
        self._show()

    # Rows

    def add_row(self, kind: str) -> GaugeRow:
        taken = {row.name for row in self.rows}
        number = len(self.rows) + 1
        while f"G{number}" in taken:
            number += 1
        row = GaugeRow(f"G{number}", kind)
        self.rows.append(row)
        self._show()
        return row

    def _remove(self) -> None:
        index = self.table.currentRow()
        index = index if index >= 0 else len(self.rows) - 1
        if 0 <= index < len(self.rows) and not self.rows[index].from_layer:
            self.rows.pop(index)
            self._show()

    def _layer_changed(self, layer) -> None:
        if self._watched is not None:
            self._watched.dataChanged.disconnect(self._fill)
        self._watched = layer
        if layer is not None:
            layer.dataChanged.connect(self._fill)
        self._fill()

    def _named(self, crs):
        layer = self.layer.currentLayer() if self.layer is not None else None
        if layer is None:
            return []
        field = self.name_field.currentField()
        return list(layer_features(layer, crs or layer.crs(), {"name": field} if field else None))

    def _fill(self, *_) -> None:
        if self.layer is None:
            return
        points = [
            (str(feature.properties.get("name") or f"Gauge {number}"), *feature.coordinates[:2])
            for number, feature in enumerate(self._named(None), start=1)
        ]
        self.rows = merge_rows(points, self.rows)
        self._show()

    def _show(self) -> None:
        with QSignalBlocker(self.table):
            self.table.setRowCount(len(self.rows))
            for number, row in enumerate(self.rows):
                self._show_row(number, row)
        high = (
            self.table.horizontalHeader().height()
            + self.table.verticalHeader().defaultSectionSize() * SHOWN_ROWS
        )
        self.table.setMaximumHeight(high + 2 * self.table.frameWidth())

    def _show_row(self, number: int, row: GaugeRow) -> None:
        fixed = row.from_layer
        for column, text in (
            (self.name_column, row.name), (self.series_column, row.series), (self.at_column, position_text(row)),
        ):  # fmt: skip
            item = QTableWidgetItem(text)
            if fixed and column in (self.name_column, self.at_column):
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)  # the layer's name and point
            self.table.setItem(number, column, item)
        if self.kind_column is not None:
            kind = QComboBox()
            for key in self.kinds:
                kind.addItem(KIND_WORDS[key], key)
            kind.setCurrentIndex(kind.findData(row.kind))
            kind.setEnabled(not fixed)
            kind.currentIndexChanged.connect(partial(self._row_kind, row, kind))
            self.table.setCellWidget(number, self.kind_column, kind)
        record = QgsFileWidget()
        record.setFilter(RECORD_FILES)
        record.setDialogTitle(f"Record of gauge {row.name}")
        record.setFilePath(row.file)
        record.fileChanged.connect(partial(self._row_file, row))
        self.table.setCellWidget(number, self.file_column, record)

    def _row_kind(self, row: GaugeRow, combo: QComboBox, *_) -> None:
        row.kind = combo.currentData()
        self._show()

    def _row_file(self, row: GaugeRow, path: str) -> None:
        row.file = path

    def _edited(self, item: QTableWidgetItem) -> None:
        index = item.row()
        if not 0 <= index < len(self.rows):
            return
        row, text = self.rows[index], item.text().strip()
        if item.column() == self.name_column:
            row.name = text
        elif item.column() == self.series_column:
            row.series = text
        elif item.column() == self.at_column and row.kind == RAIN:
            row.x, row.y = read_position(text) or (None, None)
        elif item.column() == self.at_column:
            row.at = text

    def set_row(self, index: int, **fields) -> None:
        """Change one row and redraw it; for the checks that drive the dock as a user would."""
        for key, value in fields.items():
            setattr(self.rows[index], key, value)
        self._show()

    def current_rows(self, crs) -> list[GaugeRow]:
        """The rows, the layer's points read again in the DEM's coordinates."""
        self._fill()
        moved = iter(feature.coordinates[:2] for feature in self._named(crs))
        for row in self.rows:
            if row.from_layer:
                row.x, row.y = next(moved, (row.x, row.y))
        return list(self.rows)
