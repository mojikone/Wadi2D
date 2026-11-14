# Wadi2D QGIS plugin. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""7b. Gauges: flow and level gauges to check the run against, as in HEC-HMS.

A flow gauge names a result line or a lumped element, a level gauge a result point; each row's record is a CSV table or
a DSS file. They are compared after every run and drawn in Result lines. Rain gauges live in the Storm section's Rain
gauges page since W77 (his word of 2026-11-14: one place for rain); the dock joins the two tables into the one W54
wrote (``gauge_rows.joined_gauges``).
"""

from __future__ import annotations

from qgis.PyQt.QtWidgets import QLabel, QLineEdit

from ..gauge_rows import FLOW, LEVEL, RAIN
from .common import Section
from .gauge_table import GaugeTable

NOTE = (
    "Flow and level gauges are drawn beside the run's own series in Result lines, with their agreement. A CSV has the "
    "time first, as minutes from the run's start or as dates, then the values. Rain gauges are set in the Storm "
    "section, Rain source: Rain gauges."
)
AT_TIP = (
    "A flow gauge: the name of a result line or a lumped element. A level gauge: the name of a result point."
)


class GaugesSection(Section):
    heading = "7b. Gauges (optional)"
    start_collapsed = True

    def build(self) -> None:
        self.note = QLabel(NOTE)
        self.note.setWordWrap(True)
        self.gauges = GaugeTable((FLOW, LEVEL), "Line, point or element", AT_TIP)
        self.table, self.add_buttons, self.remove_button = (
            self.gauges.table,
            self.gauges.add_buttons,
            self.gauges.remove_button,
        )
        self.start = QLineEdit()
        self.start.setPlaceholderText("As the rain gauges' start, in the Storm section")
        self.start.setToolTip(
            "Date and time the run starts at, as 2021-10-04 00:00, for records written with dates; left empty, the "
            "start of the rain gauges' storm"
        )
        self.form.addRow(self.note)
        self.form.addRow(self.gauges)
        self.form.addRow("Run starts at", self.start)

    @property
    def rows(self):
        return self.gauges.rows

    def add_row(self, kind: str):
        return self.gauges.add_row(kind)

    def set_row(self, index: int, **fields) -> None:
        self.gauges.set_row(index, **fields)

    def values(self, crs) -> dict:
        return {
            "observed_gauges": {"rows": self.gauges.current_rows(crs), "start": self.start.text().strip()}
        }


__all__ = ["FLOW", "LEVEL", "RAIN", "GaugesSection"]
