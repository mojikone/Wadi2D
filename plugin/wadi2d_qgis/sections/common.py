# Wadi2D QGIS plugin. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""What every section shares: the collapsible box, layer pickers, number boxes bound to the engine's schema."""

from __future__ import annotations

from qgis.core import QgsMapLayerProxyModel
from qgis.gui import QgsCollapsibleGroupBox, QgsFieldComboBox, QgsMapLayerComboBox
from qgis.PyQt.QtWidgets import QDoubleSpinBox, QFormLayout, QVBoxLayout, QWidget

from ..job_builder import SchemaView, raster_path
from ..section_status import OPTIONAL, Status
from ..widget_state import NOTE, inputs, read, read_rows, resolve, write, write_rows

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

    # The saved model (W99): what the section's inputs hold, as JSON, and back. A section lists nothing: its input
    # widgets are found by walking its attributes. It names only what the walk cannot know.

    key = ""
    """The section's name in a saved model; never changed once a model has been saved with it."""
    state_skip: tuple[str, ...] = ()
    """Attribute paths left out of the saved model: another section's widgets, display settings kept elsewhere."""
    state_hold: tuple[str, ...] = ()
    """Paths of lists the engine fills after the section is restored: the saved choice waits in the empty list."""
    state_rows: tuple[tuple[str, type, str], ...] = ()
    """Tables of dataclass rows: (path of the object that holds ``rows``, the row class, its method that redraws)."""

    def state(self) -> dict:
        found = {"widgets": {path: read(widget) for path, widget in inputs(self, self.state_skip)}, "rows": {}}
        for path, _row_class, _redraw in self.state_rows:
            found["rows"][path] = read_rows(resolve(self, path).rows)
        extra = self.extra_state()
        if extra:
            found["extra"] = extra
        return found

    def restore(self, state: dict, add_missing: bool = False) -> list[str]:
        """Set the inputs from a saved state; what could not be set, in words, and what was added to the project,
        each of those marked with ``NOTE``. Set twice: a choice set in the first pass can refill a list a later widget
        chooses from, and can move a widget that was already set."""
        saved = state.get("widgets", {})
        news: list[str] = []
        failed: dict[str, str] = {}
        for last in (False, True):
            for path, widget in inputs(self, self.state_skip):
                if path not in saved:
                    continue
                text = write(widget, saved[path], add_missing, path in self.state_hold)
                if text.startswith(NOTE):
                    news.append(text[len(NOTE) :])
                elif last and text:
                    failed[path] = text
        for path, row_class, redraw in self.state_rows:
            if path in state.get("rows", {}):
                holder = resolve(self, path)
                holder.rows = write_rows(row_class, state["rows"][path])
                getattr(holder, redraw)()
        found = [f"{NOTE}{text}" for text in news] + [f"{path}: {text}" for path, text in failed.items()]
        return found + list(self.restore_extra(state.get("extra") or {}, add_missing))

    def extra_state(self) -> dict:
        """What neither the walk nor ``state_rows`` reaches."""
        return {}

    def set_model_type(self, kind: str | None) -> None:
        """Show what a model of this type leaves to choose in the section; None is no type, everything."""

    def standing(self, kind: str | None = None) -> Status:
        """Where the section stands for a model of this type, from its own widgets alone: Ready, Optional or Missing,
        and one line of words (``section_status``). No layer is read feature by feature here. Not named ``status``:
        Run and the depth-area study each have a label of that name, which the dock and older checks write to."""
        return Status(OPTIONAL, "")

    def restore_extra(self, extra: dict, add_missing: bool = False) -> list[str]:
        return []


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
    """One number for the whole domain, or a raster instead.

    ``fills``: the number stays open beside a raster and stands where the raster has no value (its holes), as the
    engine reads a CN beside a CN grid (W106); the words are its empty text beside a raster, and choosing a raster
    empties the box, so a value is never carried over from before the raster without being typed again."""

    def __init__(self, decimals: int, empty: str, fills: str | None = None) -> None:
        super().__init__()
        self.box = number_box(decimals)
        self.raster = layer_combo(QgsMapLayerProxyModel.RasterLayer, empty)
        self.fills = fills
        self._alone_text = ""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.box)
        layout.addWidget(self.raster)
        if fills is None:
            self.raster.layerChanged.connect(lambda layer: self.box.setEnabled(layer is None))
        else:
            self.raster.layerChanged.connect(self._raster_changed)

    def set_alone_text(self, text: str) -> None:
        """The box's empty text with no raster; beside a raster it reads ``fills``."""
        self._alone_text = text
        self.box.setSpecialValueText(self.fills if self.fills and self.raster.currentLayer() else text)

    def _raster_changed(self, layer) -> None:
        self.box.setSpecialValueText(self.fills if layer is not None else self._alone_text)
        if layer is not None:
            self.box.setValue(self.box.minimum())

    def fill_value(self) -> float | None:
        """The number where the raster has none; None when the box is empty or no raster is chosen."""
        if self.fills is None or self.raster.currentLayer() is None or self.box.value() <= self.box.minimum():
            return None
        return self.box.value()

    def value(self) -> float:
        return self.box.value()

    def path(self) -> str | None:
        return raster_path(self.raster.currentLayer())
