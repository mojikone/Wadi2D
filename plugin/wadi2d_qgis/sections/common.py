# Wadi2D QGIS plugin. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""What every section shares: the collapsible box, layer pickers, number boxes bound to the engine's schema."""

from __future__ import annotations

from qgis.core import QgsMapLayerProxyModel
from qgis.gui import QgsCollapsibleGroupBox, QgsFieldComboBox, QgsMapLayerComboBox
from qgis.PyQt.QtWidgets import QDoubleSpinBox, QFormLayout, QVBoxLayout, QWidget

from ..job_builder import SchemaView, raster_path

UNBOUNDED = 1e12


class Section(QgsCollapsibleGroupBox):
    """One step of the workflow. A section knows its widgets; it never knows another section."""

    heading = ""
    start_collapsed = False

    def __init__(self, canvas=None) -> None:
        super().__init__(self.heading)
        self.canvas = canvas
        self.setSaveCollapsedState(False)
        self.form = QFormLayout(self)
        self.form.setRowWrapPolicy(QFormLayout.WrapLongRows)
        self.build()
        self.setCollapsed(self.start_collapsed)

    def build(self) -> None:
        """Create the widgets."""

    def apply_schema(self, schema: SchemaView) -> None:
        """Take defaults, bounds and tooltips from the engine."""

    def values(self, crs) -> dict:
        """Plain values for the job builder; geometry comes back in ``crs``, the DEM's."""
        return {}


def layer_combo(filters, empty: str | None = None) -> QgsMapLayerComboBox:
    """A layer picker; ``empty`` names the "no layer" choice and makes it the starting one."""
    combo = QgsMapLayerComboBox()
    combo.setFilters(filters)
    if empty is not None:
        combo.setAllowEmptyLayer(True, empty)
        combo.setLayer(None)
    return combo


def field_combo(layer_picker: QgsMapLayerComboBox) -> QgsFieldComboBox:
    """A field picker that follows a layer picker; empty by default."""
    combo = QgsFieldComboBox()
    combo.setAllowEmptyFieldName(True)
    combo.setLayer(layer_picker.currentLayer())
    layer_picker.layerChanged.connect(combo.setLayer)
    return combo


def number_box(decimals: int) -> QDoubleSpinBox:
    box = QDoubleSpinBox()
    box.setDecimals(decimals)
    box.setRange(-UNBOUNDED, UNBOUNDED)
    return box


def bind(box: QDoubleSpinBox, schema: SchemaView, path: str, scale: float = 1.0, default=None) -> None:
    """Bounds, value and tooltip of a number box from the schema; ``scale`` converts to the box's unit."""
    low, high = schema.bounds(path)
    box.setRange(
        -UNBOUNDED if low is None else low * scale,
        UNBOUNDED if high is None else high * scale,
    )
    value = schema.default(path) if default is None else default
    if value is not None:
        box.setValue(value * scale)
    box.setToolTip(schema.tip(path))


class ValueOrRaster(QWidget):
    """One number for the whole domain, or a raster instead."""

    def __init__(self, decimals: int, empty: str) -> None:
        super().__init__()
        self.box = number_box(decimals)
        self.raster = layer_combo(QgsMapLayerProxyModel.RasterLayer, empty)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.box)
        layout.addWidget(self.raster)
        self.raster.layerChanged.connect(lambda layer: self.box.setEnabled(layer is None))

    def value(self) -> float:
        return self.box.value()

    def path(self) -> str | None:
        return raster_path(self.raster.currentLayer())
