# Wadi2D QGIS plugin. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""The last points of the lumped model (W105): the dams the basin holds, each ticked, and the junctions added to them,
from the basin's junctions or by a click on the map (the nearest junction's icon). The rows are plain tuples
(:mod:`last_point_rows`), saved with the model by Hydrology."""

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

from ..last_point_rows import DAM, JUNCTION, KIND_WORDS, TIP, default_rows, merge, nearest_junction

COLUMNS = ("Last point", "Kind", "Ends the lumped model")
NAME, KIND, ENDS = range(len(COLUMNS))
SHOWN_ROWS = 4
PICK_WORDS = "Nearest junction to the click: {name}, {distance:.0f} m from its icon."
NO_ICON = "No junction of the basin has an icon to pick: choose one from the list."


class LastPointsTable(QWidget):
    changed = pyqtSignal()
    place_requested = pyqtSignal()
    """The next map click adds the junction whose icon lies nearest."""
    place_stopped = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()
        self.dams: list[str] = []
        self.junctions: list[str] = []
        self.icons: dict[str, tuple[float, float]] = {}
        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(list(COLUMNS))
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Stretch)
        self.table.verticalHeader().hide()
        self.table.setToolTip(TIP)
        high = header.height() + self.table.verticalHeader().defaultSectionSize() * SHOWN_ROWS
        self.table.setMinimumHeight(high + 2 * self.table.frameWidth())
        self.junction = QComboBox()
        self.junction.setToolTip("A junction of the basin to end the lumped model at, as a dam does")
        self.add_button = QPushButton("Add a junction")
        self.drop_button = QPushButton("Remove junction")
        self.place_button = QPushButton("Pick on the map")
        self.place_button.setCheckable(True)
        self.place_button.setToolTip("One click adds the junction whose HMS icon lies nearest")
        self.note = QLabel("")
        self.note.setWordWrap(True)
        buttons = QHBoxLayout()
        for widget in (self.junction, self.add_button, self.drop_button, self.place_button):
            buttons.addWidget(widget)
        form = QFormLayout(self)
        form.setContentsMargins(0, 0, 0, 0)
        heading = QLabel("Last points of the lumped model")
        heading.setToolTip(TIP)
        form.addRow(heading)
        form.addRow(self.table)
        form.addRow(buttons)
        form.addRow(self.note)
        self.add_button.clicked.connect(lambda: self.add_junction(self.junction.currentText()))
        self.drop_button.clicked.connect(self._drop)
        self.place_button.toggled.connect(
            lambda on: self.place_requested.emit() if on else self.place_stopped.emit()
        )
        self.table.itemChanged.connect(lambda _item: self.changed.emit())

    def set_candidates(
        self, dams: list[str], junctions: list[str], icons: dict[str, tuple[float, float]]
    ) -> None:
        """The basin in use: its dams (each ticked unless the rows held say otherwise) and its junctions to add."""
        self.dams, self.junctions, self.icons = list(dams), list(junctions), dict(icons)
        with QSignalBlocker(self.junction):
            self.junction.clear()
            self.junction.addItems(self.junctions)
        self.set_rows(merge(self.rows(), self.dams) if self.table.rowCount() else default_rows(self.dams))

    def _append(self, name: str, kind: str, ticked: bool) -> None:
        number = self.table.rowCount()
        with QSignalBlocker(self.table):
            self.table.insertRow(number)
            item = QTableWidgetItem(name)
            item.setFlags(item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(number, NAME, item)
            what = QTableWidgetItem(KIND_WORDS.get(kind, kind))
            what.setFlags(what.flags() & ~Qt.ItemIsEditable)
            what.setData(Qt.UserRole, kind)
            self.table.setItem(number, KIND, what)
            tick = QTableWidgetItem("")
            tick.setFlags((tick.flags() | Qt.ItemIsUserCheckable) & ~Qt.ItemIsEditable)
            tick.setCheckState(Qt.Checked if ticked else Qt.Unchecked)
            self.table.setItem(number, ENDS, tick)

    def add_junction(self, name: str) -> None:
        name = (name or "").strip()
        if not name:
            return
        if name in {row[0] for row in self.rows()}:
            self.note.setText(f"{name} is a last point already.")
            return
        self._append(name, JUNCTION, True)
        self.note.setText(f"{name} added: the lumped model ends there too.")
        self.changed.emit()

    def _drop(self) -> None:
        """The selected junction, or the last one; a dam is unticked, never removed: the basin holds it."""
        row = self.table.currentRow()
        rows = self.rows()
        junctions = [n for n, (_name, kind, _on) in enumerate(rows) if kind != DAM]
        if not junctions:
            self.note.setText(
                "Only an added junction can be removed: untick a dam to let the lumped water pass it."
            )
            return
        number = row if row in junctions else junctions[-1]
        self.table.removeRow(number)
        self.changed.emit()

    def add_point(self, x: float, y: float) -> None:
        """A click on the map: the junction whose icon lies nearest."""
        with QSignalBlocker(self.place_button):
            self.place_button.setChecked(False)
        found = nearest_junction(self.icons, self.junctions, x, y)
        if found is None:
            self.note.setText(NO_ICON)
            return
        self.add_junction(found[0])
        self.note.setText(PICK_WORDS.format(name=found[0], distance=found[1]))

    def stop_placing(self) -> None:
        with QSignalBlocker(self.place_button):
            self.place_button.setChecked(False)

    def rows(self) -> list[tuple[str, str, bool]]:
        found = []
        for number in range(self.table.rowCount()):
            name, kind, tick = (self.table.item(number, column) for column in (NAME, KIND, ENDS))
            found.append((
                name.text() if name is not None else "", kind.data(Qt.UserRole) if kind is not None else JUNCTION,
                tick is None or tick.checkState() == Qt.Checked,
            ))  # fmt: skip
        return found

    def set_rows(self, rows: list[tuple]) -> None:
        with QSignalBlocker(self.table):
            self.table.setRowCount(0)
        for name, kind, ticked in rows or []:
            self._append(str(name), str(kind), bool(ticked))
        self.changed.emit()
