# Wadi2D QGIS plugin. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""2. Mesh, one section for every type with a 2D part (W101 item 4, W94's "Mesh section of the redesign").

The mesh kind first: squares, the quadtree, or the aligned centre mesh. Each kind shows its own sizes; the banks and the
floor of a wadi, Suggest breaklines and Build mesh serve them all; Advanced holds the Suggest thresholds, the corridor
sizes of the older generator, the gorge rows and local time stepping (shown with the quadtree, or wherever it is on).

The kind is not saved: it is read from the two ticks a saved model has always held (``enabled`` for the quadtree,
``corridors`` for the aligned cells), kept here hidden, so a model of the older dock opens on its own kind and writes the
job it wrote (``mesh_kinds``).
"""

from __future__ import annotations

from qgis.core import QgsMapLayerProxyModel
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import QCheckBox, QComboBox, QFormLayout, QGroupBox, QLabel, QPushButton, QSpinBox

from .. import section_status
from ..job_builder import (
    BREAK_CAP,
    BREAK_CREST,
    BREAK_DEPTH,
    BREAK_DISC,
    BREAK_OFFSET,
    BREAK_REACH,
    BREAK_RISE,
    BREAK_SCARP,
    BREAK_SLOPE,
    BREAK_SLOPE_CAP,
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
    STRIPS_GORGE,
    STRIPS_OUTSIDE,
    ZONE_DX_FIELD,
    layer_features,
    raster_path,
)
from ..mesh_kinds import ALIGNED, KIND_NOTES, KIND_WORDS, QUADTREE, kind_of, switches
from ..mesh_rows import LineRow
from ..suggest_lines import suggest_breaklines
from .common import Section, bind, field_combo, layer_combo, number_box
from .fold import Fold, show_row
from .mesh_lines import LineTable

GENERATOR_WORDS = {
    "rings": "Rows along each bank pair (W45)",
    "centres": "The aligned centre mesh: cells from their centres along the streams (W46)",
}
"""The engine's ``strips.generator`` choices, rings its default."""
SUGGEST_NOTE = (
    "Suggest breaklines reads the ground: the streams draining more than the area given, a bank where it rises the given "
    "height over the bed of a defined wadi, or, with a run's depth map, the edge of the flooded course; crests (roads, "
    "dykes, dams) by the top-hat. On Bidah 2 m of rise is the lip of the active channel, where the 0.5 m depth margin of "
    "the 100-yr flood lies; the 0.2 m margin is about 8 m further out. High ground drawn by hand goes in Structures."
)
FLOOR_NOTE = (
    "The floor of a wadi, which the aligned cells fill and Suggest's banks edge: going out from the stream, the first "
    "scarp of the given rise within 10 m, else the ground the given height above the bed, ended sooner where the ground "
    "climbs steeper than the slope (his rules of 2026-11-08)."
)
STREAMS_TIP = (
    "The streams Suggest breaklines draws and the aligned cells follow drain more than this "
    "(mesh.stream_area_mid_km2, the quadtree's second area)."
)


