# Wadi2D QGIS plugin. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""A two-column table of numbers: add a row, drop one, or paste from a spreadsheet. The Storm section's since W20;
here since W101, so Data tables, the area reduction and the inflow tables share it."""

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

from ..storm_rows import pasted_rows

TABLE_ROWS = 8


class PairTable(QWidget):
    changed = pyqtSignal()
    """A cell, a row added or removed, or a paste: the rows may differ."""

    def __init__(self, first: str, second: str) -> None:
        super().__init__()
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels([first, second])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.verticalHeader().hide()
        self.table.setMinimumHeight(self.table.fontMetrics().height() * TABLE_ROWS)
        self.add_button = QPushButton("Add row")
        self.drop_button = QPushButton("Remove row")
        self.paste_button = QPushButton("Paste")
        self.paste_button.setToolTip("Two columns from a spreadsheet or a text file; a heading line is left out")
        buttons = QHBoxLayout()
        for button in (self.add_button, self.drop_button, self.paste_button):
            buttons.addWidget(button)
        column = QFormLayout(self)
        column.setContentsMargins(0, 0, 0, 0)
        column.addRow(self.table)
        column.addRow(buttons)
        self.add_button.clicked.connect(self._add)
        self.drop_button.clicked.connect(self._drop)
        self.paste_button.clicked.connect(lambda: self.set_rows(pasted_rows(QApplication.clipboard().text())))
        self.table.itemChanged.connect(lambda _item: self.changed.emit())

    def _add(self) -> None:
        self.table.insertRow(self.table.rowCount())
        self.changed.emit()

    def _drop(self) -> None:
        row = self.table.currentRow()
        self.table.removeRow(row if row >= 0 else self.table.rowCount() - 1)
        self.changed.emit()

    def set_headers(self, first: str, second: str) -> None:
        self.table.setHorizontalHeaderLabels([first, second])

    def set_rows(self, rows: list[tuple[float, ...]]) -> None:
        self.table.blockSignals(True)
        self.table.setRowCount(len(rows))
        for n, row in enumerate(rows):
            for m, value in enumerate(row):
                self.table.setItem(n, m, QTableWidgetItem(f"{value:.10g}"))  # W101: was :g, six digits
        self.table.blockSignals(False)
        self.changed.emit()

    def rows(self) -> list[tuple[float, float]]:
        """The filled rows; a cell that is not a number leaves its row out, and the check on the table says so."""
        found = []
        for row in range(self.table.rowCount()):
            cells = [self.table.item(row, m) for m in (0, 1)]
            text = [cell.text().strip() if cell is not None else "" for cell in cells]
            try:
                found.append((float(text[0]), float(text[1])))
            except ValueError:
                continue
        return found
