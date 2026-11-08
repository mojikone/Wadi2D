# Wadi2D QGIS plugin. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""2. Mesh: cell sizes, refinement zones and lines, the preview of tile sizes, and local time stepping."""

from __future__ import annotations

from qgis.core import QgsMapLayerProxyModel
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import QCheckBox, QLabel, QPushButton, QSpinBox

from ..job_builder import (
    BREAK_CREST,
    BREAK_DEPTH,
    BREAK_DISC,
    BREAK_OFFSET,
    BREAK_REACH,
    BREAK_RISE,
    BREAK_SLOPE,
    CORRIDOR_NOTE,
    LOCAL_STEPS,
    MESH_COARSE,
    MESH_ENABLED,
    MESH_FINE_AREA,
    MESH_MID_AREA,
    SPEED_NOTE,
    STRIPS_CELL_MAX,
    STRIPS_CELL_MIN,
    STRIPS_ENABLED,
    STRIPS_FRACTION,
    STRIPS_OUTSIDE,
    ZONE_DX_FIELD,
    layer_features,
    raster_path,
)

SUGGEST_NOTE = (
    "Suggest breaklines reads the ground: a bank where it rises the given height over the bed of a defined wadi, or, "
    "with a run's depth map, the edge of the flooded course; crests by the top-hat. On Bidah 2 m of rise is the lip of "
    "the active channel, where the 0.5 m depth margin of the 100-yr flood lies; the 0.2 m margin is about 8 m further out."
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
        self.bank_rise = number_box(1)
        self.bank_reach = number_box(0)
        self.bank_depth_layer = layer_combo(QgsMapLayerProxyModel.RasterLayer, "The ground alone, no run's depth map")
        self.bank_depth = number_box(2)
        self.bank_offset = number_box(1)
        self.crest_height = number_box(2)
        self.crest_disc = number_box(0)
        self.crest_slope = number_box(2)
        self.suggest_note = QLabel(SUGGEST_NOTE)
        self.suggest_note.setWordWrap(True)
        self.form.addRow(self.suggest_button)
        self.form.addRow("Bank where the ground rises, m", self.bank_rise)
        self.form.addRow("Look for a bank within, m", self.bank_reach)
        self.form.addRow("Banks from a run's depth map", self.bank_depth_layer)
        self.form.addRow("Flooded course deeper than, m", self.bank_depth)
        self.form.addRow("Bank at least this many cells off the thalweg", self.bank_offset)
        self.form.addRow("Crest higher than its ground, m", self.crest_height)
        self.form.addRow("Crest narrower than twice, m", self.crest_disc)
        self.form.addRow("Crests on ground flatter than, m/m", self.crest_slope)
        self.form.addRow(self.suggest_note)
        self.corridors = QCheckBox("Corridors of cells aligned with the suggested banks")
        self.corridor_layer = layer_combo(QgsMapLayerProxyModel.LineLayer, "Choose the Suggested breaklines layer")
        self.corridor_cell_min = number_box(0)
        self.corridor_cell_max = number_box(0)
        self.corridor_fraction = number_box(2)
        self.corridor_outside = QSpinBox()
        self.corridor_outside.setRange(1, 4)
        self.corridor_note = QLabel(CORRIDOR_NOTE)
        self.corridor_note.setWordWrap(True)
        self.form.addRow(self.corridors)
        self.form.addRow("Suggested breaklines", self.corridor_layer)
        self.form.addRow("Smallest cell across, m", self.corridor_cell_min)
        self.form.addRow("Largest cell across, m", self.corridor_cell_max)
        self.form.addRow("Cell across, share of the width", self.corridor_fraction)
        self.form.addRow("Rows beyond each bank", self.corridor_outside)
        self.form.addRow(self.corridor_note)
        self.suggest_button.clicked.connect(lambda: suggest_breaklines(self))
        self.enabled.toggled.connect(self._enabled_changed)
        self.corridors.toggled.connect(self._corridors_changed)
        self.coarse.valueChanged.connect(self._sizes_changed)
        self._enabled_changed(False)
        self._corridors_changed(False)

    def _corridors_changed(self, on: bool) -> None:
        for widget in (
            self.corridor_layer,
            self.corridor_cell_min,
            self.corridor_cell_max,
            self.corridor_fraction,
            self.corridor_outside,
        ):
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
        bind(self.corridor_cell_min, schema, STRIPS_CELL_MIN)
        bind(self.corridor_cell_max, schema, STRIPS_CELL_MAX)
        bind(self.corridor_fraction, schema, STRIPS_FRACTION)
        self.corridor_outside.setValue(int(schema.default(STRIPS_OUTSIDE, 1)))
        self.corridor_outside.setToolTip(schema.tip(STRIPS_OUTSIDE))
        bind(self.bank_rise, schema, BREAK_RISE)
        bind(self.bank_reach, schema, BREAK_REACH)
        bind(self.bank_depth, schema, BREAK_DEPTH)
        bind(self.bank_offset, schema, BREAK_OFFSET)
        bind(self.crest_height, schema, BREAK_CREST)
        bind(self.crest_disc, schema, BREAK_DISC)
        bind(self.crest_slope, schema, BREAK_SLOPE)

    def breakline_values(self) -> dict:
        """The Suggest settings for the job's ``breaklines`` section; the depth map is the chosen raster's file."""
        out = {
            "bank_rise_m": self.bank_rise.value(),
            "bank_reach_m": self.bank_reach.value(),
            "bank_depth_m": self.bank_depth.value(),
            "bank_offset_cells": self.bank_offset.value(),
            "crest_height_m": self.crest_height.value(),
            "disc_radius_m": self.crest_disc.value(),
            "ground_slope_max": self.crest_slope.value(),
        }
        layer = self.bank_depth_layer.currentLayer()
        if layer is not None:
            path = raster_path(layer)
            out["bank_depth_map"] = path
            out["depth_map_unset"] = path is None
        return out

    def corridor_values(self) -> dict | None:
        """What the corridors need, or None when they are off; the banks file is the chosen layer's."""
        if not self.corridors.isChecked():
            return None
        layer = self.corridor_layer.currentLayer()
        source = layer.source().split("|")[0] if layer is not None else ""
        return {
            "banks": source,
            "cell_min_m": self.corridor_cell_min.value(),
            "cell_max_m": self.corridor_cell_max.value(),
            "width_fraction": self.corridor_fraction.value(),
            "rows_outside": self.corridor_outside.value(),
        }

    def values(self, crs) -> dict:
        out: dict = {"local_steps": self.local_steps.isChecked(), "breaklines": self.breakline_values()}
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
