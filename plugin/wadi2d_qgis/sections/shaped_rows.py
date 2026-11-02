# Wadi2D QGIS plugin. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""The fields of one kind of shaped object: a line layer, each value a number or a field, a section table, the ends."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from qgis.gui import QgsFileWidget
from qgis.PyQt.QtWidgets import QComboBox, QFormLayout, QHBoxLayout, QWidget

from ..job_builder import layer_features
from ..shaped import END_KEYS, LINING, OBJECT_PATH, OPENINGS, SECTION_PATH, TABLE, TOP
from .common import bind, field_combo, number_box

NUMBER_DECIMALS = 3
TABLE_FILTER = "Section table (*.csv);;All files (*)"
NO_LINING = "none"
FIELD, NUMBER = "field", "number"

COMMON_END = (("name", "Name field", FIELD),)
SIDE_SLOPES = (
    ("left_slope", "Left side slope, H:V", NUMBER),
    ("right_slope", "Right side slope, H:V", NUMBER),
)
ROWS = {
    "embankment": (
        "Embankments (dam, dyke)",
        (
            ("crest_z", "Crest elevation field", FIELD),
            ("width", "Crest width, m", NUMBER),
            *SIDE_SLOPES,
            (OPENINGS, "Openings field (120-180 left; 600-650)", FIELD),
            *COMMON_END,
        ),
    ),
    "channel": (
        "Channels (burned)",
        (
            ("crest_z", "Bed elevation field", FIELD),
            ("bed_start_z", "Bed at station 0 field", FIELD),
            ("bed_slope", "Bed slope field, fall per m", FIELD),
            ("width", "Bottom width, m", NUMBER),
            *SIDE_SLOPES,
            (LINING, "Lining Manning n", NUMBER),
            *COMMON_END,
        ),
    ),
    "channel_dyke": (
        "Channels with dykes",
        (
            ("crest_z", "Bed elevation field", FIELD),
            ("bed_start_z", "Bed at station 0 field", FIELD),
            ("bed_slope", "Bed slope field, fall per m", FIELD),
            (TOP, "Top field, both banks", FIELD),
            ("left_top_z", "Top field, left bank", FIELD),
            ("right_top_z", "Top field, right bank", FIELD),
            ("water_depth", "Water depth field", FIELD),
            ("freeboard", "Freeboard field", FIELD),
            ("width", "Bottom width, m", NUMBER),
            ("left_slope", "Left inner slope, H:V", NUMBER),
            ("right_slope", "Right inner slope, H:V", NUMBER),
            ("left_crest_width", "Left crest width, m", NUMBER),
            ("right_crest_width", "Right crest width, m", NUMBER),
            ("left_outer_slope", "Left outer slope, H:V", NUMBER),
            ("right_outer_slope", "Right outer slope, H:V", NUMBER),
            (LINING, "Lining Manning n", NUMBER),
            (OPENINGS, "Openings field (120-180 left; 600-650)", FIELD),
            *COMMON_END,
        ),
    ),
}


class NumberOrField(QWidget):
    """One number for every line of the layer, or a field that wins where it holds a value."""

    def __init__(self, layer_picker) -> None:
        super().__init__()
        self.box = number_box(NUMBER_DECIMALS)
        self.field = field_combo(layer_picker)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(self.box, 1)
        row.addWidget(self.field, 1)
        self.field.fieldChanged.connect(lambda name: self.box.setEnabled(not name))

    def setToolTip(self, text: str) -> None:
        self.box.setToolTip(text)
        self.field.setToolTip(text)


class ShapedRows(QWidget):
    """The rows of one kind; hidden until its layer is chosen."""

    def __init__(self, kind: str, picker) -> None:
        super().__init__()
        self.kind = kind
        self.picker = picker
        self.fields: dict = {}
        self.numbers: dict = {}
        self.form = QFormLayout(self)
        self.form.setContentsMargins(0, 0, 0, 0)
        self.form.setRowWrapPolicy(QFormLayout.WrapLongRows)
        for key, text, how in ROWS[kind][1]:
            widget = NumberOrField(picker) if how == NUMBER else field_combo(picker)
            if how == NUMBER:
                self.numbers[key] = widget
                self.fields[key] = widget.field
            else:
                self.fields[key] = widget
            self.form.addRow(text, widget)
        self.table_field = field_combo(picker)
        self.table = QgsFileWidget()
        self.table.setFilter(TABLE_FILTER)
        self.table.setDialogTitle("Section table")
        self.form.addRow("Section table", self.table)
        self.form.addRow("Section table field, per line", self.table_field)
        self.start_end = QComboBox()
        self.end_end = QComboBox()
        self.taper = number_box(NUMBER_DECIMALS)
        self.form.addRow("Start of the line", self.start_end)
        self.form.addRow("End of the line", self.end_end)
        self.form.addRow("Taper length, m", self.taper)
        self.hide()
        picker.layerChanged.connect(lambda layer: self.setVisible(layer is not None))

    def apply_schema(self, schema) -> None:
        for key, widget in self.numbers.items():
            path = (OBJECT_PATH if key == LINING else SECTION_PATH) + key
            bind(widget.box, schema, path)
            widget.setToolTip(schema.tip(path))
            if key == LINING:
                widget.box.setMinimum(0.0)
                widget.box.setSpecialValueText(NO_LINING)
                widget.box.setValue(0.0)
        for key, combo in (("start_end", self.start_end), ("end_end", self.end_end)):
            path = OBJECT_PATH + key
            combo.clear()
            combo.addItems(schema.enum(path))
            combo.setToolTip(schema.tip(path))
            combo.setCurrentText(schema.default(path, ""))
        bind(self.taper, schema, OBJECT_PATH + "taper_length")

    def _table_path(self, value, layer) -> str | None:
        if not value:
            return self.table.filePath() or None
        path = Path(str(value))
        if path.is_absolute():
            return str(path)
        return str(Path(layer.source().split("|")[0]).parent / path)

    def features(self, crs) -> list:
        """The layer's lines with every value in their properties: a field where it holds one, else the number."""
        layer = self.picker.currentLayer()
        chosen = {key: combo.currentField() for key, combo in self.fields.items()}
        chosen[TABLE] = self.table_field.currentField()
        numbers = {key: widget.box.value() for key, widget in self.numbers.items()}
        ends = dict(
            zip(
                END_KEYS,
                (self.start_end.currentText(), self.end_end.currentText(), self.taper.value()),
                strict=True,
            )
        )
        features = []
        for feature in layer_features(layer, crs, chosen):
            held = {key: value for key, value in feature.properties.items() if value is not None}
            merged = {**numbers, **ends, **held, TABLE: self._table_path(held.get(TABLE), layer)}
            features.append(replace(feature, properties=merged))
        return features
