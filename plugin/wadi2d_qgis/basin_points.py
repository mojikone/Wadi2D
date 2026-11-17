# Wadi2D QGIS plugin. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""The Basin points layer on the map (W73): a new one in the model's Inputs > Hydrology, styled by kind, and a click that
adds a point of a kind to it. The generator reads the layer; a click writes a row and nothing else, so the next
Generate basin replays every edit.
"""

from __future__ import annotations

from qgis.core import (
    Qgis,
    QgsCategorizedSymbolRenderer,
    QgsFeature,
    QgsGeometry,
    QgsMarkerSymbol,
    QgsPalLayerSettings,
    QgsPointXY,
    QgsRendererCategory,
    QgsTextFormat,
    QgsVectorLayer,
    QgsVectorLayerSimpleLabeling,
)
from qgis.gui import QgsMapToolEmitPoint
from qgis.PyQt.QtGui import QColor

from .basin_point_rows import LAYER_TITLE, NAME_STEMS, POINT_FIELDS, SNAPPED_TITLE, next_name, provisional_words
from .layer_groups import HYDROLOGY, SLOT_BASIN_POINTS, add_layer, input_group

MARKERS = {
    "outfall": ("triangle", "#c00000"),
    "design_point": ("circle", "#0060c0"),
    "dam": ("square", "#5a2d00"),
    "diversion": ("diamond", "#8a2be2"),
    "source": ("star", "#00a050"),
    "junction": ("circle", "#303030"),
    "remove_junction": ("cross2", "#c00000"),
    "join_subbasins": ("pentagon", "#d08000"),
}
SIZE_MM = "3.4"
LABEL_SIZE = 8.0


def style_points(layer) -> None:
    """One marker per kind, the name beside it."""
    categories = []
    for kind, (shape, colour) in MARKERS.items():
        symbol = QgsMarkerSymbol.createSimple({"name": shape, "color": colour, "outline_color": "#ffffff", "size": SIZE_MM})
        categories.append(QgsRendererCategory(kind, symbol, NAME_STEMS[kind] if kind != "junction" else "Junction"))
    layer.setRenderer(QgsCategorizedSymbolRenderer("kind", categories))
    text = QgsTextFormat()
    text.setSize(LABEL_SIZE)
    text.setColor(QColor("#202020"))
    labels = QgsPalLayerSettings()
    labels.fieldName = "name"
    labels.placement = Qgis.LabelPlacement.OrderedPositionsAroundPoint
    labels.setFormat(text)
    layer.setLabeling(QgsVectorLayerSimpleLabeling(labels))
    layer.setLabelsEnabled(True)


def new_points_layer(crs, model: str) -> QgsVectorLayer:
    """An empty Basin points layer in the model's Inputs > Hydrology. A memory layer: save it to keep it."""
    fields = "&".join(f"field={name}:{kind}" for name, kind in POINT_FIELDS)
    layer = QgsVectorLayer(f"Point?{fields}", LAYER_TITLE, "memory")
    layer.setCrs(crs)
    style_points(layer)
    add_layer(input_group(model, HYDROLOGY), layer, SLOT_BASIN_POINTS, index=0)
    return layer


def add_point(layer, kind: str, point: QgsPointXY, crs=None) -> str:
    """A point of a kind on the layer, named afresh; its name. ``crs`` is the map's, when it differs from the layer's."""
    names = layer.fields().names()
    if "kind" not in names or "name" not in names:
        raise ValueError(f'Layer "{layer.name()}" has no name and kind fields: make a new Basin points layer.')
    if crs is not None and crs != layer.crs():
        from qgis.core import QgsCoordinateTransform, QgsProject

        point = QgsCoordinateTransform(crs, layer.crs(), QgsProject.instance()).transform(point)
    taken = {str(f["name"]) for f in layer.getFeatures()}
    name = next_name(kind, taken)
    feature = QgsFeature(layer.fields())
    feature.setGeometry(QgsGeometry.fromPointXY(point))
    feature.setAttribute("name", name)
    feature.setAttribute("kind", kind)
    if layer.isEditable():
        layer.addFeature(feature)
    else:
        layer.dataProvider().addFeatures([feature])
        layer.updateExtents()
    layer.triggerRepaint()
    return name


