# Wadi2D QGIS plugin. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""The long profile and the cross-sections of a preview, drawn from the data the engine wrote.

The long profile is ground, bed and both tops along the stations, with a band under it saying what each bank is at
each station. Below it the cross-section at the chosen station: old ground against new.
"""

from __future__ import annotations

from qgis.PyQt.QtCore import QPointF, QRectF, Qt
from qgis.PyQt.QtGui import QColor, QPainter, QPen, QPolygonF
from qgis.PyQt.QtWidgets import QComboBox, QDialog, QHBoxLayout, QLabel, QSlider, QVBoxLayout, QWidget

MARGIN = 44.0
TITLE_RISE = 6.0
LEGEND_GAP = 14.0
BAND = 8.0
GAP = 26.0
LONG_SHARE = 0.5
SERIES = (  # key, colour, label
    ("ground", "#8a6d3b", "ground"),
    ("new", "#222222", "new ground"),
    ("bed", "#1a5f9a", "bed"),
    ("left_top", "#c0392b", "left top"),
    ("right_top", "#e08e0b", "right top"),
)
SECTION_SERIES = (("ground", "#8a6d3b", "old ground"), ("new", "#222222", "new ground"))
STATE_COLOURS = {"dyke": "#c0392b", "cut": "#2e8b57", "open": "#ffffff", "none": "#dddddd"}
AXIS_COLOUR = "#666666"
SIZE = (820, 620)


def bounds(rows: list[list[float]]) -> tuple[float, float]:
    """Lowest and highest value, never equal."""
    values = [value for row in rows for value in row]
    low, high = min(values), max(values)
    return (low, high) if high > low else (low - 1.0, low + 1.0)


def scale_points(xs: list[float], ys: list[float], box: QRectF, x_range, y_range) -> list[QPointF]:
    """Data to pixels inside ``box``; y runs up."""
    x0, x1 = x_range
    y0, y1 = y_range
    return [
        QPointF(
            box.left() + (x - x0) / (x1 - x0) * box.width(),
            box.bottom() - (y - y0) / (y1 - y0) * box.height(),
        )
        for x, y in zip(xs, ys, strict=True)
    ]


class ProfileCanvas(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.item: dict | None = None
        self.index = 0
        self.setMinimumSize(*SIZE)

    def show_item(self, item: dict, index: int) -> None:
        self.item, self.index = item, index
        self.update()

    def paintEvent(self, _event) -> None:
        if self.item is None:
            return
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("white"))
        painter.setRenderHint(QPainter.Antialiasing)
        wide = self.width() - 2.0 * MARGIN
        high = self.height() - 2.0 * MARGIN - GAP - BAND
        top = QRectF(MARGIN, MARGIN, wide, high * LONG_SHARE)
        band = QRectF(MARGIN, top.bottom() + 2.0, wide, BAND)
        low = QRectF(MARGIN, band.bottom() + GAP, wide, high * (1.0 - LONG_SHARE))
        self._long(painter, top, band)
        self._section(painter, low)
        painter.end()

    def _axes(self, painter, box: QRectF, x_range, y_range, title: str, unit: str) -> None:
        painter.setPen(QPen(QColor(AXIS_COLOUR), 1.0))
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(box)
        painter.drawText(QPointF(box.left(), box.top() - TITLE_RISE), title)
        painter.drawText(QPointF(box.left() - 40.0, box.top() + 12.0), f"{y_range[1]:.1f}")
        painter.drawText(QPointF(box.left() - 40.0, box.bottom()), f"{y_range[0]:.1f}")
        painter.drawText(QPointF(box.left(), box.bottom() + 14.0), f"{x_range[0]:.0f} {unit}")
        painter.drawText(QPointF(box.right() - 54.0, box.bottom() + 14.0), f"{x_range[1]:.0f} {unit}")

    def _lines(self, painter, series, data: dict, xs, box, x_range, y_range) -> None:
        """The lines, with a legend right-aligned above the box, clear of the title on the left."""
        shown = [entry for entry in series if entry[0] in data]
        metrics = painter.fontMetrics()
        x = box.right()
        for key, colour, label in reversed(shown):
            painter.setPen(QPen(QColor(colour), 1.6))
            painter.drawPolyline(QPolygonF(scale_points(xs, data[key], box, x_range, y_range)))
            x -= metrics.horizontalAdvance(label) + LEGEND_GAP
            painter.drawText(QPointF(x, box.top() - TITLE_RISE), label)

    def _long(self, painter, box: QRectF, band: QRectF) -> None:
        item = self.item
        xs = item["station"]
        x_range = (xs[0], xs[-1]) if xs[-1] > xs[0] else (xs[0], xs[0] + 1.0)
        keys = [key for key, _colour, _label in SERIES if key in item]
        y_range = bounds([item[key] for key in keys])
        self._axes(painter, box, x_range, y_range, f"{item['name']}: long profile", "m")
        self._lines(painter, SERIES, item, xs, box, x_range, y_range)
        section = item["sections"][self.index]
        at = scale_points([section["station"]], [y_range[0]], box, x_range, y_range)[0].x()
        painter.setPen(QPen(QColor(AXIS_COLOUR), 1.0, Qt.DashLine))
        painter.drawLine(QPointF(at, box.top()), QPointF(at, box.bottom()))
        self._states(painter, band, item, x_range)

    def _states(self, painter, band: QRectF, item: dict, x_range) -> None:
        """Left bank over right bank: red a dyke, green a cut, white an opening."""
        xs = item["station"]
        painter.setPen(Qt.NoPen)
        rows = ((item["left_state"], band.top()), (item["right_state"], band.top() + 0.5 * band.height()))
        span = x_range[1] - x_range[0]
        for states, y in rows:
            for n in range(len(xs) - 1):
                x0 = band.left() + (xs[n] - x_range[0]) / span * band.width()
                x1 = band.left() + (xs[n + 1] - x_range[0]) / span * band.width()
                painter.setBrush(QColor(STATE_COLOURS.get(states[n], AXIS_COLOUR)))
                painter.drawRect(QRectF(x0, y, x1 - x0 + 0.5, 0.5 * band.height()))

    def _section(self, painter, box: QRectF) -> None:
        section = self.item["sections"][self.index]
        xs = section["offset"]
        x_range = (xs[0], xs[-1])
        y_range = bounds([section["ground"], section["new"]])
        title = f"Section at station {section['station']:.0f}: offset, m, left to right"
        self._axes(painter, box, x_range, y_range, title, "")
        self._lines(painter, SECTION_SERIES, section, xs, box, x_range, y_range)


class ProfileDialog(QDialog):
    """One object at a time, a slider along its sections."""

    def __init__(self, data: list[dict], parent=None) -> None:
        super().__init__(parent)
        self.data = data
        self.setWindowTitle("Wadi2D: sections and long profile")
        self.objects = QComboBox()
        self.objects.addItems([item["name"] for item in data])
        self.slider = QSlider(Qt.Horizontal)
        self.station = QLabel()
        self.canvas = ProfileCanvas()
        row = QHBoxLayout()
        row.addWidget(self.objects)
        row.addWidget(self.slider, 1)
        row.addWidget(self.station)
        column = QVBoxLayout(self)
        column.addLayout(row)
        column.addWidget(self.canvas, 1)
        self.objects.currentIndexChanged.connect(self._object_changed)
        self.slider.valueChanged.connect(self._section_changed)
        self._object_changed(0)

    def _object_changed(self, index: int) -> None:
        self.slider.setRange(0, len(self.data[index]["sections"]) - 1)
        self.slider.setValue(0)
        self._section_changed(0)

    def _section_changed(self, index: int) -> None:
        item = self.data[self.objects.currentIndex()]
        self.station.setText(f"Station {item['sections'][index]['station']:,.0f} m")
        self.canvas.show_item(item, index)
