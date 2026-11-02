# Wadi2D QGIS plugin. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""How depth and hazard look. Colours and class limits are display choices, so they live here, not in the job."""

from __future__ import annotations

from qgis.core import (
    Qgis,
    QgsBilinearRasterResampler,
    QgsCategorizedSymbolRenderer,
    QgsColorRampLegendNodeSettings,
    QgsColorRampShader,
    QgsFillSymbol,
    QgsLineSymbol,
    QgsMarkerSymbol,
    QgsPalettedRasterRenderer,
    QgsPalLayerSettings,
    QgsRasterShader,
    QgsRendererCategory,
    QgsSingleBandPseudoColorRenderer,
    QgsSingleSymbolRenderer,
    QgsTextBufferSettings,
    QgsTextFormat,
    QgsUnitTypes,
    QgsVectorLayerSimpleLabeling,
)
from qgis.PyQt.QtGui import QColor, QFont

DEPTH_STOPS = (  # depth m, then red, green, blue, alpha; the shallow end fades out over the map
    (0.0, (190, 225, 255, 0)),
    (0.05, (165, 210, 250, 110)),
    (0.5, (70, 140, 225, 190)),
    (2.0, (20, 75, 175, 225)),
    (5.0, (8, 30, 100, 245)),
)
HAZARD_CLASSES = (  # upper limit of depth times velocity m2/s, the Australian Rainfall and Runoff H1-H6 bands
    (0.3, (255, 255, 190, 200), "H1  below 0.3"),
    (0.6, (255, 220, 110, 210), "H2  0.3 to 0.6"),
    (1.0, (250, 170, 60, 220), "H3-H4  0.6 to 1.0"),
    (4.0, (225, 90, 40, 230), "H5  1.0 to 4.0"),
    (float("inf"), (150, 20, 30, 240), "H6  above 4.0"),
)
AIDR_COLOURS = ("#0000ff", "#0080ff", "#00ffff", "#00ff00", "#ffff00", "#ff0000")
"""H1 to H6."""
DEPTH_BLUES = (
    (0.0, "#f7fbff"), (0.75, "#a2cae5"), (1.5, "#73b2d8"), (2.25, "#2979b9"), (3.0, "#08306b"),
)  # fmt: skip
"""Depth m and colour of the final depth maps."""
WET_EDGE_M = 0.03
"""The drawing fades in up to this depth, so a wet edge is soft, whatever lies under it."""
OVERSAMPLING = 4.0
SEAM_MM = "0.05"
"""A hairline of a class's own colour, so no viewer shows a seam between two polygons."""
LABEL_BUFFER_MM = 0.8
CHANGE_STOPS = (  # change in the ground m, then red, green, blue, alpha; untouched ground stays clear
    (-5.0, (30, 80, 170, 235)),
    (-0.01, (150, 195, 240, 170)),
    (0.0, (255, 255, 255, 0)),
    (0.01, (240, 205, 150, 170)),
    (5.0, (150, 75, 20, 235)),
)
MAP_ORDER = ("max_depth", "hazard", "max_speed", "max_level", "arrival", "max_mean_depth")
"""Layer order inside a run's group, top first; only the first is switched on."""


def _pseudocolor(layer, ramp_type, items) -> None:
    ramp = QgsColorRampShader(items[0].value, items[-1].value)
    ramp.setColorRampType(ramp_type)
    ramp.setColorRampItemList(items)
    shader = QgsRasterShader()
    shader.setRasterShaderFunction(ramp)
    layer.setRenderer(QgsSingleBandPseudoColorRenderer(layer.dataProvider(), 1, shader))


def style_depth(layer) -> None:
    """A transparent blue ramp: dry ground stays visible, deep water goes dark."""
    items = [
        QgsColorRampShader.ColorRampItem(depth, QColor(*rgba), f"{depth:g} m") for depth, rgba in DEPTH_STOPS
    ]
    _pseudocolor(layer, QgsColorRampShader.Interpolated, items)


def style_change(layer) -> None:
    """Blue where the ground is cut, brown where it is filled."""
    items = [
        QgsColorRampShader.ColorRampItem(change, QColor(*rgba), f"{change:g} m") for change, rgba in CHANGE_STOPS
    ]
    _pseudocolor(layer, QgsColorRampShader.Interpolated, items)


def style_hazard(layer) -> None:
    items = [
        QgsColorRampShader.ColorRampItem(limit, QColor(*rgba), label) for limit, rgba, label in HAZARD_CLASSES
    ]
    _pseudocolor(layer, QgsColorRampShader.Discrete, items)


STYLES = {"max_depth": style_depth, "hazard": style_hazard}


MESH_OPACITY = 0.7
MESH_COLOURS = ("#d7301f", "#fc8d59", "#fdcc8a", "#b3cde3", "#6497b1")
"""Finest cell first."""


def style_mesh(layer, sizes: list[float]) -> None:
    """One colour per cell size, the finest the strongest."""
    from qgis.core import QgsPalettedRasterRenderer
    from qgis.PyQt.QtGui import QColor

    classes = [
        QgsPalettedRasterRenderer.Class(size, QColor(MESH_COLOURS[n % len(MESH_COLOURS)]), f"{size:g} m")
        for n, size in enumerate(sorted(sizes))
    ]
    layer.setRenderer(QgsPalettedRasterRenderer(layer.dataProvider(), 1, classes))
    layer.setOpacity(MESH_OPACITY)
    layer.triggerRepaint()


def _smooth_raster(layer) -> None:
    """Bilinear when zooming in and out, so no raster edge reads as a pixel."""
    pipe = layer.resampleFilter()
    pipe.setZoomedInResampler(QgsBilinearRasterResampler())
    pipe.setZoomedOutResampler(QgsBilinearRasterResampler())
    pipe.setMaxOversampling(OVERSAMPLING)


