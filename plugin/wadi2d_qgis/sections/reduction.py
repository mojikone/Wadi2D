# Wadi2D QGIS plugin. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""4b. Area reduction (W101): one setting for the lumped part, one for the 2D part (``storm.area_reduction``, W95).

Each part is a coefficient, a fixed area read on a curve of Data tables, or a curve: the lumped part read at the area
of the element where each subbasin's water enters the grid (W98), the 2D part read by the depth-area study at each of
its storm areas. What a part writes into the job is ``reduction_rows``'s; this side holds the choices and shows the
curve with the factor it gives.
"""

from __future__ import annotations

from qgis.PyQt.QtCore import pyqtSignal
from qgis.PyQt.QtWidgets import QCheckBox, QComboBox, QFormLayout, QGroupBox, QLabel

from .. import section_status
from ..model_types import LUMPED as LUMPED_TYPE
from ..model_types import TWO_D
from ..pair_chart import PairChart
from ..reduction_rows import (
    AREA,
    COEFFICIENT,
    CURVE,
    CURVE_NOTE,
    FORM_WORDS,
    GRID,
    GRID_FORMS,
    HMS_TABLE,
    LUMPED,
    LUMPED_FORMS,
    NONE,
    REDUCED_KINDS,
    STUDY,
    STUDY_NOTE,
    UNUSED_WORDS,
    factor_at,
    part,
)
from ..storm_rows import KIND_HMS
from .common import Section, number_box

HMS_TABLE_WORDS = "The HMS project's table"
HMS_SOURCE = (
    "The rain is the HMS meteorologic file's, with its own area reduction. The tick below is the HMS depth-area way for "
    "a Lumped model."
)
BY_ELEMENT = "Each lumped element at its own drainage area's reduction (the HMS depth-area analysis)"
TITLES = {LUMPED: "Lumped part: rain on the lumped subbasins", GRID: "2D part: rain on the 2D cells"}
AREA_DECIMALS = 3


def _words(text: str = "") -> QLabel:
    label = QLabel(text)
    label.setWordWrap(True)
    return label


class PartBox(QGroupBox):
    """One part's form, its curve, its area or coefficient, and the chart of the curve with the factor at the area."""

    study_wanted = pyqtSignal()

    def __init__(self, which: str) -> None:
        super().__init__(TITLES[which])
        self.which = which
        self.curves: dict = {}
        self._hms = False
        form = QFormLayout(self)
        form.setRowWrapPolicy(QFormLayout.WrapLongRows)
        self.layout_form = form
        self.form = QComboBox()
        for key in LUMPED_FORMS if which == LUMPED else GRID_FORMS:
            self.form.addItem(FORM_WORDS[key], key)
        self.curve = QComboBox()
        self.area = number_box(AREA_DECIMALS)
        self.area.setRange(0.0, 1e7)
        self.single = number_box(AREA_DECIMALS)
        self.single.setRange(0.0, 1e7)
        self.single.setToolTip("The storm area a single Run reads the curve at; the study runs at its own areas")
        self.coefficient = number_box(4)
        self.coefficient.setRange(0.0, 1.0)
        self.coefficient.setSingleStep(0.05)
        self.coefficient.setValue(1.0)
        self.coefficient.setToolTip("Every depth of this part is multiplied by it: 0.7 is a 30 % reduction")
        self.factor = _words()
        self.note = _words()
        self.chart = PairChart("Storm area, km2", "Factor")
        form.addRow("Reduction", self.form)
        form.addRow("Curve", self.curve)
        form.addRow("Storm area, km2", self.area)
        form.addRow("A single Run reads it at, km2", self.single)
        form.addRow("Coefficient", self.coefficient)
        form.addRow(self.factor)
        form.addRow(self.note)
        form.addRow(self.chart)
        self.form.currentIndexChanged.connect(self._shown)
        self.curve.currentIndexChanged.connect(self._draw)
        self.area.valueChanged.connect(self._draw)
        self.single.valueChanged.connect(self._draw)
        self._shown()

    def _row(self, widget, on: bool) -> None:
        widget.setVisible(on)
        label = self.layout_form.labelForField(widget)
        if label is not None:
            label.setVisible(on)

    def _shown(self, *_) -> None:
        form = self.form.currentData()
        self._row(self.curve, form in (AREA, CURVE, STUDY))
        self._row(self.area, form == AREA)
        self._row(self.single, form == STUDY)
        self._row(self.coefficient, form == COEFFICIENT)
        self.chart.setVisible(form in (AREA, CURVE, STUDY))
        self.note.setText(CURVE_NOTE if form == CURVE else (STUDY_NOTE if form == STUDY else ""))
        self.note.setVisible(form in (CURVE, STUDY))
        self._draw()
        if form == STUDY:
            self.study_wanted.emit()

    def set_curves(self, curves: dict, hms: bool) -> None:
        """The curves of Data tables and, with an HMS project, its own table; the choice held where it still is."""
        self.curves, self._hms = curves, hms
        held = self.curve.currentData() or self.curve.currentText()
        self.curve.blockSignals(True)
        self.curve.clear()
        for name in sorted(curves):
            self.curve.addItem(name, name)
        if hms:
            self.curve.addItem(HMS_TABLE_WORDS, HMS_TABLE)
        index = self.curve.findData(held)
        if index < 0 and held:  # a name Data tables no longer holds: kept, so the status names it
            self.curve.addItem(held, held)
            index = self.curve.count() - 1
        self.curve.setCurrentIndex(max(index, 0) if self.curve.count() else -1)
        self.curve.blockSignals(False)
        self._draw()

    def _draw(self, *_) -> None:
        form = self.form.currentData()
        name = self.curve.currentData()
        table = self.curves.get(name)
        at = self.area.value() if form == AREA else (self.single.value() if form == STUDY else 0.0)
        if form not in (AREA, CURVE, STUDY):
            self.factor.setText("")
            return
        if name == HMS_TABLE:
            self.chart.show_pairs([], [], "The HMS project's table, read when the job is written")
            self.factor.setText("")
            return
        if table is None:
            self.chart.show_pairs([], [], "")
            self.factor.setText("Choose a curve: Data tables holds them." if not self.curves else "")
            return
        mark = (at, factor_at(table, at)) if at > 0.0 else None
        self.chart.show_pairs(
            table["areas_km2"], table["factors"], name, mark=mark, log_x=True, from_zero=False,
            x_label="Storm area, km2", y_label="Factor",
        )  # fmt: skip
        self.factor.setText(f"Factor at {at:g} km2: {mark[1]:.4f}" if mark else "")

    def value(self) -> dict:
        form = self.form.currentData() or NONE
        return part(
            form, self.curve.currentData() or "", self.area.value(), self.coefficient.value(), self.single.value()
        )


