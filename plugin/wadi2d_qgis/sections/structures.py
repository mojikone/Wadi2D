# Wadi2D QGIS plugin. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""4. Structures: line layers for crests, walls, spillways, burn lines, embankments and channels, each with its fields."""

from __future__ import annotations

from qgis.core import QgsMapLayerProxyModel
from qgis.PyQt.QtCore import Qt, pyqtSignal
from qgis.PyQt.QtWidgets import QCheckBox, QFormLayout, QLabel, QPushButton, QWidget

from ..job_builder import SPILLWAY_C, layer_features
from ..profile_table import EDGE_KINDS, ProfileStore, apply_levels, keyed
from ..shaped import SHAPED_KINDS
from .common import Section, field_combo, layer_combo
from .shaped_rows import ROWS, ProfileRow, ShapedRows, lines_of

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
    edit_requested = pyqtSignal(str)
    """The profile editor is wanted for this kind."""

    def build(self) -> None:
        self.layers = {}
        self.fields = {}
        self.profiles = ProfileStore()
        self.profile_rows = {}
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
            if kind in EDGE_KINDS:
                self.profile_rows[kind] = ProfileRow(kind, picker, self.profiles)
                sub.addRow("Elevations along the line", self.profile_rows[kind])
            self.form.addRow(rows)
            picker.layerChanged.connect(lambda layer, box=rows: box.setVisible(layer is not None))
        self.shaped = {}
        for kind in SHAPED_KINDS:
            picker = layer_combo(QgsMapLayerProxyModel.LineLayer, "None")
            self.layers[kind] = picker
            self.form.addRow(ROWS[kind][0], picker)
            self.shaped[kind] = ShapedRows(kind, picker, self.profiles)
            self.fields[kind] = self.shaped[kind].fields
            self.profile_rows[kind] = self.shaped[kind].profile_row
            self.form.addRow(self.shaped[kind])
        for kind, row in self.profile_rows.items():
            row.button.clicked.connect(lambda _checked=False, name=kind: self.edit_requested.emit(name))
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
            structures[kind] = [
                apply_levels(feature, self.profiles.table(layer, kind, key)) for key, _fid, feature in self._parts(kind, crs)
            ]
        return {"structures": structures, "terrain_map": self.terrain_map.isChecked()}

    def _parts(self, kind: str, crs) -> list:
        chosen = {key: combo.currentField() for key, combo in self.fields[kind].items()}
        return keyed(layer_features(self.layers[kind].currentLayer(), crs, chosen, with_id=True))

    def lines(self, kind: str, crs) -> list:
        """The lines of one kind for the profile editor."""
        return self.shaped[kind].lines(crs) if kind in self.shaped else lines_of(kind, self._parts(kind, crs))

    def refresh_profiles(self) -> None:
        for row in self.profile_rows.values():
            row.refresh()
