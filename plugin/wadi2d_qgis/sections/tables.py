# Wadi2D QGIS plugin. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""3b. Data tables (W101): the model's named rain patterns and area-reduction curves, as HEC-HMS keeps paired data.

The Storm section picks a pattern by name, the Area reduction section a curve by name; a job carries only the tables
its storm names (``table_rows.store_job``). Each table is edited here, with its chart.
"""

from __future__ import annotations

import copy

from qgis.PyQt.QtCore import pyqtSignal
from qgis.PyQt.QtWidgets import QComboBox, QHBoxLayout, QLabel, QLineEdit, QPushButton, QWidget

from .. import section_status
from ..pair_chart import PairChart
from ..table_rows import (
    CURVES,
    FORMS,
    NAME_TAKEN,
    NEW_CURVE,
    NEW_PATTERN,
    PATTERNS,
    TIME_UNITS,
    cumulative_share,
    curve_problems,
    new_curve,
    new_pattern,
    new_store,
    pattern_problems,
    unique_name,
)
from .common import Section
from .pair_table import PairTable

KIND_WORDS = {PATTERNS: "Rain patterns", CURVES: "Area-reduction curves"}
BELOW_WORDS = {True: "The first factor holds", False: "No reduction, as HEC-HMS"}
NOTE = (
    "Tables shared by the model, by name: a rain pattern for Depth and pattern or a depth grid in Storm, a curve for "
    "the Area reduction. A run's job carries only the tables its storm reads."
)


def _words(text: str) -> QLabel:
    label = QLabel(text)
    label.setWordWrap(True)
    return label


class DataTablesSection(Section):
    heading = "3b. Data tables"
    start_collapsed = True
    key = "tables"
    state_skip = ("which", "names", "name_edit", "time_units", "form_kind", "below", "pairs")
    """The widgets show one table of the store; the store itself is the saved state (``extra_state``)."""
    tables_changed = pyqtSignal()
    """A table was added, renamed, removed or edited: the sections that read tables by name refresh their choices."""

    def build(self) -> None:
        self.store = new_store()
        self._showing = False
        self.form.addRow(_words(NOTE))
        self.which = QComboBox()
        for key, words in KIND_WORDS.items():
            self.which.addItem(words, key)
        self.names = QComboBox()
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Name of the table")
        self.new_button, self.rename_button, self.remove_button = (
            QPushButton("New"), QPushButton("Rename"), QPushButton("Remove"),
        )  # fmt: skip
        buttons = QWidget()
        row = QHBoxLayout(buttons)
        row.setContentsMargins(0, 0, 0, 0)
        for button in (self.new_button, self.rename_button, self.remove_button):
            row.addWidget(button)
        self.time_units = QComboBox()
        for key, words in TIME_UNITS.items():
            self.time_units.addItem(words, key)
        self.form_kind = QComboBox()
        for key, words in FORMS.items():
            self.form_kind.addItem(words, key)
        self.below = QComboBox()
        for key, words in BELOW_WORDS.items():
            self.below.addItem(words, key)
        self.pairs = PairTable("Time", "Depth")
        self.chart = PairChart()
        self.problem = _words("")
        self.form.addRow("Tables of", self.which)
        self.form.addRow("Table", self.names)
        self.form.addRow("Name", self.name_edit)
        self.form.addRow(buttons)
        self.form.addRow("Time in", self.time_units)
        self.form.addRow("Depth given as", self.form_kind)
        self.form.addRow("Below the smallest area", self.below)
        self.form.addRow(self.pairs)
        self.form.addRow(self.chart)
        self.form.addRow(self.problem)
        self.which.currentIndexChanged.connect(self._show_kind)
        self.names.currentIndexChanged.connect(self._show_table)
        self.new_button.clicked.connect(self._new)
        self.rename_button.clicked.connect(self._rename)
        self.remove_button.clicked.connect(self._remove)
        self.pairs.changed.connect(self._edited)
        for combo in (self.time_units, self.form_kind, self.below):
            combo.currentIndexChanged.connect(self._edited)
        self._show_kind()

    # What is shown

    def kind(self) -> str:
        return self.which.currentData()

    def current(self) -> str | None:
        name = self.names.currentText()
        return name if name in self.store[self.kind()] else None

    def _show_kind(self, *_) -> None:
        patterns = self.kind() == PATTERNS
        for widget in (self.time_units, self.form_kind):
            widget.setVisible(patterns)
            self.form.labelForField(widget).setVisible(patterns)
        self.below.setVisible(not patterns)
        self.form.labelForField(self.below).setVisible(not patterns)
        if patterns:
            self.pairs.set_headers("Time", "Depth")
        else:
            self.pairs.set_headers("Area, km2", "Factor")
        self._fill_names(None)

    def _fill_names(self, wanted: str | None) -> None:
        names = sorted(self.store[self.kind()])
        self.names.blockSignals(True)
        self.names.clear()
        self.names.addItems(names)
        if wanted in names:
            self.names.setCurrentText(wanted)
        self.names.blockSignals(False)
        self._show_table()

    def _show_table(self, *_) -> None:
        name = self.current()
        self._showing = True
        try:
            for widget in (self.pairs, self.time_units, self.form_kind, self.below, self.rename_button, self.remove_button):
                widget.setEnabled(name is not None)
            self.name_edit.setText(name or "")
            if name is None:
                self.pairs.set_rows([])
            elif self.kind() == PATTERNS:
                table = self.store[PATTERNS][name]
                self.time_units.setCurrentIndex(max(self.time_units.findData(table.get("time_units", "percent")), 0))
                self.form_kind.setCurrentIndex(max(self.form_kind.findData(table.get("form", "cumulative")), 0))
                self.pairs.set_rows(list(zip(table["time"], table["depth"], strict=False)))
            else:
                table = self.store[CURVES][name]
                self.below.setCurrentIndex(max(self.below.findData(bool(table.get("reduces_below_table", True))), 0))
                self.pairs.set_rows(list(zip(table["areas_km2"], table["factors"], strict=False)))
        finally:
            self._showing = False
        self._draw()

    def _draw(self) -> None:
        name = self.current()
        if name is None:
            self.chart.show_pairs([], [], "")
            self.problem.setText("")
            return
        if self.kind() == PATTERNS:
            table = self.store[PATTERNS][name]
            xs, ys = cumulative_share(table)
            units = TIME_UNITS[table.get("time_units", "percent")]
            self.chart.show_pairs(xs, ys, f"{name}: share of the depth fallen", x_label=f"Time, {units}", y_label="Share")
            found = pattern_problems(name, table)
        else:
            table = self.store[CURVES][name]
            self.chart.show_pairs(
                table["areas_km2"], table["factors"], f"{name}: factor by storm area", log_x=True,
                x_label="Storm area, km2", y_label="Factor", from_zero=False,
            )  # fmt: skip
            found = curve_problems(name, table)
        self.problem.setText(" ".join(found))

    # Editing

    def _edited(self, *_) -> None:
        name = self.current()
        if self._showing or name is None:
            return
        rows = self.pairs.rows()
        if self.kind() == PATTERNS:
            self.store[PATTERNS][name] = {
                "time": [r[0] for r in rows], "depth": [r[1] for r in rows],
                "time_units": self.time_units.currentData(), "form": self.form_kind.currentData(),
            }  # fmt: skip
        else:
            self.store[CURVES][name] = {
                "areas_km2": [r[0] for r in rows], "factors": [r[1] for r in rows],
                "reduces_below_table": bool(self.below.currentData()),
            }  # fmt: skip
        self._draw()
        self.tables_changed.emit()

    def add_table(self, kind: str, name: str, table: dict | None = None) -> str:
        """A table into the store, under ``name`` or the next free one like it; shown at once. Returns its name."""
        name = unique_name(name, self.store[kind])
        self.store[kind][name] = copy.deepcopy(table) if table is not None else (new_pattern() if kind == PATTERNS else new_curve())
        self.which.setCurrentIndex(self.which.findData(kind))
        self._fill_names(name)
        self.tables_changed.emit()
        return name

    def rename(self, kind: str, old: str, new: str) -> str:
        """Rename a table; the empty string when it is done, else why not."""
        new = new.strip()
        if not new or old not in self.store[kind]:
            return "Give the table a name."
        if new != old and new in self.store[kind]:
            return NAME_TAKEN.format(name=new)
        self.store[kind][new] = self.store[kind].pop(old)
        self._fill_names(new)
        self.tables_changed.emit()
        return ""

    def remove(self, kind: str, name: str) -> None:
        self.store[kind].pop(name, None)
        self._fill_names(None)
        self.tables_changed.emit()

    def _new(self) -> None:
        self.add_table(self.kind(), NEW_PATTERN if self.kind() == PATTERNS else NEW_CURVE)

    def _rename(self) -> None:
        name = self.current()
        if name is not None:
            self.problem.setText(self.rename(self.kind(), name, self.name_edit.text()))

    def _remove(self) -> None:
        name = self.current()
        if name is not None:
            self.remove(self.kind(), name)

    # The saved model and the job

    def extra_state(self) -> dict:
        return {"store": copy.deepcopy(self.store)}

    def restore_extra(self, extra: dict, add_missing: bool = False) -> list[str]:
        held = extra.get("store") or {}
        self.store = {PATTERNS: dict(held.get(PATTERNS) or {}), CURVES: dict(held.get(CURVES) or {})}
        self._fill_names(None)
        self.tables_changed.emit()
        return []

    def standing(self, kind=None):
        return section_status.tables(self.store)

    def values(self, crs) -> dict:
        return {"data_tables": copy.deepcopy(self.store)}
