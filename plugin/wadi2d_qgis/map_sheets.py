# Wadi2D QGIS plugin. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Three A3 sheets from a run folder: setup, maximum depth, hazard. QGIS's own print layout, exported to PDF.

Needs only ``qgis.core``, so the Make map button and a script on QGIS's Python run the same code. Things learned the
hard way: a layout map takes ``zoomToExtent``, not ``setExtent``, or it distorts; a legend does not own its layer tree,
so the tree is kept alive here; label placement goes through ``Qgis.LabelPlacement``; font sizes are floats.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from qgis.core import (
    QgsApplication,
    QgsCoordinateReferenceSystem,
    QgsHillshadeRenderer,
    QgsLayerTree,
    QgsLayoutExporter,
    QgsLayoutItemLabel,
    QgsLayoutItemLegend,
    QgsLayoutItemMap,
    QgsLayoutItemPage,
    QgsLayoutItemPicture,
    QgsLayoutItemScaleBar,
    QgsLayoutPoint,
    QgsLayoutSize,
    QgsMapLayerLegendUtils,
    QgsPrintLayout,
    QgsProject,
    QgsRasterLayer,
    QgsTextFormat,
    QgsUnitTypes,
)
from qgis.PyQt.QtGui import QColor, QFont

from .map_notes import RunFacts, depth_notes, hazard_notes, read_facts, setup_notes
from .protocol import PIXEL_DIR
from .result_layers import RunLayers, open_layers

PAGES = 3
PAGE_W, PAGE_H = 420.0, 297.0
MARGIN = 10.0
MAP_Y, MAP_W = 26.0, 280.0
MAP_H = PAGE_H - MAP_Y - MARGIN
SIDE_X, SIDE_W = 296.0, 114.0
NOTES_Y = 118.0
BAR_Y, BAR_MM = 262.0, 80.0
ARROW_W, ARROW_H = 16.0, 22.0
FOOT_Y = 284.0
DPI = 200
TITLE_PT, SUB_PT, NOTE_PT, FOOT_PT = 19.0, 10.5, 9.5, 8.0
EXTENT_MARGIN = 1.04
BAR_SEGMENTS = 4
NICE_STEPS = (1.0, 2.0, 2.5, 5.0)
NORTH_ARROW = "/arrows/NorthArrow_02.svg"
FALLBACK_ARROW = ":/images/north_arrows/layout_default_north_arrow.svg"
HILLSHADE_AZIMUTH, HILLSHADE_ALTITUDE = 315.0, 45.0
SATELLITE = (
    "type=xyz&url=https://mt1.google.com/vt/lyrs%3Ds%26x%3D%7Bx%7D%26y%3D%7By%7D%26z%3D%7Bz%7D"
    "&zmax=17&zmin=0&crs=EPSG3857"
)
SATELLITE_OPACITY = 0.55
BACKGROUND_NOTE = {"satellite": "Imagery: Google.", "hillshade": "Background: hillshade of the DEM."}
"""A background the sheets name in their foot line."""


@dataclass
class SheetBook:
    """What must outlive the export: the layout, its layer trees and the layers."""

    layout: object
    trees: list = field(default_factory=list)
    layers: list = field(default_factory=list)
    facts: RunFacts | None = None


def nice_segment(metres_per_mm: float) -> float:
    """A round length, km, so that four segments come near the bar's length."""
    wanted = BAR_MM * metres_per_mm / BAR_SEGMENTS / 1000.0
    power = 10.0 ** _floor_log10(wanted)
    return max((step * power for step in NICE_STEPS if step * power <= wanted), default=power)


def _floor_log10(value: float) -> int:
    exponent = 0
    while value >= 10.0:
        value /= 10.0
        exponent += 1
    while value < 1.0:
        value *= 10.0
        exponent -= 1
    return exponent


def _background(kind: str, dem: str, project):
    """The layer under everything, in the project but not in its tree."""
    if kind == "satellite":
        layer = QgsRasterLayer(SATELLITE, "Satellite", "wms")
        layer.renderer().setOpacity(SATELLITE_OPACITY)
    else:
        layer = QgsRasterLayer(dem, "Hillshade")
        if layer.isValid():
            layer.setRenderer(QgsHillshadeRenderer(layer.dataProvider(), 1, HILLSHADE_AZIMUTH, HILLSHADE_ALTITUDE))
    if not layer.isValid():
        return None
    project.addMapLayer(layer, False)
    return layer


