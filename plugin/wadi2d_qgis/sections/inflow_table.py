# Wadi2D QGIS plugin. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Point inflows of lumped elements (W103): a table of the points where a dam's, a junction's or a reach's outflow enters
the 2D grid, ``hydrology.inflows``. The rows are plain tuples (:mod:`entry_rows`), so the table is saved with the model
as a pair table is: ``rows`` and ``set_rows``. Click on the map adds a row at the point clicked (the dock's tool)."""

from __future__ import annotations

from qgis.PyQt.QtCore import QSignalBlocker, Qt, pyqtSignal
from qgis.PyQt.QtWidgets import (
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QWidget,
)

from ..entry_rows import ENTRY_POINT, INFLOW_COLUMNS, INFLOW_ENTRY_WORDS

NAME, ELEMENT, X, Y, ENTRY, ENTERS = range(len(INFLOW_COLUMNS))
SHOWN_ROWS = 4
TIP = (
    "Where a lumped element's outflow enters the 2D grid: a dam, a junction or a reach of the basin, at a point in the "
    "DEM's coordinates. The subbasins above it are carried by it, so each needs no outlet of its own (Outlet 'none' in "
    "the subbasin table), and with the catchments left out of the mesh they leave it. Unticked, the element's water "
    "leaves the model there, as at an HMS sink."
)


class InflowTable(QWidget):
    changed = pyqtSignal()
    place_requested = pyqtSignal()
    """The next map click adds a row at its point."""
    place_stopped = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()
        self.choices: list[str] = []
        self.table = QTableWidget(0, len(INFLOW_COLUMNS))
        self.table.setHorizontalHeaderLabels(list(INFLOW_COLUMNS))
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Stretch)
        self.table.verticalHeader().hide()
        self.table.setToolTip(TIP)
        high = header.height() + self.table.verticalHeader().defaultSectionSize() * SHOWN_ROWS
        self.table.setMinimumHeight(high + 2 * self.table.frameWidth())
        self.add_button, self.drop_button = QPushButton("Add row"), QPushButton("Remove row")
        self.place_button = QPushButton("Click on the map")
        self.place_button.setCheckable(True)
        self.place_button.setToolTip("One click adds a point inflow at that point, in the DEM's coordinates")
        self.note = QLabel("")
        self.note.setWordWrap(True)
        buttons = QHBoxLayout()
        for button in (self.add_button, self.drop_button, self.place_button):
            buttons.addWidget(button)
        form = QFormLayout(self)
        form.setContentsMargins(0, 0, 0, 0)
        form.addRow(QLabel("Point inflows of lumped elements"))
        form.addRow(self.table)
        form.addRow(buttons)
        form.addRow(self.note)
        self.add_button.clicked.connect(
            lambda: self._append(("", self.choices[0] if self.choices else "", None, None, ENTRY_POINT, True))
        )
        self.drop_button.clicked.connect(self._drop)
        self.place_button.toggled.connect(
            lambda on: self.place_requested.emit() if on else self.place_stopped.emit()
        )
        self.table.itemChanged.connect(lambda _item: self.changed.emit())

    def set_choices(self, choices: list[str]) -> None:
        """The elements of the basin in use, offered in each row's Element; a name typed stays."""
        self.choices = list(choices)
        for number in range(self.table.rowCount()):
            combo = self.table.cellWidget(number, ELEMENT)
            held = combo.currentText()
            with QSignalBlocker(combo):
                combo.clear()
                combo.addItems(self.choices)
                combo.setCurrentText(held)

    def _drop(self) -> None:
        row = self.table.currentRow()
        if self.table.rowCount():
            self.table.removeRow(row if row >= 0 else self.table.rowCount() - 1)
        self.changed.emit()

    def _append(self, row: tuple) -> None:
        name, element, x, y, entry, enters = row
        number = self.table.rowCount()
        with QSignalBlocker(self.table):
            self.table.insertRow(number)
            self.table.setItem(number, NAME, QTableWidgetItem(str(name)))
            combo = QComboBox()
            combo.setEditable(True)  # an element the list does not hold is the engine's to refuse, in words
            combo.addItems(self.choices)
            combo.setCurrentText(str(element or ""))
            combo.currentTextChanged.connect(lambda _text: self.changed.emit())
            self.table.setCellWidget(number, ELEMENT, combo)
            for column, value in ((X, x), (Y, y)):
                self.table.setItem(
                    number, column, QTableWidgetItem("" if value is None else f"{float(value):.15g}")
                )
            how = QComboBox()
            for key, words in INFLOW_ENTRY_WORDS.items():
                how.addItem(words, key)
            how.setCurrentIndex(max(how.findData(entry or ENTRY_POINT), 0))
            how.currentIndexChanged.connect(lambda _index: self.changed.emit())
            self.table.setCellWidget(number, ENTRY, how)
            tick = QTableWidgetItem("")
            tick.setFlags((tick.flags() | Qt.ItemIsUserCheckable) & ~Qt.ItemIsEditable)
            tick.setCheckState(Qt.Checked if enters else Qt.Unchecked)
            self.table.setItem(number, ENTERS, tick)
        self.changed.emit()

    def add_point(self, x: float, y: float) -> None:
        """A row at a point clicked on the map, named after its place in the table."""
        with QSignalBlocker(self.place_button):
            self.place_button.setChecked(False)
        taken = {row[0] for row in self.rows()}
        number = self.table.rowCount() + 1
        while f"Inflow {number}" in taken:
            number += 1
        self._append((f"Inflow {number}", self.choices[0] if self.choices else "", x, y, ENTRY_POINT, True))
        self.note.setText(f"Inflow {number} added at {x:.1f}, {y:.1f}: choose its element.")

    def stop_placing(self) -> None:
        with QSignalBlocker(self.place_button):
            self.place_button.setChecked(False)

    @staticmethod
    def _number(item):
        try:
            return float(item.text()) if item is not None and item.text().strip() else None
        except ValueError:
            return None

    def rows(self) -> list[tuple]:
        """Every row as ``(name, element, x, y, entry, enters)``; a coordinate that is no number is None."""
        found = []
        for number in range(self.table.rowCount()):
            name = self.table.item(number, NAME)
            tick = self.table.item(number, ENTERS)
            found.append((
                name.text().strip() if name is not None else "",
                self.table.cellWidget(number, ELEMENT).currentText().strip(),
                self._number(self.table.item(number, X)), self._number(self.table.item(number, Y)),
                self.table.cellWidget(number, ENTRY).currentData() or ENTRY_POINT,
                tick is None or tick.checkState() == Qt.Checked,
            ))  # fmt: skip
        return found

    def set_rows(self, rows: list[tuple]) -> None:
        with QSignalBlocker(self.table):
            self.table.setRowCount(0)
        for row in rows or []:
            name, element, x, y, *rest = tuple(row)
            entry = rest[0] if len(rest) > 0 else ENTRY_POINT
            enters = bool(rest[1]) if len(rest) > 1 else True
            self._append((name, element, x, y, entry, enters))
        self.changed.emit()
