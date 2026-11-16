# Wadi2D QGIS plugin. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""A small chart of one table of pairs (W101): a rain pattern, an area-reduction curve, an inflow hydrograph.

It draws what it is given, a line through the points with a dot on each, its two axes named, and an optional marker:
the factor read at a fixed storm area. No number is computed here that the table does not hold.
"""

from __future__ import annotations

import itertools
import math

from qgis.PyQt.QtCore import QPointF, QRectF, Qt
from qgis.PyQt.QtGui import QColor, QPainter, QPen
from qgis.PyQt.QtWidgets import QSizePolicy, QWidget

CHART_HIGH = 150
MARGIN, LEFT, BOTTOM, TOP = 6.0, 46.0, 30.0, 18.0
LINE_COLOUR, AXIS_COLOUR, TEXT_COLOUR, MARK_COLOUR = "#1a5f9a", "#666666", "#222222", "#c8560a"
DOT = 2.5


def _span(values: list[float]) -> tuple[float, float]:
    low, high = min(values), max(values)
    if high <= low:
        high = low + (abs(low) or 1.0)
    return low, high


class PairChart(QWidget):
    def __init__(self, x_label: str = "", y_label: str = "") -> None:
        super().__init__()
        self.setMinimumHeight(CHART_HIGH)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.x_label, self.y_label = x_label, y_label
        self.xs: list[float] = []
        self.ys: list[float] = []
        self.title = ""
        self.mark: tuple[float, float] | None = None
        self.log_x = False
        self.from_zero = True

    def show_pairs(
        self, xs, ys, title: str = "", mark=None, log_x: bool = False, x_label: str | None = None,
        y_label: str | None = None, from_zero: bool = True,
    ) -> None:  # fmt: skip
        pairs = [(float(x), float(y)) for x, y in zip(xs, ys, strict=False) if math.isfinite(x) and math.isfinite(y)]
        if log_x:
            pairs = [(x, y) for x, y in pairs if x > 0.0]
        self.xs, self.ys = [p[0] for p in pairs], [p[1] for p in pairs]
        self.title, self.mark, self.log_x, self.from_zero = title, mark, log_x, from_zero
        if x_label is not None:
            self.x_label = x_label
        if y_label is not None:
            self.y_label = y_label
        self.update()

    def _x(self, value: float) -> float:
        return math.log10(value) if self.log_x else value

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        box = QRectF(self.rect()).adjusted(LEFT, TOP, -MARGIN, -BOTTOM)
        painter.setPen(QColor(TEXT_COLOUR))
        painter.drawText(QRectF(MARGIN, 0.0, self.width() - 2 * MARGIN, TOP), Qt.AlignLeft | Qt.AlignVCenter, self.title)
        painter.setPen(QColor(AXIS_COLOUR))
        painter.drawLine(box.bottomLeft(), box.bottomRight())
        painter.drawLine(box.bottomLeft(), box.topLeft())
        if len(self.xs) < 1:
            painter.drawText(box, Qt.AlignCenter, "No rows yet")
            return
        x_low, x_high = _span([self._x(x) for x in self.xs])
        y_values = [*self.ys, *([self.mark[1]] if self.mark else [])]
        y_low, y_high = _span([*y_values, 0.0] if self.from_zero else y_values)

        def at(x: float, y: float) -> QPointF:
            fx = (self._x(x) - x_low) / (x_high - x_low)
            fy = (y - y_low) / (y_high - y_low)
            return QPointF(box.left() + fx * box.width(), box.bottom() - fy * box.height())

        painter.setPen(QColor(TEXT_COLOUR))
        for value, align, where in (
            (y_high, Qt.AlignRight | Qt.AlignTop, QRectF(0.0, box.top() - 2, LEFT - 4, 14)),
            (y_low, Qt.AlignRight | Qt.AlignBottom, QRectF(0.0, box.bottom() - 12, LEFT - 4, 14)),
        ):
            painter.drawText(where, align, f"{value:.4g}")
        low_x, high_x = (10**x_low, 10**x_high) if self.log_x else (x_low, x_high)
        painter.drawText(QRectF(box.left(), box.bottom() + 2, 80, 14), Qt.AlignLeft, f"{low_x:.4g}")
        painter.drawText(QRectF(box.right() - 80, box.bottom() + 2, 80, 14), Qt.AlignRight, f"{high_x:.4g}")
        axis = f"{self.x_label}{', log scale' if self.log_x else ''}"
        painter.drawText(QRectF(box.left(), box.bottom() + 14, box.width(), 14), Qt.AlignHCenter, axis)
        painter.save()
        painter.translate(10.0, box.center().y())
        painter.rotate(-90)
        painter.drawText(QRectF(-box.height() / 2, -8, box.height(), 14), Qt.AlignCenter, self.y_label)
        painter.restore()
        pen = QPen(QColor(LINE_COLOUR))
        pen.setWidthF(1.6)
        painter.setPen(pen)
        points = [at(x, y) for x, y in zip(self.xs, self.ys, strict=True)]
        for a, b in itertools.pairwise(points):
            painter.drawLine(a, b)
        painter.setBrush(QColor(LINE_COLOUR))
        for point in points:
            painter.drawEllipse(point, DOT, DOT)
        if self.mark is not None and (not self.log_x or self.mark[0] > 0.0):
            point = at(*self.mark)
            painter.setPen(QPen(QColor(MARK_COLOUR), 1.2, Qt.DashLine))
            painter.drawLine(QPointF(point.x(), box.bottom()), point)
            painter.drawLine(QPointF(box.left(), point.y()), point)
            painter.setBrush(QColor(MARK_COLOUR))
            painter.drawEllipse(point, DOT + 1, DOT + 1)
