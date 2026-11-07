# Wadi2D QGIS plugin. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""2. Mesh: cell sizes, refinement zones and lines, the preview of tile sizes, and local time stepping."""

from __future__ import annotations

from qgis.core import QgsMapLayerProxyModel
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import QCheckBox, QLabel, QPushButton, QSpinBox

from ..job_builder import (
    CORRIDOR_NOTE,
    LOCAL_STEPS,
    MESH_COARSE,
    MESH_ENABLED,
    MESH_FINE_AREA,
    MESH_MID_AREA,
    SPEED_NOTE,
    STRIPS_ENABLED,
    STRIPS_LAYER_M,
    STRIPS_ROWS,
    ZONE_DX_FIELD,
    layer_features,
)
from ..suggest_lines import suggest_breaklines
from .common import Section, bind, field_combo, layer_combo, number_box
from .mesh_lines import LineTable


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
        self.lines = LineTable(self.canvas)
        self._finest = 0.0
        self.local_steps = QCheckBox("Each tile takes the step it can afford")
        self.speed_note = QLabel(SPEED_NOTE)
        self.speed_note.setWordWrap(True)
        self.preview_button = QPushButton("Preview tile sizes")
        self.suggest_button = QPushButton("Suggest breaklines")
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        self.summary.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.form.addRow(self.enabled)
        self.form.addRow("Coarsest cell, m", self.coarse)
        self.form.addRow("Finest cell for wadis over, km2", self.fine_area)
        self.form.addRow("One step coarser for wadis over, km2", self.mid_area)
        self.form.addRow("Refinement zones", self.zones)
        self.form.addRow("Zone cell size field, m", self.zone_dx)
        self.form.addRow("Refinement lines", self.lines.layer)
        self.form.addRow(self.lines.table)
        self.form.addRow(self.lines.rounded)
        self.form.addRow(self.lines.note)
        self.form.addRow("Local time stepping", self.local_steps)
        self.form.addRow(self.speed_note)
        self.form.addRow(self.preview_button)
        self.form.addRow(self.summary)
        self.form.addRow(self.suggest_button)
        self.corridors = QCheckBox("Corridors of cells aligned with the suggested banks")
        self.corridor_layer = layer_combo(QgsMapLayerProxyModel.LineLayer, "Choose the Suggested breaklines layer")
        self.corridor_layer_m = number_box(1)
        self.corridor_rows = QSpinBox()
        self.corridor_rows.setRange(1, 8)
        self.corridor_note = QLabel(CORRIDOR_NOTE)
        self.corridor_note.setWordWrap(True)
        self.form.addRow(self.corridors)
        self.form.addRow("Suggested breaklines", self.corridor_layer)
        self.form.addRow("Row spacing across, m", self.corridor_layer_m)
        self.form.addRow("Rows either side", self.corridor_rows)
        self.form.addRow(self.corridor_note)
        self.suggest_button.clicked.connect(lambda: suggest_breaklines(self))
        self.enabled.toggled.connect(self._enabled_changed)
        self.corridors.toggled.connect(self._corridors_changed)
        self.coarse.valueChanged.connect(self._sizes_changed)
        self._enabled_changed(False)
        self._corridors_changed(False)

    def _corridors_changed(self, on: bool) -> None:
        for widget in (self.corridor_layer, self.corridor_layer_m, self.corridor_rows):
            widget.setEnabled(on)

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
        self.lines.set_enabled(on)
        if on:
            self.local_steps.setChecked(True)

    def set_finest(self, dx: float) -> None:
        """The finest cell, which the Terrain section owns; the dock passes it down."""
        self._finest = dx
        self._sizes_changed()

    def _sizes_changed(self, *_) -> None:
        self.lines.set_sizes(self._finest, self.coarse.value())

    def apply_schema(self, schema) -> None:
        self.enabled.setChecked(bool(schema.default(MESH_ENABLED, False)))
        self.enabled.setToolTip(schema.tip(MESH_ENABLED))
        self.local_steps.setChecked(bool(schema.default(LOCAL_STEPS, False)))
        self.local_steps.setToolTip(schema.tip(LOCAL_STEPS))
        bind(self.coarse, schema, MESH_COARSE)
        bind(self.fine_area, schema, MESH_FINE_AREA)
        bind(self.mid_area, schema, MESH_MID_AREA)
        self.lines.apply_schema(schema)
        self.corridors.setChecked(bool(schema.default(STRIPS_ENABLED, False)))
        self.corridors.setToolTip(schema.tip(STRIPS_ENABLED))
        bind(self.corridor_layer_m, schema, STRIPS_LAYER_M)
        self.corridor_rows.setValue(int(schema.default(STRIPS_ROWS, 3)))
        self.corridor_rows.setToolTip(schema.tip(STRIPS_ROWS))

    def corridor_values(self) -> dict | None:
        """What the corridors need, or None when they are off; the banks file is the chosen layer's."""
        if not self.corridors.isChecked():
            return None
        layer = self.corridor_layer.currentLayer()
        source = layer.source().split("|")[0] if layer is not None else ""
        return {"banks": source, "layer_m": self.corridor_layer_m.value(), "rows_per_side": self.corridor_rows.value()}

    def values(self, crs) -> dict:
        out: dict = {"local_steps": self.local_steps.isChecked()}
        strips = self.corridor_values()
        if strips is not None:
            out["strips"] = strips
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
            "lines": self.lines.features(crs),
        }
        return out
