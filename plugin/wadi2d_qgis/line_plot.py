# Wadi2D QGIS plugin. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""The result-line plot: hydrograph, depth, and the water surface with the terrain, with a cursor on the current frame.

Everything is on the widget already, so moving the time slider costs a repaint and no call to the engine.
"""

from __future__ import annotations

from qgis.PyQt.QtCore import QPointF, QRectF, Qt
from qgis.PyQt.QtGui import QColor, QPainter, QPen, QPolygonF
from qgis.PyQt.QtWidgets import QSizePolicy, QWidget

from .line_view import SECONDS_PER_HOUR, Chart, Curve, Section, View, readout, ticks
from .profile_view import bounds, scale_points

SIZE = (900, 290)
LEFT, RIGHT, GAP, GAP_HIGH = 56.0, 28.0, 70.0, 52.0
HEADER, FOOTER, AXIS = 60.0, 48.0, 18.0
TITLE_RISE, LEGEND_STEP, LEGEND_BAR, TICK = 5.0, 14.0, 16.0, 4.0
WIDE_RATIO = 2.0
"""Wider than this over its height, the panels stand side by side."""
HEADROOM = 1.05
LINE_WIDTH, CURSOR_WIDTH, DOT = 1.6, 1.0, 2.2
AXIS_COLOUR, GRID_COLOUR, TEXT_COLOUR, CURSOR_COLOUR = "#666666", "#e4e4e4", "#222222", "#aa0000"
GROUND_FILL, GROUND_LINE, WATER_FILL, WATER_LINE = "#d9c9a8", "#8a6d3b", "#9cc9ec", "#1a5f9a"
MIN_SPAN = 1e-6
MARGIN, UNIT_GAP, LEGEND_CLEAR = 14.0, 13.0, 6.0


def _range(low: float, high: float) -> tuple[float, float]:
    return (low, high) if high > low else (low, low + 1.0)


def _runs(values: list) -> list[tuple[int, int]]:
    """Stretches without a gap, as (first, one past the last)."""
    found, start = [], None
    for index, value in enumerate(values):
        if value is None and start is not None:
            found.append((start, index))
            start = None
        elif value is not None and start is None:
            start = index
    if start is not None:
        found.append((start, len(values)))
    return found


class LinePlot(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.view: View | None = None
        self.frame = 0
        self.setMinimumSize(*SIZE)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def show_view(self, view: View | None, frame: int = 0) -> None:
        self.view, self.frame = view, frame
        self.update()

    def set_frame(self, frame: int) -> None:
        self.frame = frame
        self.update()

    def _boxes(self, count: int) -> list[QRectF]:
        """One box per panel: side by side on a wide widget, one under the other on a tall one."""
        wide = self.width() - LEFT - RIGHT
        high = self.height() - HEADER - FOOTER - AXIS
        if self.width() >= WIDE_RATIO * self.height():
            each = (wide - GAP * (count - 1)) / count
            return [QRectF(LEFT + n * (each + GAP), HEADER, each, high) for n in range(count)]
        each = (high - GAP_HIGH * (count - 1)) / count
        return [QRectF(LEFT, HEADER + n * (each + GAP_HIGH), wide, each) for n in range(count)]

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("white"))
        if self.view is None:
            painter.end()
            return
        painter.setRenderHint(QPainter.Antialiasing)
        view = self.view
        self._words(painter, view)
        panels = len(view.charts) + (1 if view.section else 0)
        boxes = self._boxes(panels)
        for box, chart in zip(boxes, view.charts, strict=False):
            self._chart(painter, box, chart)
        if view.section:
            self._section(painter, boxes[-1], view.section)
        painter.end()

    def _words(self, painter, view: View) -> None:
        wide = self.width() - 2.0 * MARGIN
        painter.setPen(QPen(QColor(TEXT_COLOUR)))
        font = painter.font()
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(QRectF(MARGIN, 4.0, wide, 16.0), Qt.AlignLeft, view.heading)
        font.setBold(False)
        painter.setFont(font)
        painter.drawText(QRectF(MARGIN, 20.0, wide, 16.0), Qt.AlignLeft, readout(view, self.frame))
        painter.setPen(QPen(QColor(AXIS_COLOUR)))
        bottom = QRectF(MARGIN, self.height() - FOOTER, wide, FOOTER)
        painter.drawText(bottom, int(Qt.AlignLeft | Qt.AlignBottom) | int(Qt.TextWordWrap), view.limit)

    def _frame_hours(self) -> float | None:
        frames = self.view.frames_s
        if not frames:
            return None
        return frames[min(self.frame, len(frames) - 1)] / SECONDS_PER_HOUR

    def _grid(self, painter, box: QRectF, x_range, y_range, title: str, x_unit: str) -> None:
        """Frame, title, round ticks on both axes and light lines at them."""
        metrics = painter.fontMetrics()
        for value in ticks(*y_range):
            y = scale_points([x_range[0]], [value], box, x_range, y_range)[0].y()
            painter.setPen(QPen(QColor(GRID_COLOUR), 1.0))
            painter.drawLine(QPointF(box.left(), y), QPointF(box.right(), y))
            painter.setPen(QPen(QColor(AXIS_COLOUR), 1.0))
            text = f"{value:g}"
            painter.drawText(QPointF(box.left() - metrics.horizontalAdvance(text) - TICK - 1.0, y + 4.0), text)
        for value in ticks(*x_range):
            x = scale_points([value], [y_range[0]], box, x_range, y_range)[0].x()
            painter.setPen(QPen(QColor(GRID_COLOUR), 1.0))
            painter.drawLine(QPointF(x, box.top()), QPointF(x, box.bottom()))
            painter.setPen(QPen(QColor(AXIS_COLOUR), 1.0))
            text = f"{value:g}"
            painter.drawText(QPointF(x - metrics.horizontalAdvance(text) / 2.0, box.bottom() + 14.0), text)
        painter.setPen(QPen(QColor(AXIS_COLOUR), 1.0))
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(box)
        painter.drawText(QPointF(box.right() + UNIT_GAP, box.bottom() + 14.0), x_unit)
        painter.setPen(QPen(QColor(TEXT_COLOUR)))
        painter.drawText(QPointF(box.left(), box.top() - TITLE_RISE), title)

    def _cursor(self, painter, box: QRectF, x_range, y_range) -> None:
        hours = self._frame_hours()
        if hours is None or x_range[1] - x_range[0] < MIN_SPAN:
            return
        x = scale_points([min(max(hours, x_range[0]), x_range[1])], [y_range[0]], box, x_range, y_range)[0].x()
        painter.setPen(QPen(QColor(CURSOR_COLOUR), CURSOR_WIDTH, Qt.DashLine))
        painter.drawLine(QPointF(x, box.top()), QPointF(x, box.bottom()))

    def _curve(self, painter, box: QRectF, curve: Curve, x_range, y_range) -> None:
        if len(curve.times_h) < 1:
            return
        points = scale_points(curve.times_h, curve.values, box, x_range, y_range)
        painter.setPen(QPen(QColor(curve.colour), LINE_WIDTH))
        painter.setBrush(Qt.NoBrush)
        painter.drawPolyline(QPolygonF(points))
        if curve.markers:
            painter.setBrush(QColor(curve.colour))
            for point in points:
                painter.drawEllipse(point, DOT, DOT)
            painter.setBrush(Qt.NoBrush)

    def _legend(self, painter, box: QRectF, curves: list[Curve]) -> None:
        """Inside the box, top left: which curve is which kind is the point of this plot."""
        metrics = painter.fontMetrics()
        y = box.top() + LEGEND_STEP
        for curve in curves:
            x = box.left() + 6.0
            room = QRectF(x - 2.0, y - 11.0, LEGEND_BAR + 8.0 + metrics.horizontalAdvance(curve.label), LEGEND_STEP)
            painter.fillRect(room, QColor(255, 255, 255, 215))
            painter.setPen(QPen(QColor(curve.colour), 2.0))
            painter.drawLine(QPointF(x, y - 4.0), QPointF(x + LEGEND_BAR, y - 4.0))
            painter.setPen(QPen(QColor(TEXT_COLOUR)))
            painter.drawText(QPointF(x + LEGEND_BAR + 4.0, y), curve.label)
            y += LEGEND_STEP

    def _chart(self, painter, box: QRectF, chart: Chart) -> None:
        drawn = [curve for curve in chart.curves if curve.times_h]
        if not drawn:
            self._grid(painter, box, (0.0, 1.0), (0.0, 1.0), chart.title, "h")
            return
        end = max(curve.times_h[-1] for curve in drawn)
        start = min(curve.times_h[0] for curve in drawn)
        x_range = _range(0.0 if start < end else start, end)
        low, high = bounds([curve.values for curve in drawn])
        y_range = (0.0, high) if chart.from_zero else (low, high)
        room = box.height() / max(box.height() - LEGEND_STEP * len(drawn) - LEGEND_CLEAR, 1.0)  # no curve under the legend
        y_range = _range(y_range[0], y_range[0] + (y_range[1] - y_range[0]) * room)
        self._grid(painter, box, x_range, y_range, chart.title, "h")
        painter.save()
        painter.setClipRect(box)
        for curve in drawn:
            self._curve(painter, box, curve, x_range, y_range)
        painter.restore()
        self._cursor(painter, box, x_range, y_range)
        self._legend(painter, box, drawn)

    def _section(self, painter, box: QRectF, section: Section) -> None:
        stations = section.station_m
        x_range = _range(stations[0], stations[-1])
        known = [value for value in section.ground_m if value is not None]
        water = [value for levels in section.level_m for value in levels if value is not None]
        low, high = bounds([known + water]) if known or water else (0.0, 1.0)
        y_range = _range(low, low + (high - low) * HEADROOM)
        self._grid(painter, box, x_range, y_range, section.title, "m")
        painter.save()
        painter.setClipRect(box)
        self._ground(painter, box, section, x_range, y_range)
        self._water(painter, box, section, x_range, y_range)
        painter.restore()

    def _ground(self, painter, box: QRectF, section: Section, x_range, y_range) -> None:
        stations, ground = section.station_m, section.ground_m
        for first, last in _runs(ground):
            xs, zs = stations[first:last], ground[first:last]
            line = scale_points(xs, zs, box, x_range, y_range)
            under = [QPointF(line[-1].x(), box.bottom()), QPointF(line[0].x(), box.bottom())]
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(GROUND_FILL))
            painter.drawPolygon(QPolygonF(line + under))
            painter.setPen(QPen(QColor(GROUND_LINE), 1.2))
            painter.setBrush(Qt.NoBrush)
            painter.drawPolyline(QPolygonF(line))

    def _water(self, painter, box: QRectF, section: Section, x_range, y_range) -> None:
        """Water stands between the ground and its level, one stretch at a time; one flat level per cell."""
        stations, ground = section.station_m, section.ground_m
        levels = section.level_m[min(self.frame, len(section.level_m) - 1)]
        for first, last in _runs(levels):
            xs, tops = stations[first:last], levels[first:last]
            floors = [z if z is not None else top for z, top in zip(ground[first:last], tops, strict=True)]
            top = scale_points(xs, tops, box, x_range, y_range)
            floor = scale_points(xs, floors, box, x_range, y_range)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(WATER_FILL))
            painter.drawPolygon(QPolygonF(top + floor[::-1]))
            painter.setPen(QPen(QColor(WATER_LINE), LINE_WIDTH))
            painter.setBrush(Qt.NoBrush)
            painter.drawPolyline(QPolygonF(top))
