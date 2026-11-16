# Wadi2D QGIS plugin. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""A small table of rows typed or pasted, its columns named by its owner (W101): the land-use classes of Manning and
of the curve number, CN ranges, CN by subbasin. Saved with the model as a pair table is: ``rows`` and ``set_rows``."""

from __future__ import annotations

from qgis.PyQt.QtCore import pyqtSignal
from qgis.PyQt.QtWidgets import (
    QApplication,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QWidget,
)

from ..storm_rows import SEPARATOR

SHOWN_ROWS = 6


class ClassTable(QWidget):
    changed = pyqtSignal()

    def __init__(self, columns: tuple[str, ...], text_columns: tuple[int, ...] = ()) -> None:
        super().__init__()
        self.text_columns = set(text_columns)
        self.table = QTableWidget(0, len(columns))
        self.table.setHorizontalHeaderLabels(list(columns))
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.verticalHeader().hide()
        self.table.setMinimumHeight(self.table.fontMetrics().height() * SHOWN_ROWS)
        self.add_button, self.drop_button, self.paste_button = QPushButton("Add row"), QPushButton("Remove row"), QPushButton("Paste")
        self.paste_button.setToolTip("Rows from a spreadsheet or a text file, a column each; a heading line is left out")
        buttons = QHBoxLayout()
        for button in (self.add_button, self.drop_button, self.paste_button):
            buttons.addWidget(button)
        column = QFormLayout(self)
        column.setContentsMargins(0, 0, 0, 0)
        column.addRow(self.table)
        column.addRow(buttons)
        self.add_button.clicked.connect(self._add)
        self.drop_button.clicked.connect(self._drop)
        self.paste_button.clicked.connect(lambda: self.set_rows(self._pasted(QApplication.clipboard().text())))
        self.table.itemChanged.connect(lambda _item: self.changed.emit())

    def set_headers(self, columns: tuple[str, ...], text_columns: tuple[int, ...] = ()) -> None:
        self.text_columns = set(text_columns)
        self.table.setColumnCount(len(columns))
        self.table.setHorizontalHeaderLabels(list(columns))

    def _add(self) -> None:
        self.table.insertRow(self.table.rowCount())
        self.changed.emit()

    def _drop(self) -> None:
        row = self.table.currentRow()
        self.table.removeRow(row if row >= 0 else self.table.rowCount() - 1)
        self.changed.emit()

    def _pasted(self, text: str) -> list[tuple]:
        found = []
        width = self.table.columnCount()
        for line in text.splitlines():
            cells = [cell for cell in (SEPARATOR.split(line.strip()) if "\t" not in line else line.strip().split("\t")) if cell]
            if len(cells) < width:
                continue
            row = self._typed(cells[:width])
            if row is not None:
                found.append(row)
        return found

    def _typed(self, cells: list[str]):
        row = []
        for number, text in enumerate(cells):
            if number in self.text_columns:
                row.append(text.strip())
                continue
            try:
                row.append(float(text))
            except ValueError:
                return None
        return tuple(row)

    def set_rows(self, rows: list[tuple]) -> None:
        self.table.blockSignals(True)
        self.table.setRowCount(len(rows))
        for n, row in enumerate(rows):
            for m, value in enumerate(row):
                text = value if isinstance(value, str) else f"{value:.10g}"
                self.table.setItem(n, m, QTableWidgetItem(text))
        self.table.blockSignals(False)
        self.changed.emit()

    def rows(self) -> list[tuple]:
        """The filled rows; a cell that is not a number where one is wanted leaves its row out."""
        found = []
        for n in range(self.table.rowCount()):
            cells = [self.table.item(n, m) for m in range(self.table.columnCount())]
            row = self._typed([cell.text().strip() if cell is not None else "" for cell in cells])
            if row is not None and all(value != "" for number, value in enumerate(row) if number not in self.text_columns):
                found.append(row)
        return found
