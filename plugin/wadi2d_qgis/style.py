# Wadi2D QGIS plugin. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""How depth and hazard look. Colours and class limits are display choices, so they live here, not in the job."""

from __future__ import annotations

import itertools

from qgis.core import (
    Qgis,
    QgsBilinearRasterResampler,
    QgsCategorizedSymbolRenderer,
    QgsColorRampLegendNodeSettings,
    QgsColorRampShader,
    QgsFillSymbol,
    QgsGraduatedSymbolRenderer,
    QgsLinePatternFillSymbolLayer,
    QgsLineSymbol,
    QgsMarkerSymbol,
    QgsMeshDatasetIndex,
    QgsMeshRendererScalarSettings,
    QgsPalettedRasterRenderer,
    QgsPalLayerSettings,
    QgsRasterShader,
    QgsRendererCategory,
    QgsRendererRange,
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
SPEED_STOPS = ((0.0, "#2c7bb6"), (1.0, "#abd9e9"), (2.0, "#ffffbf"), (3.5, "#fdae61"), (5.0, "#d7191c"))
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
DEPTH_CUTOFF_M = 0.05
"""Depth below which no depth layer draws a cell or a pixel (W88: a rain-on-grid map painted every cell wet). A
display choice: the rasters keep their values; the dock's Run section sets it, saved per user."""
DEPTH_CUTOFF_MAX_M = 1.0
MAP_ORDER = ("max_depth", "hazard", "max_speed", "max_level", "arrival", "max_mean_depth")
"""Layer order inside a run's group, top first; only the first is switched on."""


def depth_cutoff() -> float:
    """The cutoff in force: the user's, else :data:`DEPTH_CUTOFF_M`."""
    from .settings import depth_cutoff as saved

    return saved()


def cut_items(items: list, cutoff: float) -> list:
    """A depth ramp that starts at ``cutoff``: the colour there read off the ramp, nothing below it. 0 is the ramp."""
    if cutoff <= 0.0 or cutoff <= items[0].value:
        return items
    above = [item for item in items if item.value > cutoff]
    below = [item for item in items if item.value <= cutoff][-1]
    if not above:
        return [QgsColorRampShader.ColorRampItem(cutoff, below.color, f"{cutoff:g} m")]
    nxt = above[0]
    share = (cutoff - below.value) / (nxt.value - below.value)
    mixed = QColor(
        *(round(a + share * (b - a)) for a, b in zip(below.color.getRgb(), nxt.color.getRgb(), strict=True))
    )
    return [QgsColorRampShader.ColorRampItem(cutoff, mixed, f"{cutoff:g} m"), *above]


CUTOFF_STEP_M = 1e-4
"""Width of the step from clear to the cutoff's colour: a value below the cutoff reads the clear item."""


def _depth_shader(items: list, cutoff: float | None = None) -> QgsColorRampShader:
    """An interpolated depth shader cut at the cutoff: a value below it is not drawn, one above the ramp's top takes
    the deepest colour. Not by the shader's clip, which hides both ends, so every pool deeper than the ramp went blank."""
    cutoff = depth_cutoff() if cutoff is None else cutoff
    cut = cut_items(items, cutoff)
    if cut is not items:
        clear = QColor(cut[0].color)
        clear.setAlpha(0)
        cut = [QgsColorRampShader.ColorRampItem(cut[0].value - CUTOFF_STEP_M, clear, ""), *cut]
    shader = QgsColorRampShader(cut[0].value, cut[-1].value)
    shader.setColorRampType(QgsColorRampShader.Interpolated)
    shader.setColorRampItemList(cut)
    shader.setClip(False)
    return shader


DEPTH_STYLE = "wadi2d/depth_style"
"""On a layer styled by one of the depth styles: which, so a new cutoff restyles it (:func:`restyle_depth_layers`)."""


def _depth_pseudocolor(layer, items: list) -> None:
    shader = QgsRasterShader()
    shader.setRasterShaderFunction(_depth_shader(items))
    layer.setRenderer(QgsSingleBandPseudoColorRenderer(layer.dataProvider(), 1, shader))


def _tag(layer, name: str) -> None:
    layer.setCustomProperty(DEPTH_STYLE, name)


def restyle_depth_layers() -> int:
    """Every depth layer of the project styled again at the cutoff in force; how many."""
    from qgis.core import QgsProject

    styles = {
        "depth": style_depth, "pixel_depth": style_pixel_depth, "depth_drawing": style_depth_drawing,
        "frames": style_frames, "strip_depth": style_strip_depth,
    }  # fmt: skip
    count = 0
    for layer in QgsProject.instance().mapLayers().values():
        make = styles.get(layer.customProperty(DEPTH_STYLE) or "")
        if make is not None:
            make(layer)
            layer.triggerRepaint()
            count += 1
    return count


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
    _depth_pseudocolor(layer, items)
    _tag(layer, "depth")


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
    _depth_pseudocolor(layer, _ramp_items(WET_EDGE_M))
    settings = QgsColorRampLegendNodeSettings()
    settings.setSuffix(" m")
    layer.renderer().shader().rasterShaderFunction().setLegendSettings(settings)


def style_depth_drawing(layer) -> None:
    """The final depth map: Blues from 0 to 3 m, the shallow end fading out, smooth at any zoom."""
    _depth_renderer(layer)
    _smooth_raster(layer)
    _tag(layer, "depth_drawing")


def style_pixel_depth(layer) -> None:
    """The same colours on the numbers of record, pixel by pixel."""
    _depth_renderer(layer)
    _tag(layer, "pixel_depth")


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


def style_strip_cells(layer) -> None:
    """The aligned cells as outlines only, so the depth drawing shows through them."""
    symbol = QgsFillSymbol.createSimple({"color": "0,0,0,0", "outline_color": "80,80,80,220", "outline_width": "0.12"})
    layer.setRenderer(QgsSingleSymbolRenderer(symbol))


def style_strip_depth(layer) -> None:
    """The aligned cells filled by their maximum depth in the cell maps' blues, a cell under the cutoff left empty."""
    cutoff = depth_cutoff()
    stops = [(depth, rgba) for depth, rgba in DEPTH_STOPS if depth > cutoff]
    edges = [cutoff, *(depth for depth, _rgba in stops)]
    ranges = []
    for low, high, (_depth, rgba) in zip(edges, edges[1:] + [float("inf")], [*stops, stops[-1]], strict=False):
        symbol = QgsFillSymbol.createSimple({"color": ",".join(str(v) for v in rgba), "outline_style": "no"})
        top = f"{high:g}" if high != float("inf") else "deeper"
        ranges.append(QgsRendererRange(low, high if high != float("inf") else 1e9, symbol, f"{low:g} to {top} m"))
    layer.setRenderer(QgsGraduatedSymbolRenderer("max_depth_m", ranges))
    _tag(layer, "strip_depth")


def style_strip_faces(layer) -> None:
    """A corridor's faces by kind: on a bank line red, the join to the squares orange, the inner ones hidden."""
    categories = [
        QgsRendererCategory("breakline", QgsLineSymbol.createSimple({"color": "#c00000", "width": "0.5"}), "On a bank line"),
        QgsRendererCategory("interface", QgsLineSymbol.createSimple({"color": "#e08a00", "width": "0.35"}), "Join to the squares"),
    ]
    inner = QgsRendererCategory("inner", QgsLineSymbol.createSimple({"color": "0,0,0,0", "width": "0.0"}), "Inner face")
    inner.setRenderState(False)
    layer.setRenderer(QgsCategorizedSymbolRenderer("kind", [*categories, inner]))


def _frame_shader(kind, items) -> QgsColorRampShader:
    shader = QgsColorRampShader(items[0].value, items[-1].value)
    shader.setColorRampType(kind)
    shader.setColorRampItemList(items)
    return shader


def _depth_frames() -> QgsColorRampShader:
    items = [QgsColorRampShader.ColorRampItem(depth, QColor(*colour), f"{depth:g} m") for depth, colour in DEPTH_STOPS]
    return _depth_shader(items)


def _speed_frames() -> QgsColorRampShader:
    items = [QgsColorRampShader.ColorRampItem(speed, QColor(colour), f"{speed:g} m/s") for speed, colour in SPEED_STOPS]
    return _frame_shader(QgsColorRampShader.Interpolated, items)


def _hazard_frames() -> QgsColorRampShader:
    items = [
        QgsColorRampShader.ColorRampItem(index + 0.5, QColor(colour), f"H{index}")
        for index, colour in enumerate(AIDR_COLOURS, start=1)
    ]
    return _frame_shader(QgsColorRampShader.Discrete, items)


def style_frames(layer) -> None:
    """Depth shows first; speed and hazard are one click away in the layer's own styling panel. Each cell draws flat."""
    shaders = {"depth": _depth_frames, "speed": _speed_frames, "hazard": _hazard_frames}
    settings = layer.rendererSettings()
    active = None
    for group in range(layer.datasetGroupCount()):
        name = layer.datasetGroupMetadata(QgsMeshDatasetIndex(group, 0)).name().lower()
        made = next((make for key, make in shaders.items() if name.startswith(key)), None)
        if made is None:
            continue
        shader = made()
        scalar = QgsMeshRendererScalarSettings()
        scalar.setClassificationMinimumMaximum(shader.minimumValue(), shader.maximumValue())  # first: it crashes QGIS
        scalar.setColorRampShader(shader)  # once it has a shader with no source ramp to reclassify
        scalar.setDataResamplingMethod(QgsMeshRendererScalarSettings.NoResampling)
        settings.setScalarSettings(group, scalar)
        if name.startswith("depth"):
            active = group
    settings.setActiveScalarDatasetGroup(active if active is not None else 0)
    layer.setRendererSettings(settings)
    _tag(layer, "frames")


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


def style_basin_subbasins(layer) -> None:
    """A generated subbasin: complete ones in one tone, those lacking a parameter in another, named."""
    complete = QgsFillSymbol.createSimple({"color": "120,170,230,60", "outline_color": "#1f4e8c", "outline_width": "0.4"})
    lacking = QgsFillSymbol.createSimple({"color": "230,150,60,90", "outline_color": "#9a4a00", "outline_width": "0.6"})
    categories = [
        QgsRendererCategory("complete", complete, "Subbasin, parameters complete (lumped by default)"),
        QgsRendererCategory("lacking", lacking, "Subbasin lacking a parameter (runs as rain-on-grid)"),
    ]
    layer.setRenderer(QgsCategorizedSymbolRenderer("if(\"missing\" = '', 'complete', 'lacking')", categories))
    _labels(layer, "name", 8.0, "#1f3a66", Qgis.LabelPlacement.OverPoint, bold=True)


def style_basin_reaches(layer) -> None:
    layer.setRenderer(QgsSingleSymbolRenderer(QgsLineSymbol.createSimple({"color": "#0060c0", "width": "0.9"})))
    _labels(layer, "name", 7.5, "#003c80", Qgis.LabelPlacement.Line)


def style_basin_junctions(layer) -> None:
    marker = {"name": "square", "color": "#ffffff", "outline_color": "#003c80", "outline_width": "0.5", "size": "2.6"}
    layer.setRenderer(QgsSingleSymbolRenderer(QgsMarkerSymbol.createSimple(marker)))
    _labels(layer, "name", 7.5, "#003c80", Qgis.LabelPlacement.OrderedPositionsAroundPoint, bold=True)


def style_subbasins(layer) -> None:
    lumped = QgsFillSymbol.createSimple({"color": "255,170,60,70", "outline_color": "#b35a00", "outline_width": "0.5"})
    two_d = QgsFillSymbol.createSimple({"color": "40,190,90,110", "outline_color": "#0a7a30", "outline_width": "0.8"})
    categories = [
        QgsRendererCategory("lumped", lumped, "Subbasin, lumped (rain masked in 2D)"),
        QgsRendererCategory("2d", two_d, "Subbasin, 2D rain-on-grid"),
    ]
    layer.setRenderer(QgsCategorizedSymbolRenderer("mode", categories))
    _labels(layer, "label", 8.5, "#5a2d00", Qgis.LabelPlacement.OverPoint, bold=True)


HMS_HATCH = "#8a4b08"
"""The catchments that ran the HMS way (W88): hatched, so the 2D results under and beside them still read."""
HMS_LEFT_OUT = "#5a5a5a"
"""The same, left out of the 2D mesh: grey, the grid has no cell there."""


def _hatched(colour: str, angle: float) -> QgsFillSymbol:
    symbol = QgsFillSymbol.createSimple({"color": "0,0,0,0", "outline_color": colour, "outline_width": "0.6"})
    hatch = QgsLinePatternFillSymbolLayer()
    hatch.setLineAngle(angle)
    hatch.setDistance(2.5)
    hatch.setColor(QColor(colour))
    hatch.setLineWidth(0.2)
    symbol.appendSymbolLayer(hatch)
    return symbol


def style_network_subbasins(layer) -> None:
    """The lumped subbasins of a run, hatched; those the 2D mesh left out in grey; labelled with area and peak."""
    categories = [
        QgsRendererCategory(0, _hatched(HMS_HATCH, 45.0), "Ran the HMS way, its water routed by the lumped network"),
        QgsRendererCategory(1, _hatched(HMS_LEFT_OUT, -45.0), "Ran the HMS way, left out of the 2D mesh"),
    ]
    layer.setRenderer(QgsCategorizedSymbolRenderer("left_out", categories))
    _labels(layer, "label", 8.0, "#5a2d00", Qgis.LabelPlacement.OverPoint, bold=True)


def style_network_reaches(layer) -> None:
    layer.setRenderer(QgsSingleSymbolRenderer(QgsLineSymbol.createSimple({"color": "#0060c0", "width": "1.0"})))
    _labels(layer, "label", 7.5, "#003c80", Qgis.LabelPlacement.Line)


def style_network_points(layer) -> None:
    marker = {"name": "diamond", "color": "#ffffff", "outline_color": "#003c80", "outline_width": "0.6", "size": "3.2"}
    layer.setRenderer(QgsSingleSymbolRenderer(QgsMarkerSymbol.createSimple(marker)))
    _labels(layer, "label", 7.5, "#003c80", Qgis.LabelPlacement.OrderedPositionsAroundPoint, bold=True)


RAIN_BLUES = ("#eff3ff", "#bdd7e7", "#6baed6", "#3182bd", "#08519c")
"""Total rain depth from least to most: the storm map before the run (W77)."""


def _rain_colours(low: float, high: float) -> list[tuple[float, QColor]]:
    span = (high - low) or 1.0
    step = span / (len(RAIN_BLUES) - 1)
    return [(low + n * step, QColor(colour)) for n, colour in enumerate(RAIN_BLUES)]


def style_rain_areas(layer, low: float, high: float) -> None:
    """Each lumped subbasin and the 2D area in the blue of its depth, named with it."""
    stops = _rain_colours(low, high)
    bands = [(start, end, colour) for (start, _c), (end, colour) in itertools.pairwise(stops)] if high > low else [
        (low, high, stops[-1][1])
    ]  # fmt: skip
    ranges = []
    for start, end, colour in bands:
        symbol = QgsFillSymbol.createSimple({"outline_color": "#1f3a66", "outline_width": "0.4"})
        symbol.setColor(colour)
        symbol.setOpacity(0.75)
        ranges.append(QgsRendererRange(start, end, symbol, f"{start:.0f} to {end:.0f} mm"))
    layer.setRenderer(QgsGraduatedSymbolRenderer("depth_mm", ranges))
    _labels(layer, "label", 8.0, "#08306b", Qgis.LabelPlacement.OverPoint, bold=True)


def style_rain_total(layer, low: float, high: float) -> None:
    """The total depth over the domain, the same blues."""
    items = [QgsColorRampShader.ColorRampItem(value, colour, f"{value:.0f} mm") for value, colour in _rain_colours(low, high)]
    _pseudocolor(layer, QgsColorRampShader.Interpolated, items)
    layer.setOpacity(0.8)
