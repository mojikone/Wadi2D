# Wadi2D QGIS plugin. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""The saved maps of a run on the Temporal Controller at the terrain pixel, drawn on demand as RAS Mapper draws them.

A raster layer whose data provider is this module's: for every drawing QGIS asks it for one band over the extent and
the size on screen, at the time on the controller, and it asks the run's drawing process
(:mod:`render_client`) for those numbers. Nothing is written per frame. Being a raster layer, it is coloured by the
same renderer as the depth of record (:func:`style.style_pixel_depth`), Identify reads it, its legend, styling and
temporal settings are QGIS's own, and QGIS redraws it on a pan, a zoom and every step of the controller.

Band 1 is depth, 2 speed, 3 the hazard class. Time is not interpolated: a drawing shows the last saved map at or before
the controller's time.

Every method QGIS calls from C++ catches what it raises: an exception there would end QGIS, not the drawing.
"""

from __future__ import annotations

import collections
import itertools
import statistics
from pathlib import Path

from qgis.core import (
    Qgis,
    QgsCoordinateReferenceSystem,
    QgsDataProvider,
    QgsDateTimeRange,
    QgsInterval,
    QgsMessageLog,
    QgsProject,
    QgsProviderMetadata,
    QgsProviderRegistry,
    QgsRasterBlock,
    QgsRasterDataProvider,
    QgsRasterIdentifyResult,
    QgsRasterLayer,
    QgsRectangle,
    QgsTemporalNavigationObject,
    QgsUnitTypes,
)
from qgis.PyQt.QtCore import QDate, QDateTime, QObject, Qt, QTime, QTimer, pyqtSignal
from qgis.PyQt.QtWidgets import QDockWidget

from . import render_client, settings, style
from .protocol import FRAMES_EPOCH, SLIDER_PROVIDER
from .time_layer import _add

LAYER_TITLE = "Flood over time, pixels"
LOG_TAG = "Wadi2D"
NODATA = -9999.0
BANDS = (("depth", "Depth, m"), ("speed", "Speed, m/s"), ("hazard", "Hazard class, 1 to 6 are H1 to H6"))
MS_PER_S = 1000.0
MORE_AFTER_MS = 150
"""A drawing made while ground was still being read asks for the finer one this much later."""
MORE_TIMES = 40
"""At most this many such asks in a row, so a read that never ends cannot keep QGIS drawing."""
_alive: dict[int, QgsRasterDataProvider] = {}
"""The providers and the copies made for QGIS's drawings. Python must hold them: one handed to C++ and let go here
stops answering, and QGIS then draws nothing (seen on 3.44.8). Each leaves when QGIS deletes it."""
_last_t: dict[str, float | None] = {}
"""The time of the last drawing of each run."""
recent: collections.deque = collections.deque(maxlen=20)
"""The last requests sent, for a look at what QGIS asked."""
_canvas_t: list[float | None] = [None]
"""The time on the map canvas. QGIS 3.44's Identify tool gives a provider no time of its own (seen in the W51 dock
check), so a request with no time reads the map the canvas shows, or failing that the last one drawn; with neither,
the run's last map."""


def epoch() -> QDateTime:
    year, month, day = FRAMES_EPOCH
    return QDateTime(QDate(year, month, day), QTime(0, 0), Qt.UTC)


def seconds_at(when: QDateTime) -> float | None:
    """Seconds since the start of the run of a time on the controller; None when there is none."""
    if when is None or not when.isValid():
        return None
    return epoch().msecsTo(when) / MS_PER_S


def at_seconds(seconds: float) -> QDateTime:
    return epoch().addMSecs(round(seconds * MS_PER_S))


def frame_interval(frames_s: list[float]) -> float:
    """The usual time between saved maps; a run's last map may come early, at its end."""
    steps = [b - a for a, b in itertools.pairwise(frames_s) if b > a]
    return float(statistics.median(steps)) if steps else 60.0


class Repainter(QObject):
    """Lives on QGIS's main thread; a drawing made on another thread asks it, through a signal, to draw once more."""

    more = pyqtSignal(str)

    def __init__(self) -> None:
        super().__init__()
        self.more.connect(self._later)
        self.asked: dict[str, int] = {}

    def _later(self, uri: str) -> None:
        QTimer.singleShot(MORE_AFTER_MS, lambda: self._repaint(uri))

    def _repaint(self, uri: str) -> None:
        for layer in QgsProject.instance().mapLayers().values():
            if isinstance(layer, QgsRasterLayer) and layer.providerType() == SLIDER_PROVIDER and layer.source() == uri:
                layer.triggerRepaint()

    def ask(self, uri: str, pending: int) -> None:
        if pending <= 0:
            self.asked[uri] = 0
            return
        self.asked[uri] = self.asked.get(uri, 0) + 1
        if self.asked[uri] <= MORE_TIMES:
            self.more.emit(uri)


_repainter: Repainter | None = None


def _held(provider: QgsRasterDataProvider) -> QgsRasterDataProvider:
    key = id(provider)
    _alive[key] = provider
    provider.destroyed.connect(lambda *_args, key=key: _alive.pop(key, None))
    return provider