class BasinPointsLinks:
    """The Generate box's New layer and Click on the map, on the dock's canvas; held by the dock."""

    def __init__(self, dock) -> None:
        self.dock = dock
        self.box = dock.hydrology.basin
        self.canvas = dock.iface.mapCanvas()
        self.tool = QgsMapToolEmitPoint(self.canvas)
        self.old_tool = None
        self.kind: str | None = None
        self.tool.canvasClicked.connect(self._clicked)
        self.box.new_points_requested.connect(self.new_layer)
        self.box.place_requested.connect(self.start)
        self.box.place_stopped.connect(self.stop)

    def _model(self) -> str:
        from .layer_groups import model_name

        return model_name(self.dock.panel.folder.filePath() or None)

    def new_layer(self) -> QgsVectorLayer:
        dem = self.dock.terrain.dem_layer()
        crs = dem.crs() if dem is not None else self.canvas.mapSettings().destinationCrs()
        layer = new_points_layer(crs, self._model())
        self.box.pour.setLayer(layer)
        self.box.say("A new Basin points layer is in Inputs > Hydrology: add points with Click on the map. Save it to keep it.")
        return layer

    def start(self, kind: str) -> None:
        if self.box.pour.currentLayer() is None:
            self.new_layer()
        self.kind = kind
        self.old_tool = self.canvas.mapTool()
        self.canvas.setMapTool(self.tool)

    def stop(self) -> None:
        if self.canvas.mapTool() is self.tool:
            self.canvas.unsetMapTool(self.tool)
            if self.old_tool is not None:
                self.canvas.setMapTool(self.old_tool)

    def _clicked(self, point, _button=None) -> None:
        layer = self.box.pour.currentLayer()
        self.stop()
        if layer is None or self.kind is None:
            return
        try:
            name = add_point(layer, self.kind, QgsPointXY(point), self.canvas.mapSettings().destinationCrs())
        except ValueError as problem:
            self.box.point_placed(str(problem))
            return
        said = f"{name} ({self.kind}) added to {layer.name()}: Generate basin applies it."
        near = self._nearest_reach(point)  # W106: the stream it lies on, from the last generated basin
        if near is not None:
            said += " " + provisional_words(name, *near, self._snap_m())
        self.box.point_placed(said)

    def _snap_m(self) -> float:
        schema = getattr(self.dock, "schema", None)
        found = schema.default(SNAP_PATH) if schema is not None else None
        return float(found) if found else DEFAULT_SNAP_M

    def _nearest_reach(self, point) -> tuple[str | None, float | None, float] | None:
        """The last generated basin's reach nearest a click, the drainage area at its lower end and the distance;
        None with no generated basin. The click is in the map's CRS, the basin in the DEM's: one of them, the DEM's."""
        model, path = self.box.model, self.box.json_path
        if not model or not path:
            return None
        from pathlib import Path

        reaches = QgsVectorLayer(f"{Path(path).with_name('basin.gpkg')}|layername=reaches", "reaches", "ogr")
        if not reaches.isValid():
            return None
        here = QgsGeometry.fromPointXY(QgsPointXY(point))
        crs = self.canvas.mapSettings().destinationCrs()
        if crs != reaches.crs():
            from qgis.core import QgsCoordinateTransform, QgsProject

            here.transform(QgsCoordinateTransform(crs, reaches.crs(), QgsProject.instance()))
        best = (None, float("inf"))
        for feature in reaches.getFeatures():
            distance = feature.geometry().distance(here)
            if distance < best[1]:
                best = (str(feature["name"]), distance)
        if best[0] is None:
            return None
        elements = {e["name"]: e for e in model.get("elements", [])}
        below = (elements.get(best[0]) or {}).get("downstream")
        area = ((elements.get(below) or {}).get("parameters") or {}).get("drainage_area_km2", {}).get("value")
        return best[0], area, best[1]


SNAP_PATH = "basin.snap_m"
DEFAULT_SNAP_M = 100.0
SLOT_SNAPPED = "basin points snapped"
"""The lines from each point to where it snapped: the next Generate basin replaces them."""


def show_snapped(rows: list[dict], crs, model: str):
    """Each point's move to its stream as a line, labelled with the drainage area there, in Inputs > Hydrology."""
    from qgis.core import QgsLineSymbol, QgsSingleSymbolRenderer

    from .layer_groups import clear_slot

    clear_slot(model, SLOT_SNAPPED)
    if not rows:
        return None
    layer = QgsVectorLayer("LineString?field=name:string&field=area_km2:double&field=moved_m:double&field=label:string", SNAPPED_TITLE, "memory")
    layer.setCrs(crs)
    features = []
    for row in rows:
        feature = QgsFeature(layer.fields())
        start, end = QgsPointXY(row["x"], row["y"]), QgsPointXY(*row["outlet"])
        feature.setGeometry(QgsGeometry.fromPolylineXY([start, end]))
        area = row["area_km2"]
        feature.setAttributes([row["name"], area, row["moved_m"], f"{row['name']}: {area:,.2f} km2" if area is not None else row["name"]])
        features.append(feature)
    layer.dataProvider().addFeatures(features)
    layer.updateExtents()
    layer.setRenderer(QgsSingleSymbolRenderer(QgsLineSymbol.createSimple({"color": "#c00000", "width": "0.8", "line_style": "dash"})))
    text = QgsTextFormat()
    text.setSize(LABEL_SIZE)
    text.setColor(QColor("#c00000"))
    labels = QgsPalLayerSettings()
    labels.fieldName = "label"
    labels.setFormat(text)
    layer.setLabeling(QgsVectorLayerSimpleLabeling(labels))
    layer.setLabelsEnabled(True)
    add_layer(input_group(model, HYDROLOGY), layer, SLOT_SNAPPED, index=0)
    return layer