def _ramp_items(fade_to: float) -> list:
    items = [QgsColorRampShader.ColorRampItem(0.0, QColor(255, 255, 255, 0), "0 m")]
    low = QColor(DEPTH_BLUES[0][1])
    items.append(QgsColorRampShader.ColorRampItem(fade_to, low, f"{fade_to:g} m"))
    for depth, colour in DEPTH_BLUES[1:]:
        items.append(QgsColorRampShader.ColorRampItem(depth, QColor(colour), f"{depth:g} m"))
    return items


def _depth_renderer(layer) -> None:
    _pseudocolor(layer, QgsColorRampShader.Interpolated, _ramp_items(WET_EDGE_M))
    settings = QgsColorRampLegendNodeSettings()
    settings.setSuffix(" m")
    layer.renderer().shader().rasterShaderFunction().setLegendSettings(settings)


def style_depth_drawing(layer) -> None:
    """The final depth map: Blues from 0 to 3 m, the shallow end fading out, smooth at any zoom."""
    _depth_renderer(layer)
    _smooth_raster(layer)


def style_pixel_depth(layer) -> None:
    """The same colours on the numbers of record, pixel by pixel."""
    _depth_renderer(layer)


def style_pixel_hazard(layer) -> None:
    classes = [
        QgsPalettedRasterRenderer.Class(index, QColor(colour), f"H{index}")
        for index, colour in enumerate(AIDR_COLOURS, start=1)
    ]
    layer.setRenderer(QgsPalettedRasterRenderer(layer.dataProvider(), 1, classes))


def style_hazard_classes(layer, labels: list[str]) -> None:
    """The class polygons, in the AIDR colours, each with a hairline of its own colour."""
    categories = []
    for index, colour in enumerate(AIDR_COLOURS, start=1):
        symbol = QgsFillSymbol.createSimple(
            {"color": colour, "outline_color": colour, "outline_width": SEAM_MM, "outline_width_unit": "MM"}
        )
        label = labels[index - 1] if index <= len(labels) else f"H{index}"
        categories.append(QgsRendererCategory(index, symbol, label))
    layer.setRenderer(QgsCategorizedSymbolRenderer("class", categories))


def _labels(layer, field, size, colour, placement, bold=False) -> None:
    fmt = QgsTextFormat()
    font = QFont("Arial")
    font.setBold(bold)
    fmt.setFont(font)
    fmt.setSize(float(size))
    fmt.setSizeUnit(QgsUnitTypes.RenderPoints)
    fmt.setColor(QColor(colour))
    buffer = QgsTextBufferSettings()
    buffer.setEnabled(True)
    buffer.setSize(LABEL_BUFFER_MM)
    buffer.setColor(QColor("white"))
    fmt.setBuffer(buffer)
    settings = QgsPalLayerSettings()
    settings.fieldName = field
    settings.setFormat(fmt)
    settings.placement = placement
    settings.displayAll = True
    layer.setLabeling(QgsVectorLayerSimpleLabeling(settings))
    layer.setLabelsEnabled(True)


def style_domain(layer) -> None:
    symbol = QgsFillSymbol.createSimple({"color": "0,0,0,0", "outline_color": "#0033cc", "outline_width": "0.8"})
    layer.setRenderer(QgsSingleSymbolRenderer(symbol))


def style_cell_grid(layer, largest_scale: int) -> None:
    """Thin orange: it has to read on dark ground, pale ground and blue water alike. Drawn only near enough to read as cells."""
    layer.setRenderer(QgsSingleSymbolRenderer(QgsLineSymbol.createSimple({"color": "255,140,0,200", "width": "0.1"})))
    layer.setScaleBasedVisibility(True)
    layer.setMinimumScale(largest_scale)


def style_boundaries(layer) -> None:
    layer.setRenderer(QgsSingleSymbolRenderer(QgsLineSymbol.createSimple({"color": "#e0001b", "width": "1.4"})))
    _labels(layer, "label", 8.5, "#a00014", Qgis.LabelPlacement.Line, bold=True)


def style_inflows(layer) -> None:
    marker = {"name": "circle", "color": "#d400d4", "outline_color": "white", "size": "3.2"}
    layer.setRenderer(QgsSingleSymbolRenderer(QgsMarkerSymbol.createSimple(marker)))
    _labels(layer, "label", 7.5, "#7a007a", Qgis.LabelPlacement.OrderedPositionsAroundPoint)


def style_lines(layer) -> None:
    layer.setRenderer(QgsSingleSymbolRenderer(QgsLineSymbol.createSimple({"color": "#000000", "width": "1.0"})))
    _labels(layer, "label", 8.0, "#000000", Qgis.LabelPlacement.Line, bold=True)


def style_reaches(layer) -> None:
    layer.setRenderer(QgsSingleSymbolRenderer(QgsLineSymbol.createSimple({"color": "#00b7e0", "width": "0.5"})))


def style_subbasins(layer) -> None:
    lumped = QgsFillSymbol.createSimple({"color": "255,170,60,70", "outline_color": "#b35a00", "outline_width": "0.5"})
    two_d = QgsFillSymbol.createSimple({"color": "40,190,90,110", "outline_color": "#0a7a30", "outline_width": "0.8"})
    categories = [
        QgsRendererCategory("lumped", lumped, "Subbasin, lumped (rain masked in 2D)"),
        QgsRendererCategory("2d", two_d, "Subbasin, 2D rain-on-grid"),
    ]
    layer.setRenderer(QgsCategorizedSymbolRenderer("mode", categories))
    _labels(layer, "label", 8.5, "#5a2d00", Qgis.LabelPlacement.OverPoint, bold=True)