def _log(text: str) -> None:
    QgsMessageLog.logMessage(text, LOG_TAG, Qgis.Warning)


class SliderProvider(QgsRasterDataProvider):
    """One run's saved maps as a three-band raster with no fixed pixel: QGIS asks for what is on screen."""

    def __init__(self, uri: str = "", options=None, flags=None) -> None:
        options = options if options is not None else QgsDataProvider.ProviderOptions()
        flags = flags if flags is not None else QgsDataProvider.ReadFlags()
        super().__init__(uri, options, flags)
        self._client: render_client.RenderClient | None = None
        self._info: dict = {}
        self._extent = QgsRectangle()
        self._crs = QgsCoordinateReferenceSystem()
        try:
            self._open(uri)
        except Exception as problem:
            _log(f"The time slider at the pixel could not open {uri}: {problem}")

    def _open(self, uri: str) -> None:
        client = render_client.existing(uri)
        if client is None or not (client.alive or not client.settled):  # a project opened again: start its process
            client = render_client.client_for(uri, settings.engine_text())
        if not client.wait_ready():
            _log(f"The time slider at the pixel could not open {uri}: {client.error}")
            return
        self._client = client
        self._info = client.ready
        self._extent = QgsRectangle(*self._info["extent"])
        self._crs = QgsCoordinateReferenceSystem.fromWkt(self._info["crs"])
        frames = [float(t) for t in self._info["frames_s"]]
        caps = self.temporalCapabilities()
        caps.setHasTemporalCapabilities(True)
        caps.setAvailableTemporalRange(QgsDateTimeRange(at_seconds(frames[0]), at_seconds(frames[-1])))
        caps.setAllAvailableTemporalRanges([QgsDateTimeRange(at_seconds(t), at_seconds(t)) for t in frames])
        caps.setDefaultInterval(QgsInterval(frame_interval(frames), QgsUnitTypes.TemporalSeconds))
        caps.setIntervalHandlingMethod(Qgis.TemporalIntervalMatchMethod.FindClosestMatchToStartOfRange)

    @classmethod
    def create(cls, uri, options, flags=None):
        return _held(cls(uri, options, flags))

    @property
    def info(self) -> dict:
        return self._info

    # What QGIS asks of any raster provider.

    def name(self) -> str:
        return SLIDER_PROVIDER

    def description(self) -> str:
        return "Wadi2D saved maps drawn at the terrain pixel"

    def isValid(self) -> bool:
        return self._client is not None

    def crs(self) -> QgsCoordinateReferenceSystem:
        return self._crs

    def extent(self) -> QgsRectangle:
        return self._extent

    def bandCount(self) -> int:
        return len(BANDS)

    def dataType(self, _band: int):
        return Qgis.DataType.Float32

    def sourceDataType(self, _band: int):
        return Qgis.DataType.Float32

    def sourceHasNoDataValue(self, _band: int) -> bool:
        return True

    def sourceNoDataValue(self, _band: int) -> float:
        return NODATA

    def generateBandName(self, band: int) -> str:
        return BANDS[band - 1][1] if 1 <= band <= len(BANDS) else ""

    def capabilities(self):
        return Qgis.RasterInterfaceCapabilities(
            Qgis.RasterInterfaceCapability.Identify | Qgis.RasterInterfaceCapability.IdentifyValue
        )

    def htmlMetadata(self) -> str:
        info = self._info
        if not info:
            return ""
        return (
            f"{len(info['frames_s'])} saved maps, every {frame_interval(info['frames_s']) / 60.0:g} min; "
            f"cells of {info['dx']:g} m, terrain pixel {info['pixel_m']:g} m; drawn on the {info['backend'].upper()}. "
            f"{info.get('note', '')}"
        )

    def clone(self):
        try:
            return _held(SliderProvider(self.dataSourceUri()))
        except Exception as problem:
            _log(f"The time slider at the pixel could not copy its provider: {problem}")
            return None

    # The drawing.

    def _time(self) -> float | None:
        requested = self.temporalCapabilities().requestedTemporalRange()
        return seconds_at(requested.begin()) if requested.begin().isValid() else None

    def _time_on_screen(self) -> float | None:
        for found in (self._time(), _canvas_t[0], _last_t.get(self.dataSourceUri())):
            if found is not None:
                return found
        return None

    def _nothing(self, width: int, height: int) -> QgsRasterBlock:
        block = QgsRasterBlock(Qgis.DataType.Float32, width, height)
        block.setNoDataValue(NODATA)
        block.setIsNoData()
        return block

    def block(self, band, extent, width, height, feedback=None):
        try:
            if self._client is None or not 1 <= band <= len(BANDS) or width < 1 or height < 1:
                return self._nothing(max(width, 1), max(height, 1))
            if feedback is not None and feedback.isCanceled():
                return self._nothing(width, height)
            if width == 1 and height == 1:  # QGIS's own Identify asks this way: the value at the terrain pixel
                return self._point_block(band, extent)
            request = {
                "op": "values",
                "t": self._time_on_screen(),
                "extent": [extent.xMinimum(), extent.yMinimum(), extent.xMaximum(), extent.yMaximum()],
                "width": int(width),
                "height": int(height),
                "field": BANDS[band - 1][0],
                "nodata": NODATA,
            }
            _last_t[self.dataSourceUri()] = request["t"]
            recent.append(request)
            head, payload = self._client.ask(request)
            if not head.get("ok"):
                _log(f"The time slider at the pixel drew nothing: {head.get('message')}")
                return self._nothing(width, height)
            block = QgsRasterBlock(Qgis.DataType.Float32, width, height)
            block.setData(payload)
            block.setNoDataValue(NODATA)
            if _repainter is not None:
                _repainter.ask(self.dataSourceUri(), int(head.get("pending", 0)))
            return block
        except Exception as problem:
            _log(f"The time slider at the pixel drew nothing: {problem}")
            return self._nothing(max(width, 1), max(height, 1))

    def _point_block(self, band: int, extent) -> QgsRasterBlock:
        centre = extent.center()
        request = {"op": "point", "t": self._time_on_screen(), "x": centre.x(), "y": centre.y()}
        recent.append(request)
        head, _ = self._client.ask(request)
        value = head.get(BANDS[band - 1][0]) if head.get("ok") else None
        block = self._nothing(1, 1)
        if value is not None:
            block.setValue(0, 0, float(value))
        return block

    def identify(self, point, format_, bounding_box=None, width=0, height=0, dpi=96):
        """Depth, speed and class under the point at the terrain pixel, whatever the zoom."""
        try:
            if self._client is None:
                return QgsRasterIdentifyResult(Qgis.RasterIdentifyFormat.Value, {})
            request = {"op": "point", "t": self._time_on_screen(), "x": point.x(), "y": point.y(), "identify": True}
            recent.append(request)
            head, _ = self._client.ask(request)
            if not head.get("ok"):
                return QgsRasterIdentifyResult(Qgis.RasterIdentifyFormat.Value, {})
            return QgsRasterIdentifyResult(
                Qgis.RasterIdentifyFormat.Value,
                {band: head.get(name) for band, (name, _title) in enumerate(BANDS, start=1)},
            )
        except Exception as problem:
            _log(f"The time slider at the pixel could not read a point: {problem}")
            return QgsRasterIdentifyResult(Qgis.RasterIdentifyFormat.Value, {})


