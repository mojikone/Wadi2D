# Wadi2D QGIS plugin. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""7b. Gauges: rain gauges for the storm, and flow and level gauges to check the run against, as in HEC-HMS.

A point layer of gauges fills the table with rain gauges at their points; rows added by hand take a position typed as
x, y. A flow gauge names a result line or a lumped element, a level gauge a result point. Each row's record is a CSV
table or a DSS file. The rain goes into the run when the Storm section is set to the rain gauges; flow and level gauges
are compared after every run and drawn in Result lines.
"""

from __future__ import annotations

from functools import partial

from qgis.core import QgsMapLayerProxyModel
from qgis.gui import QgsFileWidget
from qgis.PyQt.QtCore import QSignalBlocker, Qt
from qgis.PyQt.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
)

from ..gauge_rows import (
    FLOW,
    GAP_WORDS,
    INVERSE_DISTANCE,
    KIND_WORDS,
    LEVEL,
    METHOD_WORDS,
    RAIN,
    VALUE_WORDS,
    GaugeRow,
    merge_rows,
    position_text,
    read_position,
)
from ..job_builder import layer_features
from .common import Section, field_combo, layer_combo, number_box

COLUMNS = ["Name", "Gauge", "Record", "Series", "Position x, y, or compared with"]
NAME_COLUMN, KIND_COLUMN, FILE_COLUMN, SERIES_COLUMN, AT_COLUMN = range(5)
RECORD_FILES = "Station records (*.csv *.txt *.tsv *.dat *.dss);;All files (*)"
SHOWN_ROWS = 6
NOTE = (
    "Rain gauges feed the storm when Storm is set to the rain gauges. Flow and level gauges are drawn beside the run's "
    "own series in Result lines, with their agreement. A CSV has the time first, as minutes from the run's start or as "
    "dates, then the values."
)
TIPS = {
    SERIES_COLUMN: "The column heading in a CSV, or the DSS pathname or its B/C parts; empty takes the only one.",
    AT_COLUMN: "A rain gauge: x, y in the DEM's coordinates. A flow gauge: the name of a result line or a lumped "
    "element. A level gauge: the name of a result point.",
}
RADIUS_DECIMALS = 0


class GaugesSection(Section):
    heading = "7b. Gauges (optional)"
    start_collapsed = True

    def build(self) -> None:
        self.rows: list[GaugeRow] = []
        self._watched = None
        self.note = QLabel(NOTE)
        self.note.setWordWrap(True)
        self.layer = layer_combo(QgsMapLayerProxyModel.PointLayer, "None")
        self.layer.setToolTip("A point layer of rain gauges: each point a row of the table, at its position.")
        self.name_field = field_combo(self.layer)
        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.verticalHeader().hide()
        for column, tip in TIPS.items():
            self.table.horizontalHeaderItem(column).setToolTip(tip)
        self.add_buttons = {
            kind: QPushButton(f"Add {words.lower()} gauge") for kind, words in KIND_WORDS.items()
        }
        self.remove_button = QPushButton("Remove gauge")
        buttons = QHBoxLayout()
        for button in (*self.add_buttons.values(), self.remove_button):
            buttons.addWidget(button)
        self.method = QComboBox()
        for key, words in METHOD_WORDS.items():
            self.method.addItem(words, key)
        self.radius = number_box(RADIUS_DECIMALS)
        self.radius.setRange(0.0, 1e7)
        self.radius.setSpecialValueText("Every gauge")
        self.gaps = QComboBox()
        for key, words in GAP_WORDS.items():
            self.gaps.addItem(words, key)
        self.values_kind = QComboBox()
        for key, words in VALUE_WORDS.items():
            self.values_kind.addItem(words, key)
        self.start = QLineEdit()
        self.start.setPlaceholderText("Start of the first period of rain")
        self.start.setToolTip(
            "Date and time the run starts at, as 2021-10-04 00:00, for records written with dates"
        )
        self.form.addRow(self.note)
        self.form.addRow("Rain gauge points", self.layer)
        self.form.addRow("Name field", self.name_field)
        self.form.addRow(self.table)
        self.form.addRow(buttons)
        self.form.addRow("Rain spread by", self.method)
        self.form.addRow("Search radius, m", self.radius)
        self.form.addRow("A gauge with no value", self.gaps)
        self.form.addRow("A rain CSV holds", self.values_kind)
        self.form.addRow("Run starts at", self.start)
        for kind, button in self.add_buttons.items():
            button.clicked.connect(partial(self.add_row, kind))
        self.remove_button.clicked.connect(self._remove)
        self.layer.layerChanged.connect(self._layer_changed)
        self.name_field.fieldChanged.connect(self._fill)
        self.method.currentIndexChanged.connect(self._method_changed)
        self.table.itemChanged.connect(self._edited)
        self._method_changed()

    def apply_schema(self, schema) -> None:
        for path, widget in (
            ("storm.gauges.method", self.method), ("storm.gauges.search_radius_m", self.radius),
            ("storm.gauges.gaps", self.gaps),
        ):  # fmt: skip
            if schema.has(path):
                widget.setToolTip(schema.tip(path))

    def _method_changed(self, *_) -> None:
        self.radius.setEnabled(self.method.currentData() == INVERSE_DISTANCE)

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

    def _points(self) -> list[tuple[str, float, float]]:
        layer = self.layer.currentLayer()
        if layer is None:
            return []
        field = self.name_field.currentField()
        found = []
        for number, feature in enumerate(
            layer_features(layer, layer.crs(), {"name": field} if field else None), start=1
        ):
            found.append((str(feature.properties.get("name") or f"Gauge {number}"), *feature.coordinates[:2]))
        return found

    def _fill(self, *_) -> None:
        self.rows = merge_rows(self._points(), self.rows)
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
            (NAME_COLUMN, row.name),
            (SERIES_COLUMN, row.series),
            (AT_COLUMN, position_text(row)),
        ):
            item = QTableWidgetItem(text)
            if fixed and column in (NAME_COLUMN, AT_COLUMN):
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)  # the layer's name and point
            self.table.setItem(number, column, item)
        kind = QComboBox()
        for key, words in KIND_WORDS.items():
            kind.addItem(words, key)
        kind.setCurrentIndex(kind.findData(row.kind))
        kind.setEnabled(not fixed)
        kind.currentIndexChanged.connect(partial(self._row_kind, row, kind))
        self.table.setCellWidget(number, KIND_COLUMN, kind)
        record = QgsFileWidget()
        record.setFilter(RECORD_FILES)
        record.setDialogTitle(f"Record of gauge {row.name}")
        record.setFilePath(row.file)
        record.fileChanged.connect(partial(self._row_file, row))
        self.table.setCellWidget(number, FILE_COLUMN, record)

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
        if item.column() == NAME_COLUMN:
            row.name = text
        elif item.column() == SERIES_COLUMN:
            row.series = text
        elif item.column() == AT_COLUMN and row.kind == RAIN:
            row.x, row.y = read_position(text) or (None, None)
        elif item.column() == AT_COLUMN:
            row.at = text

    def set_row(self, index: int, **fields) -> None:
        """Change one row and redraw it; for the checks that drive the dock as a user would."""
        for key, value in fields.items():
            setattr(self.rows[index], key, value)
        self._show()

    # To the job

    def values(self, crs) -> dict:
        self._fill()
        layer = self.layer.currentLayer()
        if layer is not None:  # the points again, in the DEM's coordinates this time
            field = self.name_field.currentField()
            placed = layer_features(layer, crs, {"name": field} if field else None)
            moved = iter(feature.coordinates[:2] for feature in placed)
            for row in self.rows:
                if row.from_layer:
                    row.x, row.y = next(moved, (row.x, row.y))
        for row in self.rows:
            if row.kind == RAIN:
                row.values = self.values_kind.currentData()
        settings = {
            "method": self.method.currentData(),
            "radius_m": self.radius.value() if self.radius.value() > 0.0 else None,
            "gaps": self.gaps.currentData(),
            "start": self.start.text().strip(),
        }
        return {"gauges": {"rows": list(self.rows), "settings": settings}}


__all__ = ["FLOW", "LEVEL", "RAIN", "GaugesSection"]
