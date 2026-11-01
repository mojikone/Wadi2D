# Wadi2D QGIS plugin. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""1. Terrain: the DEM, the cell size, the domain, the roughness."""

from __future__ import annotations

from qgis.core import QgsMapLayerProxyModel

from ..job_builder import DX, MANNING, PREFERRED_DX, layer_features, map_extent, raster_path
from .common import Section, ValueOrRaster, bind, layer_combo, number_box


class TerrainSection(Section):
    heading = "1. Terrain"

    def build(self) -> None:
        self.dem = layer_combo(QgsMapLayerProxyModel.RasterLayer)
        self.dx = number_box(2)
        self.domain = layer_combo(QgsMapLayerProxyModel.PolygonLayer, "Current map extent")
        self.manning = ValueOrRaster(3, "Same value everywhere")
        self.form.addRow("DEM", self.dem)
        self.form.addRow("Cell size, m", self.dx)
        self.form.addRow("Domain", self.domain)
        self.form.addRow("Manning n", self.manning)
        self.dem.layerChanged.connect(self._dem_changed)
        self._dem_changed(self.dem.currentLayer())

    def _dem_changed(self, layer) -> None:
        if layer is not None:
            self.dx.setSingleStep(layer.rasterUnitsPerPixelX())

    def apply_schema(self, schema) -> None:
        bind(self.dx, schema, DX, default=PREFERRED_DX)
        bind(self.manning.box, schema, MANNING)

    def dem_layer(self):
        return self.dem.currentLayer()

    def values(self, crs) -> dict:
        layer = self.dem_layer()
        domain = self.domain.currentLayer()
        values = {
            "dem": raster_path(layer),
            "crs": crs.authid(),
            "geographic": crs.isGeographic(),
            "pixel": layer.rasterUnitsPerPixelX(),
            "dx": self.dx.value(),
            "manning": self.manning.value(),
            "manning_raster": self.manning.path(),
        }
        if domain is not None:
            values["domain"] = layer_features(domain, crs)
        else:
            values["extent"] = map_extent(self.canvas, crs, layer.extent())
        return values
