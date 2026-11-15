# Wadi2D QGIS plugin. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""The reach table of section 3 for Muskingum routing (W89): K, X and subreaches per reach, typed or proposed.

Shown when the Reach routing choice is Muskingum. ``Propose K and X`` asks the engine (the dock runs ``wadi2d
muskingum``); what comes back lands in the cells, in italics until edited, with its derivation in the last column.
The job takes what the cells hold and nothing else.
"""

from __future__ import annotations

from qgis.PyQt.QtCore import QSignalBlocker, Qt, pyqtSignal
from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtWidgets import (
    QDoubleSpinBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..muskingum_rows import (
    COLUMN_TIPS,
    COLUMNS,
    EDITABLE,
    WORDS_COLUMN,
    ReachRow,
    apply_proposals,
    cell_text,
    job_rows,
    merge_reaches,
    set_cell,
    table_note,
)

PROBLEM_COLOUR = "#b00000"
SHOWN_ROWS = 8
MAX_VELOCITY = 20.0
NO_VELOCITY = "None: Kirpich on the reach"


class MuskingumBox(QWidget):
    """The reaches with their K, X and subreaches, a velocity for reaches with no section, and the proposal button."""

    propose_requested = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()
        self.rows: list[ReachRow] = []
        self.generated = False
        self._said = ""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeToContents)
        header.setSectionResizeMode(WORDS_COLUMN, QHeaderView.Stretch)
        self.table.verticalHeader().hide()
        for column, tip in COLUMN_TIPS.items():
            self.table.horizontalHeaderItem(column).setToolTip(tip)
        high = header.height() + self.table.verticalHeader().defaultSectionSize() * SHOWN_ROWS
        self.table.setMaximumHeight(high + 2 * self.table.frameWidth())
        layout.addWidget(self.table)
        row = QHBoxLayout()
        row.addWidget(QLabel("Mean velocity where a reach has no section, m/s"))
        self.velocity = QDoubleSpinBox()
        self.velocity.setDecimals(2)
        self.velocity.setRange(0.0, MAX_VELOCITY)
        self.velocity.setSpecialValueText(NO_VELOCITY)
        self.velocity.setToolTip(
            "Only for a reach with no channel section: K is its length over 1.5 times this velocity (EM 1110-2-1417). "
            "Left at none, K is Kirpich's expression on the reach's length and slope, a rough start."
        )
        row.addWidget(self.velocity)
        self.button = QPushButton("Propose K and X")
        self.button.setToolTip(
            "Asks the engine for K, X and subreaches of every reach you have not typed: Cunge's relations at the "
            "reference flow where the reach has a section (at the flow of its index celerity where you give none), "
            "else from its length. The proposal fills the cells, where you can read how it was derived and change it; "
            "nothing is used that the table does not show."
        )
        row.addWidget(self.button)
        layout.addLayout(row)
        self.note = QLabel("")
        self.note.setWordWrap(True)
        layout.addWidget(self.note)
        self.table.cellChanged.connect(self._edited)
        self.button.clicked.connect(self.propose_requested)

    def set_reaches(self, names: list[str], generated: bool) -> None:
        """The reaches of the basin now chosen; a reach still there keeps its numbers."""
        self.rows = merge_reaches(names, self.rows)
        self.generated = generated
        self._said = ""
        self._show()

    def _show(self) -> None:
        with QSignalBlocker(self.table):
            self.table.setRowCount(len(self.rows))
            for number, row in enumerate(self.rows):
                for column in range(len(COLUMNS)):
                    text = cell_text(row, column)
                    item = QTableWidgetItem(text)
                    if column not in EDITABLE:
                        item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                        item.setToolTip(text)
                    else:
                        item.setToolTip(COLUMN_TIPS[column])
                        font = item.font()
                        font.setItalic(row.proposed and column != EDITABLE[0])
                        item.setFont(font)
                    if row.problems and column == WORDS_COLUMN:
                        item.setForeground(QColor(PROBLEM_COLOUR))
                    self.table.setItem(number, column, item)
        self.note.setText(" ".join(part for part in (self._said, table_note(self.rows, self.generated)) if part))

    def _edited(self, number: int, column: int) -> None:
        if column in EDITABLE and 0 <= number < len(self.rows):
            set_cell(self.rows[number], column, self.table.item(number, column).text())
            self._show()

    def say(self, text: str) -> None:
        self._said = text
        self._show()

    def set_busy(self, busy: bool) -> None:
        self.button.setEnabled(not busy)

    def take(self, found: dict) -> None:
        """The engine's proposals, into the rows the user has not typed."""
        self._said = apply_proposals(self.rows, found)
        self._show()

    def velocity_ms(self) -> float | None:
        return self.velocity.value() or None

    def values(self) -> list[dict]:
        return job_rows(self.rows)
