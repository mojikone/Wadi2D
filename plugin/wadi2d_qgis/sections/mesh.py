# Wadi2D QGIS plugin. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""2. Mesh: cell sizes, refinement zones, the preview of tile sizes, and local time stepping."""

from __future__ import annotations

from qgis.core import QgsMapLayerProxyModel
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import QCheckBox, QLabel, QPushButton

from ..job_builder import (
    LOCAL_STEPS,
    MESH_COARSE,
    MESH_ENABLED,
    MESH_FINE_AREA,
    MESH_MID_AREA,
    SPEED_NOTE,
    ZONE_DX_FIELD,
    layer_features,
)
from .common import Section, bind, field_combo, layer_combo, number_box


class MeshSection(Section):
    heading = "2. Mesh (optional)"
    start_collapsed = True

    def build(self) -> None:
        self.enabled = QCheckBox("Refine where the ground changes; the cell size above is the finest")
        self.coarse = number_box(2)
        self.fine_area = number_box(2)
        self.mid_area = number_box(2)
        self.zones = layer_combo(QgsMapLayerProxyModel.PolygonLayer, "No refinement zones")
        self.zone_dx = field_combo(self.zones)
        self.local_steps = QCheckBox("Each tile takes the step it can afford")
        self.speed_note = QLabel(SPEED_NOTE)
        self.speed_note.setWordWrap(True)
        self.preview_button = QPushButton("Preview tile sizes")
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        self.summary.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.form.addRow(self.enabled)
        self.form.addRow("Coarsest cell, m", self.coarse)
        self.form.addRow("Finest cell for wadis over, km2", self.fine_area)
        self.form.addRow("One step coarser for wadis over, km2", self.mid_area)
        self.form.addRow("Refinement zones", self.zones)
        self.form.addRow("Zone cell size field, m", self.zone_dx)
        self.form.addRow("Local time stepping", self.local_steps)
        self.form.addRow(self.speed_note)
        self.form.addRow(self.preview_button)
        self.form.addRow(self.summary)
        self.enabled.toggled.connect(self._enabled_changed)
        self._enabled_changed(False)

    def _enabled_changed(self, on: bool) -> None:
        for widget in (
            self.coarse,
            self.fine_area,
            self.mid_area,
            self.zones,
            self.zone_dx,
            self.preview_button,
        ):
            widget.setEnabled(on)
        if on:
            self.local_steps.setChecked(True)

    def apply_schema(self, schema) -> None:
        self.enabled.setChecked(bool(schema.default(MESH_ENABLED, False)))
        self.enabled.setToolTip(schema.tip(MESH_ENABLED))
        self.local_steps.setChecked(bool(schema.default(LOCAL_STEPS, False)))
        self.local_steps.setToolTip(schema.tip(LOCAL_STEPS))
        bind(self.coarse, schema, MESH_COARSE)
        bind(self.fine_area, schema, MESH_FINE_AREA)
        bind(self.mid_area, schema, MESH_MID_AREA)

    def values(self, crs) -> dict:
        out: dict = {"local_steps": self.local_steps.isChecked()}
        if not self.enabled.isChecked():
            return out
        layer = self.zones.currentLayer()
        name = self.zone_dx.currentField()
        out["mesh"] = {
            "coarse_dx": self.coarse.value(),
            "fine_km2": self.fine_area.value(),
            "mid_km2": self.mid_area.value(),
            "zones": layer_features(layer, crs, {ZONE_DX_FIELD: name}) if layer is not None and name else [],
            "zones_unset": layer is not None and not name,
        }
        return out
