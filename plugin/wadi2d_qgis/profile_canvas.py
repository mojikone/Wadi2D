# Wadi2D QGIS plugin. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""The long profile you can take hold of: the ground from the DEM, and each series with its points.

Drag a point. Shift holds its station. Double-click adds a point to the nearest series, right-click deletes one. The
wheel zooms along the line, Ctrl and the wheel zoom the levels, the middle button pans. The ranges do not move while a
point is held, so it stays under the mouse.
"""

from __future__ import annotations

import math

from qgis.PyQt.QtCore import QPointF, QRectF, Qt, pyqtSignal
from qgis.PyQt.QtGui import QColor, QPainter, QPen, QPolygonF
from qgis.PyQt.QtWidgets import QMenu, QWidget

from .profile_table import BED, CREST, LEFT, RIGHT, interp
from .profile_view import AXIS_COLOUR, SERIES, bounds, scale_points

COLOURS = {key: colour for key, colour, _label in SERIES}
SERIES_COLOURS = {BED: COLOURS["bed"], LEFT: COLOURS["left_top"], RIGHT: COLOURS["right_top"], CREST: COLOURS["left_top"]}
GROUND = COLOURS["ground"]
GRID = "#e6e6e6"
HELD = "#000000"

MARGIN_LEFT, MARGIN_RIGHT, MARGIN_TOP, MARGIN_BOTTOM = 58.0, 16.0, 26.0, 30.0
HANDLE = 4.0
"""Half a point's square, px."""
REACH = 9.0
"""A press this close to a point takes it, px."""
PAD = 0.06
"""Room around the levels, as a share of their range."""
PAD_ALONG = 0.012
"""Room past each end of the line, so the end points stand clear of the frame and can be taken."""
SMALLEST_SPAN = 0.5
"""The narrowest range of levels the fit shows, m: a flat line would otherwise fill the plot with nothing."""
TICKS = 7
ZOOM = 1.25
MIN_X_SPAN = 1.0
MIN_Y_SPAN = 0.05
STATION_STEP = 0.1
LEVEL_STEP = 0.01
"""A drag lands on these, m, so the table stays readable."""
RULE_NOTCH = 5.0


def round_to(value: float, step: float) -> float:
    return round(round(value / step) * step, 6)


def tick_values(low: float, high: float, count: int = TICKS) -> list[float]:
    """Round numbers across a range."""
    span = high - low
    raw = span / max(count, 1)
    power = 10.0 ** math.floor(math.log10(raw))
    step = next((m * power for m in (1.0, 2.0, 5.0, 10.0) if m * power >= raw), 10.0 * power)
    first = math.ceil(low / step) * step + 0.0  # never -0
    values = []
    while first + len(values) * step <= high + 1e-9:
        values.append(first + len(values) * step)
    return values