class _Sheets:
    """Builds the pages of one layout."""

    def __init__(self, project, crs, extent, book: SheetBook, foot: str) -> None:
        self.layout = book.layout
        self.crs, self.extent, self.book, self.foot = crs, extent, book, foot

    def _label(self, page, text, x, y, w, h, size, bold=False, colour="#000000"):
        item = QgsLayoutItemLabel(self.layout)
        item.setText(text)
        font = QFont("Arial")
        font.setBold(bold)
        fmt = QgsTextFormat()
        fmt.setFont(font)
        fmt.setSize(float(size))
        fmt.setSizeUnit(QgsUnitTypes.RenderPoints)
        fmt.setColor(QColor(colour))
        item.setTextFormat(fmt)
        item.attemptMove(QgsLayoutPoint(x, y, QgsUnitTypes.LayoutMillimeters), page=page)
        item.attemptResize(QgsLayoutSize(w, h, QgsUnitTypes.LayoutMillimeters))
        self.layout.addLayoutItem(item)
        return item

    def _map(self, page, layers):
        item = QgsLayoutItemMap(self.layout)
        item.attemptMove(QgsLayoutPoint(MARGIN, MAP_Y, QgsUnitTypes.LayoutMillimeters), page=page)
        item.attemptResize(QgsLayoutSize(MAP_W, MAP_H, QgsUnitTypes.LayoutMillimeters))
        item.setCrs(self.crs)
        item.zoomToExtent(self.extent)
        item.setLayers(layers)
        item.setKeepLayerSet(True)
        item.setFrameEnabled(True)
        self.layout.addLayoutItem(item)
        return item

    def _legend(self, page, linked, layers):
        root = QgsLayerTree()
        self.book.trees.append(root)  # the legend does not own it
        for layer in layers:
            root.addLayer(layer)
        legend = QgsLayoutItemLegend(self.layout)
        legend.setLinkedMap(linked)
        legend.setAutoUpdateModel(False)
        legend.model().setRootGroup(root)
        for node in root.findLayers():
            if isinstance(node.layer(), QgsRasterLayer):  # leave out the band name
                count = len(legend.model().layerLegendNodes(node, True))
                if count > 1:
                    QgsMapLayerLegendUtils.setLegendNodeOrder(node, list(range(1, count)))
                    legend.model().refreshLayerLegend(node)
        legend.setTitle("Legend")
        legend.attemptMove(QgsLayoutPoint(SIDE_X, MAP_Y, QgsUnitTypes.LayoutMillimeters), page=page)
        self.layout.addLayoutItem(legend)
        return legend

    def _scale(self, page, linked):
        bar = QgsLayoutItemScaleBar(self.layout)
        bar.setStyle("Single Box")
        bar.setLinkedMap(linked)
        bar.setUnits(QgsUnitTypes.DistanceKilometers)
        bar.setNumberOfSegments(BAR_SEGMENTS)
        bar.setNumberOfSegmentsLeft(0)
        bar.setUnitsPerSegment(nice_segment(self.extent_per_mm(linked)))
        bar.setUnitLabel("km")
        bar.attemptMove(QgsLayoutPoint(SIDE_X, BAR_Y, QgsUnitTypes.LayoutMillimeters), page=page)
        self.layout.addLayoutItem(bar)

    @staticmethod
    def extent_per_mm(linked) -> float:
        return linked.extent().width() / MAP_W

    def _arrow(self, page, linked):
        arrow = QgsLayoutItemPicture(self.layout)
        path = QgsApplication.svgPaths()[0] + NORTH_ARROW
        arrow.setPicturePath(path if Path(path).is_file() else FALLBACK_ARROW)
        arrow.setLinkedMap(linked)
        arrow.attemptMove(QgsLayoutPoint(PAGE_W - MARGIN - ARROW_W, BAR_Y - 6.0, QgsUnitTypes.LayoutMillimeters), page=page)
        arrow.attemptResize(QgsLayoutSize(ARROW_W, ARROW_H, QgsUnitTypes.LayoutMillimeters))
        self.layout.addLayoutItem(arrow)

    def sheet(self, page, title, sub, layers, legend_layers, notes) -> None:
        self._label(page, title, MARGIN, 8.0, PAGE_W - 2 * MARGIN, 10.0, TITLE_PT, bold=True)
        self._label(page, sub, MARGIN, 18.0, PAGE_W - 2 * MARGIN, 7.0, SUB_PT)
        linked = self._map(page, layers)
        self._legend(page, linked, legend_layers)
        self._scale(page, linked)
        self._arrow(page, linked)
        self._label(page, notes, SIDE_X, NOTES_Y, SIDE_W, BAR_Y - NOTES_Y - 4.0, NOTE_PT)
        self._label(page, self.foot, SIDE_X, FOOT_Y, SIDE_W, 6.0, FOOT_PT, colour="#555555")


