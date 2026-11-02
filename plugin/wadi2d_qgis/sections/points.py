# Wadi2D QGIS plugin. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""7. Results points: where hydrographs and levels are recorded. Points for levels, lines across the flow for Q."""

from __future__ import annotations

from qgis.core import QgsMapLayerProxyModel

from ..job_builder import layer_features
from .common import Section, field_combo, layer_combo


class PointsSection(Section):
    heading = "7. Results points (optional)"
    start_collapsed = True

    def build(self) -> None:
        self.layer = layer_combo(QgsMapLayerProxyModel.PointLayer | QgsMapLayerProxyModel.LineLayer, "None")
        self.name = field_combo(self.layer)
        self.form.addRow("Design points", self.layer)
        self.form.addRow("Name field", self.name)

    def values(self, crs) -> dict:
        layer = self.layer.currentLayer()
        if layer is None:
            return {"design": []}
        return {"design": layer_features(layer, crs, {"name": self.name.currentField()})}
