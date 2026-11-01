# Wadi2D QGIS plugin. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""3. Structures: line layers for crests, walls, spillways and burn lines, each with its fields."""

from __future__ import annotations

from qgis.core import QgsMapLayerProxyModel
from qgis.PyQt.QtWidgets import QFormLayout, QWidget

from ..job_builder import SPILLWAY_C, layer_features
from .common import Section, field_combo, layer_combo

RELATED = {
    "crest_line": ("Crest lines", {"crest_z": "Crest elevation field"}),
    "wall": ("Walls", {}),
    "spillway": (
        "Spillways",
        {"crest_z": "Crest elevation field", "coefficient": "C field", "length": "Length field"},
    ),
    "burn_line": ("Burn lines", {"crest_z": "Invert elevation field"}),
}


class StructuresSection(Section):
    heading = "3. Structures (optional)"
    start_collapsed = True

    def build(self) -> None:
        self.layers = {}
        self.fields = {}
        for kind, (label, wanted) in RELATED.items():
            picker = layer_combo(QgsMapLayerProxyModel.LineLayer, "None")
            self.layers[kind] = picker
            self.form.addRow(label, picker)
            rows = QWidget()
            rows.hide()
            sub = QFormLayout(rows)
            sub.setContentsMargins(0, 0, 0, 0)
            self.fields[kind] = {key: field_combo(picker) for key in wanted}
            for key, text in wanted.items():
                sub.addRow(text, self.fields[kind][key])
            self.form.addRow(rows)
            picker.layerChanged.connect(lambda layer, box=rows: box.setVisible(layer is not None))

    def apply_schema(self, schema) -> None:
        tip = schema.tip(SPILLWAY_C)
        self.fields["spillway"]["coefficient"].setToolTip(tip)

    def values(self, crs) -> dict:
        structures = {}
        for kind, picker in self.layers.items():
            layer = picker.currentLayer()
            if layer is None:
                continue
            chosen = {key: combo.currentField() for key, combo in self.fields[kind].items()}
            structures[kind] = layer_features(layer, crs, chosen)
        return {"structures": structures}
