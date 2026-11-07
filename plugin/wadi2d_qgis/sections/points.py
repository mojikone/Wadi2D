# Wadi2D QGIS plugin. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""7. Results points: where hydrographs and levels are recorded. Points for levels, lines across the flow for Q."""

from __future__ import annotations

from qgis.core import QgsMapLayerProxyModel

from ..job_builder import layer_features
from ..study_rows import AREA_KEY
from .common import Section, field_combo, layer_combo

AREA_TIP = (
    "Each line's own drainage area, km2, for the depth-area study: a line reads the study's runs either side of it. "
    "A line with none, and every point, gets no design flow. A run does not use it."
)


class PointsSection(Section):
    heading = "7. Results points (optional)"
    start_collapsed = True

    def build(self) -> None:
        self.layer = layer_combo(QgsMapLayerProxyModel.PointLayer | QgsMapLayerProxyModel.LineLayer, "None")
        self.name = field_combo(self.layer)
        self.area = field_combo(self.layer)
        self.area.setToolTip(AREA_TIP)
        self.form.addRow("Design points", self.layer)
        self.form.addRow("Name field", self.name)
        self.form.addRow("Drainage area field, km2", self.area)

    def values(self, crs) -> dict:
        layer = self.layer.currentLayer()
        if layer is None:
            return {"design": []}
        fields = {"name": self.name.currentField(), AREA_KEY: self.area.currentField()}
        return {"design": layer_features(layer, crs, fields)}
