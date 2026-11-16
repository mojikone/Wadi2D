# Wadi2D QGIS plugin. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""1. Terrain: the DEM, the cell size, the domain (drawn, or completed from a rough outline), the roughness."""

from __future__ import annotations

from qgis.core import QgsMapLayerProxyModel, QgsProject
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QWidget,
)

from .. import section_status
from ..dem_choice import default_dem
from ..job_builder import DX, FILL_PITS, MANNING, PREFERRED_DX, layer_features, map_extent, raster_path
from ..land_rows import GRID, LAND, LAND_COLUMNS, ONE, ROUGH_WORDS, SPLIT
from ..model_types import LUMPED
from .class_table import ClassTable
from .common import Section, ValueOrRaster, bind, layer_combo, number_box

OUTLINE_NOTE = (
    "Draw a rough outline: Complete upstream adds every catchment draining into it, read on this DEM with the generated "
    "basin's pixel and stream threshold, and keeps as drawn the edges along the boundary lines and the layer above; "
    "Align to catchments snaps the outline's edge to catchment polygons, a band narrower than 200 m removed or added. "
    "Either loads the result as the Domain above (W97)."
)


class TerrainSection(Section):
    heading = "1. Terrain"
    key = "terrain"

    def build(self) -> None:
        self.dem = layer_combo(QgsMapLayerProxyModel.RasterLayer, "Choose the DEM")  # W101: never a run's raster
        self.dx = number_box(2)
        self.domain = layer_combo(QgsMapLayerProxyModel.PolygonLayer, "Current map extent")
        self.manning_form = QComboBox()  # W101 item 2: Manning in its four forms (W96's terrain.roughness)
        for key, words in ROUGH_WORDS.items():
            self.manning_form.addItem(words, key)
        self.manning = ValueOrRaster(3, "Same value everywhere")
        self.manning_aligned = number_box(3)
        self.manning_aligned.setRange(0.008, 0.5)
        self.manning_aligned.setValue(0.04)
        self.manning_aligned.setToolTip("Manning n of the aligned cells along the streams; the squares take the value above")
        self.rough_landuse = layer_combo(QgsMapLayerProxyModel.RasterLayer, "Choose the land-use raster")
        self.rough_classes = ClassTable(*LAND_COLUMNS)
        self.rough_classes.setToolTip("Manning n of each class of the land-use raster; a class found and not listed stops the run")
        self.form.addRow("DEM", self.dem)
        self.form.addRow("Cell size, m", self.dx)
        self.form.addRow("Domain", self.domain)
        self.outline_box = QGroupBox("Domain from an outline")  # W101 item 5: wadi2d domain (W97)
        outline = QFormLayout(self.outline_box)
        outline.setRowWrapPolicy(QFormLayout.WrapLongRows)
        self.outline = layer_combo(QgsMapLayerProxyModel.PolygonLayer, "Choose a rough outline")
        self.outline_keep = layer_combo(QgsMapLayerProxyModel.LineLayer, "The boundary lines alone")
        self.outline_catchments = layer_combo(QgsMapLayerProxyModel.PolygonLayer, "Choose the catchments")
        self.complete_button = QPushButton("Complete upstream")
        self.align_button = QPushButton("Align to catchments")
        buttons = QWidget()
        row = QHBoxLayout(buttons)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(self.complete_button)
        row.addWidget(self.align_button)
        self.outline_words = QLabel(OUTLINE_NOTE)
        self.outline_words.setWordWrap(True)
        self.outline_words.setTextInteractionFlags(Qt.TextSelectableByMouse)
        outline.addRow("Rough outline", self.outline)
        outline.addRow("Edges kept as drawn, beside the boundary lines", self.outline_keep)
        outline.addRow("Catchments to align to", self.outline_catchments)
        outline.addRow(buttons)
        outline.addRow(self.outline_words)
        self.form.addRow(self.outline_box)
        self.form.addRow("Manning given as", self.manning_form)
        self.form.addRow("Manning n", self.manning)
        self.form.addRow("Manning n, aligned cells", self.manning_aligned)
        self.form.addRow("Land-use raster", self.rough_landuse)
        self.form.addRow(self.rough_classes)
        self.manning_form.currentIndexChanged.connect(self._manning_shown)
        self.manning.raster.layerChanged.connect(self._manning_raster_chosen)
        self._lumped = False
        self._manning_shown()
        self.fill_pits = QCheckBox("Fill pits: small deep holes of the terrain, to their spill level")
        self.form.addRow(self.fill_pits)
        self.dem.layerChanged.connect(self._dem_changed)
        self.choose_default_dem()
        self._dem_changed(self.dem.currentLayer())

    def choose_default_dem(self) -> None:
        """The DEM a run in the project was made on, or none: a layer picker would take the first raster, which in a
        project of results is a depth map (his fault of 2026-11-16)."""
        self.dem.setLayer(default_dem(QgsProject.instance()))

    def _row(self, widget, on: bool) -> None:
        widget.setVisible(on)
        label = self.form.labelForField(widget)
        if label is not None:
            label.setVisible(on)

    def _manning_shown(self, *_) -> None:
        """Only the chosen form's fields; one value takes no raster, a grid its raster, the land use its table."""
        form = self.manning_form.currentData()
        shown = not self._lumped
        self.manning.raster.setVisible(form == GRID)
        if form == ONE and self.manning.raster.currentLayer() is not None:
            self.manning.raster.setLayer(None)
        self.manning.box.setEnabled(form != GRID or self.manning.raster.currentLayer() is None)
        self._row(self.manning_form, shown)
        self._row(self.manning, shown)
        self._row(self.manning_aligned, shown and form == SPLIT)
        self._row(self.rough_landuse, shown and form == LAND)
        self.rough_classes.setVisible(shown and form == LAND)

    def _manning_raster_chosen(self, layer) -> None:
        """A raster chosen, or brought back by a model from before the forms: the form is a grid."""
        if layer is not None and self.manning_form.currentData() == ONE:
            self.manning_form.setCurrentIndex(self.manning_form.findData(GRID))

    def roughness(self) -> dict:
        return {
            "form": self.manning_form.currentData(), "n": self.manning.value(), "n_aligned": self.manning_aligned.value(),
            "land_use": raster_path(self.rough_landuse.currentLayer()) or "", "classes": self.rough_classes.rows(),
        }  # fmt: skip

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
        self._lumped = lumped
        for widget in (self.dx, self.fill_pits):
            self._row(widget, not lumped)
        self.outline_box.setVisible(not lumped)  # a domain is for the 2D part (W101 item 5)
        self._manning_shown()

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
            self.roughness(),
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
            "manning_raster": self.manning.path() if self.manning_form.currentData() in (ONE, GRID) else None,
            "roughness": self.roughness(),
            "fill_pits": self.fill_pits.isChecked() and self.fill_pits.isEnabled(),
        }
        if domain is not None:
            values["domain"] = layer_features(domain, crs)
        else:
            values["extent"] = map_extent(self.canvas, crs, layer.extent())
        return values
