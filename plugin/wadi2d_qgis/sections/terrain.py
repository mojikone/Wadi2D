# Wadi2D QGIS plugin. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""1. Terrain: the DEM, the cell size, the domain, the roughness."""

from __future__ import annotations

from qgis.core import QgsMapLayerProxyModel, QgsProject
from qgis.PyQt.QtWidgets import QCheckBox

from .. import section_status
from ..dem_choice import default_dem
from ..job_builder import DX, FILL_PITS, MANNING, PREFERRED_DX, layer_features, map_extent, raster_path
from ..model_types import LUMPED
from .common import Section, ValueOrRaster, bind, layer_combo, number_box


class TerrainSection(Section):
    heading = "1. Terrain"
    key = "terrain"

    def build(self) -> None:
        self.dem = layer_combo(QgsMapLayerProxyModel.RasterLayer, "Choose the DEM")  # W101: never a run's raster
        self.dx = number_box(2)
        self.domain = layer_combo(QgsMapLayerProxyModel.PolygonLayer, "Current map extent")
        self.manning = ValueOrRaster(3, "Same value everywhere")
        self.form.addRow("DEM", self.dem)
        self.form.addRow("Cell size, m", self.dx)
        self.form.addRow("Domain", self.domain)
        self.form.addRow("Manning n", self.manning)
        self.fill_pits = QCheckBox("Fill pits: small deep holes of the terrain, to their spill level")
        self.form.addRow(self.fill_pits)
        self.dem.layerChanged.connect(self._dem_changed)
        self.choose_default_dem()
        self._dem_changed(self.dem.currentLayer())

    def choose_default_dem(self) -> None:
        """The DEM a run in the project was made on, or none: a layer picker would take the first raster, which in a
        project of results is a depth map (his fault of 2026-11-16)."""
        self.dem.setLayer(default_dem(QgsProject.instance()))

    def _dem_changed(self, layer) -> None:
        if layer is not None:
            self.dx.setSingleStep(layer.rasterUnitsPerPixelX())

    def apply_schema(self, schema) -> None:
        bind(self.dx, schema, DX, default=PREFERRED_DX)
        bind(self.manning.box, schema, MANNING)
        self.fill_pits.setChecked(bool(schema.default(FILL_PITS, False)))
        self.fill_pits.setToolTip(schema.tip(FILL_PITS))
        self.fill_pits.setEnabled(schema.has(FILL_PITS))  # an engine from before W85 would refuse the field

    def set_model_type(self, kind: str | None) -> None:
        """His item 7 (W101): a Lumped model asks for no cell size, no Manning and no pit fill; the engine's lumped run
        reads none of them. Their values stay as they were, for the day the type has a 2D part again. A basin
        generated in Hydrology still reads Manning for its reaches (W101 README, found 1)."""
        lumped = kind == LUMPED
        for widget in (self.dx, self.manning, self.fill_pits):
            widget.setVisible(not lumped)
            label = self.form.labelForField(widget)
            if label is not None:
                label.setVisible(not lumped)

    def dem_layer(self):
        return self.dem.currentLayer()

    def standing(self, kind=None):
        layer, domain, raster = self.dem_layer(), self.domain.currentLayer(), self.manning.raster.currentLayer()
        return section_status.terrain(
            layer.name() if layer is not None else None,
            layer is not None and raster_path(layer) is not None,
            layer is not None and layer.crs().isGeographic(),
            self.dx.value(),
            domain.name() if domain is not None else None,
            self.manning.value(),
            raster.name() if raster is not None else None,
        )

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
            "fill_pits": self.fill_pits.isChecked() and self.fill_pits.isEnabled(),
        }
        if domain is not None:
            values["domain"] = layer_features(domain, crs)
        else:
            values["extent"] = map_extent(self.canvas, crs, layer.extent())
        return values
