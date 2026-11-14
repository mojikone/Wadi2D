# Wadi2D QGIS plugin. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""The preview of the rain: a table of each lumped subbasin and the 2D area, and a small hyetograph of the row picked.

The numbers are the engine's (``wadi2d rain-preview``); this side only shows them.
"""

from __future__ import annotations

from qgis.PyQt.QtCore import QRectF, Qt
from qgis.PyQt.QtGui import QColor, QPainter
from qgis.PyQt.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QWidget,
)

COLUMNS = ("Rain falls on", "Taken as", "Area, km2", "Depth, mm", "Peak, mm/h")
MODE_WORDS = {"lumped": "Lumped", "2d": "2D cells"}
CHART_HIGH = 120
MARGIN = 6.0
TEXT_HIGH = 14.0
BAR_COLOUR, AXIS_COLOUR, TEXT_COLOUR = "#1a5f9a", "#666666", "#222222"
TABLE_ROWS = 6


class HyetographChart(QWidget):
    """Bars of depth per step, with the total and the peak written over them."""

    def __init__(self) -> None:
        super().__init__()
        self.setMinimumHeight(CHART_HIGH)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.row: dict | None = None

    def show_row(self, row: dict | None) -> None:
        self.row = row
        self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        box = QRectF(self.rect()).adjusted(MARGIN, MARGIN + TEXT_HIGH, -MARGIN, -MARGIN)
        painter.setPen(QColor(AXIS_COLOUR))
        painter.drawLine(box.bottomLeft(), box.bottomRight())
        row = self.row
        if not row or not row["mm"]:
            painter.setPen(QColor(TEXT_COLOUR))
            painter.drawText(QRectF(self.rect()), Qt.AlignCenter, "No rain" if row else "")
            return
        values, step = row["mm"], row["minutes"][0]
        top = max(values) or 1.0
        width = box.width() / len(values)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(BAR_COLOUR))
        for n, value in enumerate(values):
            high = box.height() * value / top
            painter.drawRect(QRectF(box.left() + n * width, box.bottom() - high, max(width - 0.5, 0.5), high))
        painter.setPen(QColor(TEXT_COLOUR))
        hours = row["minutes"][-1] / 60.0
        words = (
            f"{row['name']}: {row['depth_mm']:.1f} mm in {hours:g} h, at most {max(values):.2f} mm "
            f"in {step:g} min ({row['peak_mm_h']:.1f} mm/h)"
        )
        painter.drawText(QRectF(MARGIN, 0.0, self.width() - 2 * MARGIN, TEXT_HIGH + MARGIN), Qt.AlignLeft, words)


class PreviewTable(QTableWidget):
    def __init__(self) -> None:
        super().__init__(0, len(COLUMNS))
        self.setHorizontalHeaderLabels(COLUMNS)
        self.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.verticalHeader().hide()
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setMinimumHeight(self.fontMetrics().height() * TABLE_ROWS)
        self.rows: list[dict] = []

    def show_rows(self, rows: list[dict]) -> None:
        self.rows = rows
        self.setRowCount(len(rows))
        for n, row in enumerate(rows):
            cells = (
                row["name"], MODE_WORDS.get(row["mode"], row["mode"]), f"{row['area_km2']:.3f}",
                f"{row['depth_mm']:.1f}", f"{row['peak_mm_h']:.1f}",
            )  # fmt: skip
            for m, text in enumerate(cells):
                item = QTableWidgetItem(text)
                if m >= 2:
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.setItem(n, m, item)
        if rows:
            self.selectRow(0)