class EditCanvas(QWidget):
    """Draws a :class:`ProfileModel`; every edit goes through it, between ``begin`` and ``end``."""

    edited = pyqtSignal()
    """An edit has finished: the table and the buttons catch up."""
    readout = pyqtSignal(str)
    """Words for the status line: where the mouse is, what the point holds."""
    activated = pyqtSignal(str)
    """The series in hand changed."""
    selected_point = pyqtSignal(float)
    """A point was taken: its station."""
    refused = pyqtSignal(str)

    def __init__(self) -> None:
        super().__init__()
        self.model = None
        self.ground: list = []
        self.vertices: list[float] = []
        self.active = ""
        self.selected: tuple[str, int] | None = None
        self.held: tuple[str, int] | None = None
        self.x_range = (0.0, 1.0)
        self.y_range = (0.0, 1.0)
        self._pan: tuple[QPointF, tuple, tuple] | None = None
        self.whole = True
        """The view is the whole line: nobody has zoomed or panned since the last fit."""
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMinimumSize(520, 320)

    def show_model(self, model, ground: list, vertices: list[float]) -> None:
        self.model, self.ground, self.vertices = model, ground, vertices
        self.active = model.keys[0]
        self.selected = self.held = None
        self.fit()

    def _levels(self) -> list[float]:
        found = [z for _s, z in self.ground]
        for points in self.model.points.values():
            found.extend(z for _s, z in points)
        return found

    def fit(self) -> None:
        """Everything in view."""
        if self.model is None:
            return
        limit = self.model.limit or 1.0
        self.x_range = (-PAD_ALONG * limit, (1.0 + PAD_ALONG) * limit)
        levels = self._levels()
        low, high = bounds([levels]) if levels else (0.0, 1.0)
        spare = max(high - low, SMALLEST_SPAN) * PAD
        middle = max(high - low, SMALLEST_SPAN) / 2.0 + spare
        centre = 0.5 * (low + high)
        self.y_range = (centre - middle, centre + middle)
        self.whole = True
        self.update()

    def keep_in_view(self) -> None:
        """A typed level can land outside the frame, as a drag cannot. A view zoomed on purpose stays as it is."""
        if self.whole and any(
            not self.y_range[0] <= z <= self.y_range[1] for found in self.model.points.values() for _s, z in found
        ):
            self.fit()

    # Pixels and data.

    def _box(self) -> QRectF:
        wide = self.width() - MARGIN_LEFT - MARGIN_RIGHT
        return QRectF(MARGIN_LEFT, MARGIN_TOP, wide, self.height() - MARGIN_TOP - MARGIN_BOTTOM)

    def to_pixel(self, s: float, z: float) -> QPointF:
        return scale_points([s], [z], self._box(), self.x_range, self.y_range)[0]

    def to_data(self, point: QPointF) -> tuple[float, float]:
        box = self._box()
        x0, x1 = self.x_range
        y0, y1 = self.y_range
        return (
            x0 + (point.x() - box.left()) / box.width() * (x1 - x0),
            y0 + (box.bottom() - point.y()) / box.height() * (y1 - y0),
        )

    def hit(self, point: QPointF) -> tuple[str, int] | None:
        """The point under the mouse; the series in hand first, as two tops often lie together."""
        best, reach = None, REACH
        for key in sorted(self.model.keys, key=lambda name: name != self.active):
            for index, (s, z) in enumerate(self.model.points[key]):
                at = self.to_pixel(s, z)
                gap = math.hypot(at.x() - point.x(), at.y() - point.y())
                if gap < reach:
                    best, reach = (key, index), gap
        return best

    def nearest_series(self, point: QPointF) -> str:
        """The series whose line passes closest above or below the mouse."""
        s, _z = self.to_data(point)
        found = [(key, self.model.level(key, s)) for key in self.model.keys]
        known = [(abs(self.to_pixel(s, z).y() - point.y()), key != self.active, key) for key, z in found if z is not None]
        return min(known)[2] if known else self.active

    # The mouse.

    def mousePressEvent(self, event) -> None:
        if self.model is None:
            return
        self.setFocus()
        point = QPointF(event.pos())
        if event.button() == Qt.MiddleButton:
            self._pan = (point, self.x_range, self.y_range)
            return
        found = self.hit(point)
        if event.button() == Qt.RightButton:
            self._menu(event, found)
            return
        if event.button() != Qt.LeftButton:
            return
        self.selected = found
        if found is None:
            self.update()
            return
        self.take(found[0])
        self.selected_point.emit(self.model.points[found[0]][found[1]][0])
        self.model.begin()
        self.held = found
        self._say_point(found)
        self.update()

    def mouseMoveEvent(self, event) -> None:
        if self.model is None:
            return
        point = QPointF(event.pos())
        if self._pan is not None:
            self._panned(point)
        elif self.held is not None:
            self._dragged(point, event.modifiers())
        else:
            self._hover(point)

    def mouseReleaseEvent(self, _event) -> None:
        self._pan = None
        if self.held is None:
            return
        self.held = None
        self.model.end()
        self.update()
        self.edited.emit()

    def mouseDoubleClickEvent(self, event) -> None:
        if self.model is None or event.button() != Qt.LeftButton or self.hit(QPointF(event.pos())) is not None:
            return
        self.add_at(QPointF(event.pos()))

    def wheelEvent(self, event) -> None:
        if self.model is None:
            return
        factor = 1.0 / ZOOM if event.angleDelta().y() > 0 else ZOOM
        s, z = self.to_data(event.position())
        self.whole = False
        if event.modifiers() & Qt.ControlModifier:
            self.y_range = self._zoomed(self.y_range, z, factor, MIN_Y_SPAN)
        else:
            self.x_range = self._zoomed(self.x_range, s, factor, MIN_X_SPAN)
        self.update()

    def keyPressEvent(self, event) -> None:
        if event.key() in (Qt.Key_Delete, Qt.Key_Backspace) and self.selected is not None:
            self.delete(self.selected)
            return
        super().keyPressEvent(event)

    def _zoomed(self, span: tuple[float, float], about: float, factor: float, smallest: float) -> tuple[float, float]:
        low, high = span
        width = max((high - low) * factor, smallest)
        share = (about - low) / (high - low)
        return about - share * width, about + (1.0 - share) * width

    def _panned(self, point: QPointF) -> None:
        start, x_range, y_range = self._pan
        self.whole = False
        box = self._box()
        along = (point.x() - start.x()) / box.width() * (x_range[1] - x_range[0])
        up = (point.y() - start.y()) / box.height() * (y_range[1] - y_range[0])
        self.x_range = (x_range[0] - along, x_range[1] - along)
        self.y_range = (y_range[0] + up, y_range[1] + up)
        self.update()

    def _dragged(self, point: QPointF, modifiers) -> None:
        key, index = self.held
        s, z = self.to_data(point)
        if modifiers & Qt.ShiftModifier:
            s = self.model.points[key][index][0]
        self.model.drag(key, index, round_to(s, STATION_STEP), round_to(z, LEVEL_STEP))
        self._say_point(self.held)
        self.update()

    def _hover(self, point: QPointF) -> None:
        found = self.hit(point)
        self.setCursor(Qt.SizeAllCursor if found else Qt.CrossCursor)
        if found:
            self._say_point(found)
            return
        s, _z = self.to_data(point)
        if 0.0 <= s <= self.model.limit:
            self.readout.emit(self._at_station(s))

    def _at_station(self, s: float) -> str:
        words = [f"Station {s:,.1f} m"]
        for key in self.model.keys:
            level = self.model.level(key, s)
            if level is not None:
                words.append(f"{self.model.labels[key]} {level:.2f}")
        if self.ground:
            words.append(f"ground {interp(self.ground, s):.2f}")
        return ", ".join(words)

    def _say_point(self, found: tuple[str, int]) -> None:
        key, index = found
        s, z = self.model.points[key][index]
        self.readout.emit(f"{self.model.labels[key].capitalize()} at station {s:,.1f} m: {z:.2f} m")

    def _menu(self, event, found) -> None:
        menu = QMenu(self)
        if found is not None:
            menu.addAction("Delete this point", lambda: self.delete(found))
        else:
            point = QPointF(event.pos())
            menu.addAction("Add a point here", lambda: self.add_at(point))
        menu.addAction("Show the whole line", self.fit)
        menu.exec_(event.globalPos())

    # Edits.

    def take(self, key: str) -> None:
        """Make this the series in hand."""
        if key != self.active:
            self.active = key
            self.activated.emit(key)
        self.update()

    def add_at(self, point: QPointF) -> None:
        key = self.nearest_series(point)
        s, z = self.to_data(point)
        self.model.begin()
        index = self.model.add(key, round_to(s, STATION_STEP), round_to(z, LEVEL_STEP))
        self.model.end()
        self.selected = (key, index)
        self.take(key)
        self.edited.emit()

    def delete(self, found: tuple[str, int]) -> None:
        self.model.begin()
        words = self.model.remove(*found)
        self.model.end()
        self.selected = None
        self.update()
        if words:
            self.refused.emit(words)
        else:
            self.edited.emit()

    # The drawing.

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("white"))
        if self.model is None:
            return
        painter.setRenderHint(QPainter.Antialiasing)
        box = self._box()
        self._grid(painter, box)
        painter.save()
        painter.setClipRect(box)
        self._ground(painter)
        for key in sorted(self.model.keys, key=lambda name: name == self.active):
            self._series(painter, key)
        painter.restore()
        painter.setPen(QPen(QColor(AXIS_COLOUR), 1.0))
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(box)
        self._legend(painter, box)
        painter.end()

    def _grid(self, painter, box: QRectF) -> None:
        painter.setFont(self.font())
        for s in tick_values(*self.x_range):
            x = self.to_pixel(s, self.y_range[0]).x()
            painter.setPen(QPen(QColor(GRID), 1.0))
            painter.drawLine(QPointF(x, box.top()), QPointF(x, box.bottom()))
            painter.setPen(QPen(QColor(AXIS_COLOUR), 1.0))
            painter.drawText(QPointF(x - 14.0, box.bottom() + 15.0), f"{s:,.0f}")
        for z in tick_values(*self.y_range):
            y = self.to_pixel(self.x_range[0], z).y()
            painter.setPen(QPen(QColor(GRID), 1.0))
            painter.drawLine(QPointF(box.left(), y), QPointF(box.right(), y))
            painter.setPen(QPen(QColor(AXIS_COLOUR), 1.0))
            painter.drawText(QPointF(4.0, y + 4.0), f"{z:.2f}")
        painter.drawText(QPointF(box.right() - 110.0, box.bottom() + 27.0), "station, m")
        painter.setPen(QPen(QColor(AXIS_COLOUR), 1.0))
        for s in self.vertices:  # where the line turns: a notch on the top edge
            x = self.to_pixel(s, self.y_range[0]).x()
            painter.drawLine(QPointF(x, box.top()), QPointF(x, box.top() + RULE_NOTCH))

    def _ground(self, painter) -> None:
        if not self.ground:
            return
        points = [self.to_pixel(s, z) for s, z in self.ground]
        painter.setPen(QPen(QColor(GROUND), 1.6))
        painter.drawPolyline(QPolygonF(points))

    def _series(self, painter, key: str) -> None:
        points = self.model.points[key]
        if not points:
            return
        colour = QColor(SERIES_COLOURS[key])
        pixels = [self.to_pixel(s, z) for s, z in points]
        hold = QPen(colour, 1.0, Qt.DashLine)
        painter.setPen(hold)  # past its last point a series holds its level, as the engine reads it
        painter.drawLine(self.to_pixel(0.0, points[0][1]), pixels[0])
        painter.drawLine(pixels[-1], self.to_pixel(self.model.limit, points[-1][1]))
        painter.setPen(QPen(colour, 2.4 if key == self.active else 1.6))
        painter.drawPolyline(QPolygonF(pixels))
        size = HANDLE + (1.0 if key == self.active else 0.0)
        for index, pixel in enumerate(pixels):
            chosen = self.selected == (key, index)
            painter.setPen(QPen(QColor(HELD) if chosen else colour, 1.5))
            painter.setBrush(QColor("white") if chosen else colour)
            painter.drawRect(QRectF(pixel.x() - size, pixel.y() - size, 2.0 * size, 2.0 * size))

    def _legend(self, painter, box: QRectF) -> None:
        """Right-aligned above the box; the series in hand in bold."""
        x = box.right()
        entries = [(self.model.labels[key], SERIES_COLOURS[key], key == self.active) for key in self.model.keys]
        for label, colour, bold in reversed([("ground", GROUND, False), *entries]):
            font = painter.font()
            font.setBold(bold)
            painter.setFont(font)
            x -= painter.fontMetrics().horizontalAdvance(label) + 14.0
            painter.setPen(QPen(QColor(colour), 1.6))
            painter.drawText(QPointF(x, box.top() - 8.0), label)
        font = painter.font()
        font.setBold(False)
        painter.setFont(font)
