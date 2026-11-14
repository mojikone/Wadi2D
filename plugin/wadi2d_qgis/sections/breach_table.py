# Wadi2D QGIS plugin. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""The dam breach table of the Structures section (W63): a row per breach of a named dam line, Add and Remove."""

from __future__ import annotations

from functools import partial

from qgis.PyQt.QtCore import QSignalBlocker
from qgis.PyQt.QtWidgets import (
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QWidget,
)

from ..breach_rows import BREACHES, MODES, PROGRESSIONS, TRIGGER_HELD, TRIGGER_TIME, TRIGGERS, BreachRow
from .common import number_box

COLUMNS = [
    ("dam", "Dam"),
    ("mode", "Mode"),
    ("bottom_z", "Bottom, m"),
    ("width_m", "Bottom width, m"),
    ("slope", "Side slope, H:V"),
    ("formation_min", "Forms in, min"),
    ("progression", "Growth"),
    ("trigger", "Starts at"),
    ("value", "Level, m or time, h"),
    ("held_min", "Held, min"),
    ("piping_z", "Pipe centre, m"),
]
CHOICES = {"mode": MODES, "progression": PROGRESSIONS, "trigger": TRIGGERS}
DECIMALS = {"slope": 2, "formation_min": 1, "held_min": 1, "value": 2}
UNSET = -1.0e4
"""A number box's floor: shown as "not set"."""
SHOWN_ROWS = 4
NOTE = (
    "A breach opens a named dam line on the uniform grid as HEC-RAS's user-entered breach does: the centre at the "
    "lowest ground under the line, a trapezoid growing to its final bottom and width. Not on the mesh or the corridors."
)


class BreachTable(QWidget):
    """``dams()`` gives the named crest lines and embankments the rows may choose."""

    def __init__(self, dams) -> None:
        super().__init__()
        self.dams = dams
        self.rows: list[BreachRow] = []
        form = QFormLayout(self)
        form.setContentsMargins(0, 0, 0, 0)
        form.setRowWrapPolicy(QFormLayout.WrapLongRows)
        self.note = QLabel(NOTE)
        self.note.setWordWrap(True)
        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels([words for _key, words in COLUMNS])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.verticalHeader().hide()
        self.add_button = QPushButton("Add breach")
        self.remove_button = QPushButton("Remove breach")
        buttons = QHBoxLayout()
        buttons.addWidget(self.add_button)
        buttons.addWidget(self.remove_button)
        buttons.addStretch(1)
        form.addRow("Dam breach", self.note)
        form.addRow(self.table)
        form.addRow(buttons)
        self.add_button.clicked.connect(self.add)
        self.remove_button.clicked.connect(self.remove)
        self.fill()

    def apply_schema(self, schema) -> None:
        for column, (key, _words) in enumerate(COLUMNS):
            path = {"width_m": "bottom_width_m", "slope": "left_slope", "formation_min": "formation_time_s"}.get(key, key)
            path = {"value": "trigger_level", "held_min": "trigger_duration_s"}.get(key, path)
            tip = schema.tip(f"{BREACHES}.{path}")
            if tip:
                self.table.horizontalHeaderItem(column).setToolTip(tip)

    def add(self) -> None:
        names = self.dams()
        self.rows.append(BreachRow(dam=names[0] if names else ""))
        self.fill()

    def remove(self) -> None:
        number = self.table.currentRow()
        if 0 <= number < len(self.rows):
            del self.rows[number]
        elif self.rows:
            self.rows.pop()
        self.fill()

    def fill(self, *_) -> None:
        names = self.dams()
        self.table.setRowCount(len(self.rows))
        for number, row in enumerate(self.rows):
            for column, (key, _words) in enumerate(COLUMNS):
                if key == "dam":
                    widget = QComboBox()
                    for name in names if row.dam in names or not row.dam else [*names, row.dam]:
                        widget.addItem(name, name)
                    widget.setCurrentIndex(max(widget.findData(row.dam), 0))
                    row.dam = widget.currentData() or ""
                    widget.currentIndexChanged.connect(partial(self._choice, row, key, widget))
                elif key in CHOICES:
                    widget = QComboBox()
                    for value, words in CHOICES[key].items():
                        widget.addItem(words, value)
                    widget.setCurrentIndex(widget.findData(getattr(row, key)))
                    widget.currentIndexChanged.connect(partial(self._choice, row, key, widget))
                else:
                    widget = number_box(DECIMALS.get(key, 2))
                    widget.setMinimum(UNSET)
                    widget.setSpecialValueText("not set")
                    with QSignalBlocker(widget):
                        current = getattr(row, key)
                        widget.setValue(UNSET if current is None else current)
                    widget.valueChanged.connect(partial(self._number, row, key))
                self.table.setCellWidget(number, column, widget)
            self._enable(number, row)
        high = self.table.horizontalHeader().height() + self.table.verticalHeader().defaultSectionSize() * SHOWN_ROWS
        self.table.setMaximumHeight(high + 2 * self.table.frameWidth() + self.table.horizontalScrollBar().sizeHint().height())
        self.table.setVisible(bool(self.rows))
        self.remove_button.setEnabled(bool(self.rows))

    def _enable(self, number: int, row: BreachRow) -> None:
        keys = [key for key, _words in COLUMNS]
        self.table.cellWidget(number, keys.index("held_min")).setEnabled(row.trigger == TRIGGER_HELD)
        self.table.cellWidget(number, keys.index("piping_z")).setEnabled(row.mode == "piping")
        value = self.table.cellWidget(number, keys.index("value"))
        value.setToolTip("Run time at which the breach starts, h" if row.trigger == TRIGGER_TIME else "Pool level that starts the breach, m")

    def _choice(self, row: BreachRow, key: str, combo: QComboBox, *_) -> None:
        setattr(row, key, combo.currentData())
        self._enable(self.rows.index(row), row)

    def _number(self, row: BreachRow, key: str, value: float) -> None:
        setattr(row, key, None if value <= UNSET else value)

    def values(self) -> dict:
        self.fill()
        return {"breach_rows": list(self.rows)}