class AreaReductionSection(Section):
    heading = "4b. Area reduction"
    start_collapsed = True
    key = "reduction"
    state_hold = ("lumped.curve", "grid.curve")
    """A curve of Data tables, which may be restored after this section: the saved name waits in the empty list."""
    study_areas_requested = pyqtSignal()

    def build(self) -> None:
        self._kind: str | None = None
        self._source: str | None = None
        self._hms = False
        self.source_note = _words()
        self.lumped = PartBox(LUMPED)
        self.grid = PartBox(GRID)
        self.by_element = QCheckBox(BY_ELEMENT)
        self.study_label = _words()
        self.form.addRow(self.source_note)
        self.form.addRow(self.lumped)
        self.form.addRow(self.grid)
        self.form.addRow(self.study_label)
        self.form.addRow(self.by_element)
        self.grid.study_wanted.connect(self.study_areas_requested.emit)
        self.grid.form.currentIndexChanged.connect(self._study_shown)
        self._shown()

    def set_curves(self, curves: dict) -> None:
        for box in (self.lumped, self.grid):
            box.set_curves(curves, self._hms)

    def set_hms(self, in_use: bool) -> None:
        self._hms = in_use
        self.set_curves(self.lumped.curves)
        self._shown()

    def set_source(self, source: str | None) -> None:
        """The Storm section's rain source: observed rain takes no reduction, the HMS storm its own."""
        self._source = source
        self._shown()

    def set_model_type(self, kind: str | None) -> None:
        self._kind = kind
        self._shown()

    def _shown(self) -> None:
        hms = self._source == KIND_HMS
        reduced = self._source in REDUCED_KINDS
        self.lumped.setVisible(not hms and self._kind != TWO_D)
        self.grid.setVisible(not hms and self._kind != LUMPED_TYPE)
        for box in (self.lumped, self.grid):
            box.setEnabled(reduced)
        self.by_element.setVisible(hms and self._kind in (None, LUMPED_TYPE))
        if hms:
            self.source_note.setText(HMS_SOURCE)
        elif not reduced and self._source is not None:
            self.source_note.setText(f"{UNUSED_WORDS}.")
        else:
            self.source_note.setText("")
        self.source_note.setVisible(bool(self.source_note.text()))
        self._study_shown()

    def _study_shown(self, *_) -> None:
        grid_shown = self._source != KIND_HMS and self._kind != LUMPED_TYPE
        self.study_label.setVisible(grid_shown and self.grid.form.currentData() == STUDY)

    def show_study_areas(self, text: str) -> None:
        self.study_label.setText(text)

    def reduction(self) -> dict:
        """Both parts, as the job builder takes them: a part the model type has no use for is absent."""
        return {
            LUMPED: self.lumped.value(),
            GRID: self.grid.value(),
            f"{LUMPED}_absent": self._kind == TWO_D,
            f"{GRID}_absent": self._kind == LUMPED_TYPE,
        }

    def standing(self, kind=None):
        return section_status.reduction(self._source, self.reduction(), self.lumped.curves, self._hms)

    def values(self, crs) -> dict:
        """``arf_by_element`` is HMS's depth-area way on the HMS storm; on the dock's own rain the lumped part's curve
        is the same rule (W95), so the tick of Hydrology that held it before W101 lives here, for the HMS storm alone."""
        return {
            "reduction": self.reduction(),
            "arf_by_element": self._source == KIND_HMS and self.by_element.isChecked(),
        }