def build_book(
    run: Path | str,
    title: str = "",
    background: str = "hillshade",
    caution: str = "",
    leave_out: str = "",
    project=None,
) -> SheetBook:
    """The layout of a run folder, ready to export. ``leave_out`` hides design lines with that word in their name."""
    project = project or QgsProject.instance()
    facts = read_facts(run, leave_out)
    found: RunLayers = open_layers(run, leave_out)
    if found.domain is None:
        raise ValueError("This run has no map layers yet.")
    crs = found.domain.crs()
    if not crs.isValid():
        crs = QgsCoordinateReferenceSystem(project.crs())
    layout = QgsPrintLayout(project)
    layout.initializeDefaults()
    pages = layout.pageCollection()
    pages.page(0).setPageSize("A3", QgsLayoutItemPage.Landscape)
    for _ in range(PAGES - 1):
        page = QgsLayoutItemPage(layout)
        page.setPageSize("A3", QgsLayoutItemPage.Landscape)
        pages.addPage(page)
    book = SheetBook(layout, facts=facts)
    layers = [layer for layer in (*found.setup(), found.depth, found.hazard, *found.record) if layer is not None]
    for layer in layers:
        project.addMapLayer(layer, False)
    under = _background(background, facts.dem, project)
    base = [under] if under is not None else []
    book.layers = layers + base
    extent = found.domain.extent()
    extent.scale(EXTENT_MARGIN)
    foot = " ".join(part for part in (crs.authid() + ".", BACKGROUND_NOTE.get(background, "")) if part)
    title = title or facts.name
    sheets = _Sheets(project, crs, extent, book, foot)
    closing = f"\n\n{caution}" if caution else ""
    over = found.overlays()
    legend_over = [layer for layer in (found.domain, found.boundaries, found.inflows, found.lines) if layer]
    sheets.sheet(
        0, f"{title}: setup", "How the model is built", found.setup() + base,
        [layer for layer in (found.subbasins, found.domain, found.boundaries, found.inflows, found.reaches, found.lines) if layer],
        setup_notes(facts) + closing,
    )  # fmt: skip
    pixel = f"Depth at the {facts.pixel:g} m pixel, sloped water surface"
    sheets.sheet(
        1, f"{title}: maximum depth", pixel, over + [found.depth] + base, [found.depth, *legend_over],
        depth_notes(facts) + closing,
    )  # fmt: skip
    every = f"{facts.map_every_s / 60.0:g}-minute maps" if facts.map_every_s else "the run's maxima"
    sheets.sheet(
        2, f"{title}: AIDR hazard H1 to H6", f"Pixel depth x interpolated velocity, {every}",
        over + [found.hazard] + base, [found.hazard, *legend_over], hazard_notes(facts) + closing,
    )  # fmt: skip
    return book


def sheets_file(run: Path | str) -> Path:
    return Path(run) / PIXEL_DIR / f"{Path(run).name}_maps.pdf"


def export_pdf(book: SheetBook, path: Path | str) -> Path:
    """The PDF of a book; a refusal by the exporter is an error, never a quiet empty file."""
    settings = QgsLayoutExporter.PdfExportSettings()
    settings.dpi = DPI
    settings.rasterizeWholeImage = False
    result = QgsLayoutExporter(book.layout).exportToPdf(str(path), settings)
    if result != QgsLayoutExporter.Success:
        raise OSError(f"The PDF could not be written: exporter code {result}.")
    return Path(path)


def export_images(book: SheetBook, path: Path | str, dpi: int = DPI) -> Path:
    """One PNG per page: ``name.png``, ``name_2.png``, ..."""
    settings = QgsLayoutExporter.ImageExportSettings()
    settings.dpi = dpi
    settings.generateWorldFile = False
    result = QgsLayoutExporter(book.layout).exportToImage(str(path), settings)
    if result != QgsLayoutExporter.Success:
        raise OSError(f"The image could not be written: exporter code {result}.")
    return Path(path)


__all__ = ["SheetBook", "build_book", "export_images", "export_pdf", "nice_segment", "sheets_file"]