def register() -> None:
    """Once per QGIS session; the provider of an earlier load of the plugin stays registered, as QGIS allows no other."""
    global _repainter
    if _repainter is None:
        _repainter = Repainter()
    registry = QgsProviderRegistry.instance()
    if SLIDER_PROVIDER not in registry.providerList():
        registry.registerProvider(QgsProviderMetadata(SLIDER_PROVIDER, "Wadi2D time slider at the pixel", SliderProvider.create))


def open_layer(run: Path | str) -> QgsRasterLayer | None:
    """The layer of a run whose drawing process is ready; None when QGIS refuses it."""
    register()
    layer = QgsRasterLayer(str(Path(run)), LAYER_TITLE, SLIDER_PROVIDER)
    if not layer.isValid():
        return None
    properties = layer.temporalProperties()
    properties.setMode(Qgis.RasterTemporalMode.TemporalRangeFromDataProvider)
    properties.setIsActive(True)
    style.style_pixel_depth(layer)
    return layer


def follow_canvas(canvas) -> None:
    """Keep the canvas's time where Identify can read it; connected once a session."""
    if getattr(follow_canvas, "done", False):
        return

    def moved() -> None:
        span = canvas.temporalRange()
        _canvas_t[0] = seconds_at(span.begin()) if canvas.mapSettings().isTemporal() else None

    canvas.temporalRangeChanged.connect(moved)
    follow_canvas.done = True
    moved()


def show_controller(canvas, main_window, frames_s: list[float]) -> None:
    """The Temporal Controller over the run's saved maps, one step a map, at the start; the last map is reachable."""
    interval = frame_interval(frames_s)
    controller = canvas.temporalController()
    controller.setNavigationMode(QgsTemporalNavigationObject.Animated)
    controller.setTemporalExtents(QgsDateTimeRange(at_seconds(frames_s[0]), at_seconds(frames_s[-1] + interval)))
    controller.setFrameDuration(QgsInterval(interval, QgsUnitTypes.TemporalSeconds))
    controller.rewindToStart()
    for dock in main_window.findChildren(QDockWidget):
        if "temporal" in dock.objectName().lower() or "temporal" in dock.windowTitle().lower():
            dock.setVisible(True)
            dock.raise_()


def load_slider(run: Path | str, canvas, main_window) -> QgsRasterLayer | None:
    layer = open_layer(run)
    if layer is None:
        return None
    _add(layer, Path(run).name)
    follow_canvas(canvas)
    show_controller(canvas, main_window, [float(t) for t in layer.dataProvider().info["frames_s"]])
    return layer