class MeshSection(Section):
    heading = "2. Mesh"
    start_collapsed = True
    key = "mesh"
    state_rows = (("lines", LineRow, "_fill"),)
    state_skip = ("kind",)
    """The kind is read from the two ticks the model holds."""

    def build(self) -> None:
        self._syncing = False
        self._finest = 0.0
        self._defaults: dict = {}
        self.kind = QComboBox()
        for key, words in KIND_WORDS.items():
            self.kind.addItem(words, key)
        self.kind_note = QLabel()
        self.kind_note.setWordWrap(True)
        self.form.addRow("Mesh kind", self.kind)
        self.form.addRow(self.kind_note)
        # the two ticks a saved model holds: hidden, set by the kind (the order of old models kept: these first)
        self.enabled = QCheckBox("Refine where the ground changes; the cell size above is the finest")
        self.corridors = QCheckBox("Corridors of cells aligned with the suggested banks")
        for tick in (self.enabled, self.corridors):
            self.form.addRow(tick)
            tick.hide()

        self.quad_box = QGroupBox("Quadtree")
        quad = QFormLayout(self.quad_box)
        quad.setRowWrapPolicy(QFormLayout.WrapLongRows)
        self.coarse = number_box(2)
        self.fine_area = number_box(2)
        self.mid_area = number_box(2)
        self.zones = layer_combo(QgsMapLayerProxyModel.PolygonLayer, "No refinement zones")
        self.zone_dx = field_combo(self.zones)
        self.lines = LineTable(self.canvas)
        quad.addRow("Coarsest cell, m", self.coarse)
        quad.addRow("Finest cell for wadis over, km2", self.fine_area)
        quad.addRow("One step coarser for wadis over, km2", self.mid_area)
        quad.addRow("Refinement zones", self.zones)
        quad.addRow("Zone cell size field, m", self.zone_dx)
        quad.addRow("Refinement lines", self.lines.layer)
        quad.addRow(self.lines.table)
        quad.addRow(self.lines.rounded)
        quad.addRow(self.lines.note)
        self.form.addRow(self.quad_box)

        self.aligned_box = QGroupBox("Aligned centre mesh")
        aligned = QFormLayout(self.aligned_box)
        aligned.setRowWrapPolicy(QFormLayout.WrapLongRows)
        self.corridor_layer = layer_combo(QgsMapLayerProxyModel.LineLayer, "Choose the Suggested breaklines layer")
        self.across_note = QLabel()
        self.across_note.setWordWrap(True)
        aligned.addRow("Streams and banks (Suggest's layer)", self.corridor_layer)
        aligned.addRow(self.across_note)
        self.form.addRow(self.aligned_box)

        self.lines_box = QGroupBox("Streams, banks and high ground: Suggest breaklines")
        lines = QFormLayout(self.lines_box)
        lines.setRowWrapPolicy(QFormLayout.WrapLongRows)
        self.stream_area = number_box(2)
        self.stream_area.setToolTip(STREAMS_TIP)
        self.bank_rise = number_box(1)
        self.bank_scarp = number_box(1)
        self.bank_slope = number_box(3)
        self.bank_slope_cap = QCheckBox("The floor ends where the ground climbs steeper than the slope")
        self.floor_note = QLabel(FLOOR_NOTE)
        self.floor_note.setWordWrap(True)
        self.suggest_button = QPushButton("Suggest breaklines")
        self.suggest_note = QLabel(SUGGEST_NOTE)
        self.suggest_note.setWordWrap(True)
        lines.addRow("Streams draining over, km2", self.stream_area)
        lines.addRow("Bank where the ground rises, m", self.bank_rise)
        lines.addRow("Or a scarp of, m", self.bank_scarp)
        lines.addRow("Floor slope at most, m/m", self.bank_slope)
        lines.addRow(self.bank_slope_cap)
        lines.addRow(self.floor_note)
        lines.addRow(self.suggest_button)
        lines.addRow(self.suggest_note)
        self.form.addRow(self.lines_box)

        self.preview_button = QPushButton("Build mesh")
        self.preview_button.setToolTip(
            "Builds the cells a run would step, as the run builds them, and draws them under the model's Inputs > Mesh; "
            "no tables, no water. The engine's refusals come back in its words."
        )
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        self.summary.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.form.addRow(self.preview_button)
        self.form.addRow(self.summary)

        self.advanced = Fold("Advanced")
        more = self.advanced.form
        self.bank_reach = number_box(0)
        self.bank_depth_layer = layer_combo(QgsMapLayerProxyModel.RasterLayer, "The ground alone, no run's depth map")
        self.bank_depth = number_box(2)
        self.bank_offset = number_box(1)
        self.crest_height = number_box(2)
        self.crest_disc = number_box(0)
        self.crest_slope = number_box(2)
        more.addRow("Look for a bank within, m", self.bank_reach)
        more.addRow("Banks from a run's depth map", self.bank_depth_layer)
        more.addRow("Flooded course deeper than, m", self.bank_depth)
        more.addRow("Bank at least this many cells off the thalweg", self.bank_offset)
        more.addRow("Crest higher than its ground, m", self.crest_height)
        more.addRow("Crest narrower than twice, m", self.crest_disc)
        more.addRow("Crests on ground flatter than, m/m", self.crest_slope)
        self.corridor_generator = QComboBox()
        for key, words in GENERATOR_WORDS.items():
            self.corridor_generator.addItem(words, key)
        self.corridor_cell_min = number_box(0)
        self.corridor_cell_max = number_box(0)
        self.corridor_fraction = number_box(2)
        self.corridor_outside = QSpinBox()
        self.corridor_outside.setRange(1, 4)
        self.corridor_note = QLabel(CORRIDOR_NOTE)
        self.corridor_note.setWordWrap(True)
        self.gorge_rows = QSpinBox()
        self.gorge_rows.setRange(0, 12)
        self.gorge_rows.setSingleStep(2)
        self.gorge_rows.setSpecialValueText("None: the pair as it is")
        more.addRow("Aligned cells made by", self.corridor_generator)
        more.addRow("Rows across a narrow gorge", self.gorge_rows)
        more.addRow("Smallest cell across, m", self.corridor_cell_min)
        more.addRow("Largest cell across, m", self.corridor_cell_max)
        more.addRow("Cell across, share of the width", self.corridor_fraction)
        more.addRow("Rows beyond each bank", self.corridor_outside)
        more.addRow(self.corridor_note)
        self.local_steps = QCheckBox("Each tile takes the step it can afford")
        self.speed_note = QLabel(SPEED_NOTE)
        self.speed_note.setWordWrap(True)
        more.addRow("Local time stepping", self.local_steps)
        more.addRow(self.speed_note)
        self.form.addRow(self.advanced)

        self.suggest_button.clicked.connect(lambda: suggest_breaklines(self))
        self.kind.activated.connect(lambda _index: self.set_kind(self.kind.currentData()))
        self.enabled.toggled.connect(self._switches_changed)
        self.corridors.toggled.connect(self._switches_changed)
        self.enabled.toggled.connect(self._enabled_changed)
        self.corridors.toggled.connect(self._corridors_changed)
        self.corridor_generator.currentIndexChanged.connect(self._shown)
        self.local_steps.toggled.connect(self._shown)
        self.coarse.valueChanged.connect(self._sizes_changed)
        self._enabled_changed(False)
        self._corridors_changed(False)
        self._switches_changed()

    # The kind.

    def current_kind(self) -> str:
        return kind_of(self.enabled.isChecked(), self.corridors.isChecked())

    def set_kind(self, kind: str) -> None:
        """What a user's choice does: the two ticks set, and the aligned mesh made from centres, the four Block 2 runs'
        construction (an older model's rings stay until the kind is chosen again). Local time stepping goes with the
        quadtree, on with it and off without it (W10: no gain on a uniform grid); Advanced still sets it either way."""
        quadtree, corridors = switches(kind)
        self._syncing = True
        try:
            self.corridors.setChecked(corridors)
            self.enabled.setChecked(quadtree)
            self.local_steps.setChecked(quadtree)
            if kind == ALIGNED:
                self.corridor_generator.setCurrentIndex(self.corridor_generator.findData("centres"))
        finally:
            self._syncing = False
        self._switches_changed()

    def _switches_changed(self, *_) -> None:
        kind = self.current_kind()
        self.kind.blockSignals(True)
        self.kind.setCurrentIndex(self.kind.findData(kind))
        self.kind.blockSignals(False)
        if not self._syncing:
            self._shown()

    def _enabled_changed(self, on: bool) -> None:
        for widget in (self.coarse, self.fine_area, self.mid_area, self.zones, self.zone_dx):
            widget.setEnabled(on)
        self.lines.set_enabled(on)
        if on:
            self.local_steps.setChecked(True)

    def _corridors_changed(self, on: bool) -> None:
        for widget in (
            self.corridor_layer, self.corridor_generator, self.corridor_cell_min, self.corridor_cell_max,
            self.corridor_fraction, self.corridor_outside, self.gorge_rows,
        ):  # fmt: skip
            widget.setEnabled(on)

    def _shown(self, *_) -> None:
        kind = self.current_kind()
        self.kind_note.setText(KIND_NOTES[kind])
        self.quad_box.setVisible(kind == QUADTREE)
        self.aligned_box.setVisible(kind == ALIGNED)
        more = self.advanced.form
        rings = self.corridor_generator.currentData() == "rings"
        show_row(more, self.corridor_generator, kind == ALIGNED)
        show_row(more, self.gorge_rows, kind == ALIGNED and not rings)
        for widget in (self.corridor_cell_min, self.corridor_cell_max, self.corridor_fraction, self.corridor_outside):
            show_row(more, widget, kind == ALIGNED and rings)
        self.corridor_note.setVisible(kind == ALIGNED and rings)
        steps = kind == QUADTREE or self.local_steps.isChecked()  # never on unseen
        show_row(more, self.local_steps, steps)
        self.speed_note.setVisible(steps)
        show_row(self.lines_box.layout(), self.stream_area, kind != QUADTREE)
        self._across()

    def set_finest(self, dx: float) -> None:
        """The finest cell, which the Terrain section owns; the dock passes it down."""
        self._finest = dx
        self._sizes_changed()
        self._across()

    def _across(self) -> None:
        size = f"{self._finest:g} m" if self._finest else "Terrain's cell size"
        self.across_note.setText(
            f"Cells across the streams: {size} (Terrain's cell size), the same along them; the rows repeat out to the "
            "floor's edge, so a cell never stretches."
        )

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
        bind(self.stream_area, schema, MESH_MID_AREA)
        self.stream_area.setToolTip(STREAMS_TIP)
        self.lines.apply_schema(schema)
        self.corridors.setChecked(bool(schema.default(STRIPS_ENABLED, False)))
        self.corridors.setToolTip(schema.tip(STRIPS_ENABLED))
        bind(self.corridor_cell_min, schema, STRIPS_CELL_MIN)
        bind(self.corridor_cell_max, schema, STRIPS_CELL_MAX)
        bind(self.corridor_fraction, schema, STRIPS_FRACTION)
        self.corridor_outside.setValue(int(schema.default(STRIPS_OUTSIDE, 1)))
        self.corridor_outside.setToolTip(schema.tip(STRIPS_OUTSIDE))
        self.gorge_rows.setValue(int(schema.default(STRIPS_GORGE, 0)))
        self.gorge_rows.setToolTip(schema.tip(STRIPS_GORGE))
        bind(self.bank_rise, schema, BREAK_RISE)
        bind(self.bank_scarp, schema, BREAK_SCARP)
        bind(self.bank_slope, schema, BREAK_SLOPE_CAP)
        self.bank_slope_cap.setChecked(bool(schema.default(BREAK_CAP, True)))
        self.bank_slope_cap.setToolTip(schema.tip(BREAK_CAP))
        bind(self.bank_reach, schema, BREAK_REACH)
        bind(self.bank_depth, schema, BREAK_DEPTH)
        bind(self.bank_offset, schema, BREAK_OFFSET)
        bind(self.crest_height, schema, BREAK_CREST)
        bind(self.crest_disc, schema, BREAK_DISC)
        bind(self.crest_slope, schema, BREAK_SLOPE)
        self._defaults = {
            "stream_km2": schema.default(MESH_MID_AREA), "bank_scarp_m": schema.default(BREAK_SCARP),
            "bank_slope": schema.default(BREAK_SLOPE_CAP), "bank_slope_cap": schema.default(BREAK_CAP, True),
        }  # fmt: skip
        self._shown()

    def standing(self, kind=None):
        banks = self.corridor_layer.currentLayer()
        return section_status.mesh(
            self.enabled.isChecked(), self.coarse.value(), len(self.lines.rows), self.corridors.isChecked(),
            banks.name() if banks is not None else None, self.corridor_generator.currentData() == "centres",
        )  # fmt: skip

    def _changed(self, key: str, value) -> bool:
        """A setting written only off the engine's default, so a model of the older dock writes the job it wrote."""
        default = self._defaults.get(key)
        if isinstance(value, bool) or default is None:
            return value != default
        return abs(float(value) - float(default)) > 1e-9

    def breakline_values(self) -> dict:
        """The Suggest settings for the job's ``breaklines`` section; the depth map is the chosen raster's file. The
        floor's scarp and slope only where they differ from the engine's (W101)."""
        out = {
            "bank_rise_m": self.bank_rise.value(),
            "bank_reach_m": self.bank_reach.value(),
            "bank_depth_m": self.bank_depth.value(),
            "bank_offset_cells": self.bank_offset.value(),
            "crest_height_m": self.crest_height.value(),
            "disc_radius_m": self.crest_disc.value(),
            "ground_slope_max": self.crest_slope.value(),
        }
        for key, value in (
            ("bank_scarp_m", self.bank_scarp.value()),
            ("bank_slope", self.bank_slope.value()),
            ("bank_slope_cap", self.bank_slope_cap.isChecked()),
        ):
            if self._changed(key, value):
                out[key] = value
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
        out = {
            "banks": source,
            "generator": self.corridor_generator.currentData(),
            "cell_min_m": self.corridor_cell_min.value(),
            "cell_max_m": self.corridor_cell_max.value(),
            "width_fraction": self.corridor_fraction.value(),
            "rows_outside": self.corridor_outside.value(),
        }
        if self.corridor_generator.currentData() == "centres" and self.gorge_rows.value() > 0:
            out["gorge_rows"] = self.gorge_rows.value()
        return out

    def values(self, crs) -> dict:
        out: dict = {"local_steps": self.local_steps.isChecked(), "breaklines": self.breakline_values()}
        strips = self.corridor_values()
        if strips is not None:
            out["strips"] = strips
        if not self.enabled.isChecked():
            if self._changed("stream_km2", self.stream_area.value()):  # Suggest's streams, without the quadtree
                out["stream_km2"] = self.stream_area.value()
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


__all__ = ["GENERATOR_WORDS", "MeshSection"]
