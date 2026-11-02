# Wadi2D QGIS plugin. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""4. Structures: line layers for crests, walls, spillways, burn lines, embankments and channels, each with its fields."""

from __future__ import annotations

from qgis.core import QgsMapLayerProxyModel
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import QCheckBox, QFormLayout, QLabel, QPushButton, QWidget

from ..job_builder import SPILLWAY_C, layer_features
from ..shaped import SHAPED_KINDS
from .common import Section, field_combo, layer_combo
from .shaped_rows import ROWS, ShapedRows

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
    heading = "4. Structures (optional)"
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
        self.shaped = {}
        for kind in SHAPED_KINDS:
            picker = layer_combo(QgsMapLayerProxyModel.LineLayer, "None")
            self.layers[kind] = picker
            self.form.addRow(ROWS[kind][0], picker)
            self.shaped[kind] = ShapedRows(kind, picker)
            self.fields[kind] = self.shaped[kind].fields
            self.form.addRow(self.shaped[kind])
        self.terrain_map = QCheckBox("Write the modified terrain with the run")
        self.preview_button = QPushButton("Preview terrain")
        self.profile_button = QPushButton("Sections and long profile...")
        self.profile_button.hide()
        self.preview_label = QLabel()
        self.preview_label.setWordWrap(True)
        self.preview_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.form.addRow(self.terrain_map)
        self.form.addRow(self.preview_button)
        self.form.addRow(self.profile_button)
        self.form.addRow(self.preview_label)

    def apply_schema(self, schema) -> None:
        tip = schema.tip(SPILLWAY_C)
        self.fields["spillway"]["coefficient"].setToolTip(tip)
        for rows in self.shaped.values():
            rows.apply_schema(schema)

    def values(self, crs) -> dict:
        structures = {}
        for kind, picker in self.layers.items():
            layer = picker.currentLayer()
            if layer is None:
                continue
            if kind in self.shaped:
                structures[kind] = self.shaped[kind].features(crs)
                continue
            chosen = {key: combo.currentField() for key, combo in self.fields[kind].items()}
            structures[kind] = layer_features(layer, crs, chosen)
        return {"structures": structures, "terrain_map": self.terrain_map.isChecked()}
