# Wadi2D QGIS plugin. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""4. Boundaries: one line layer, one kind and value. A layer with fields "kind" and "value" sets them per line."""

from __future__ import annotations

from dataclasses import replace

from qgis.core import QgsMapLayerProxyModel
from qgis.PyQt.QtWidgets import QComboBox, QLabel

from ..job_builder import BOUNDARY_KIND, BOUNDARY_SLOPE, BOUNDARY_STAGE, layer_features
from .common import Section, bind, layer_combo, number_box

VALUE_FIELDS = {"stage": (BOUNDARY_STAGE, "Stage, m"), "normal": (BOUNDARY_SLOPE, "Energy slope")}


class BoundariesSection(Section):
    heading = "4. Boundaries"
    start_collapsed = True

    def build(self) -> None:
        self.layer = layer_combo(QgsMapLayerProxyModel.LineLayer, "None: all edges are walls")
        self.kind = QComboBox()
        self.value = number_box(5)
        self.value_label = QLabel()
        self.form.addRow("Lines", self.layer)
        self.form.addRow("Kind", self.kind)
        self.form.addRow(self.value_label, self.value)
        self._schema = None
        self.kind.currentTextChanged.connect(self._kind_changed)

    def apply_schema(self, schema) -> None:
        self._schema = schema
        self.kind.clear()
        self.kind.addItems(schema.enum(BOUNDARY_KIND))
        self.kind.setToolTip(schema.tip(BOUNDARY_KIND))
        self._kind_changed(self.kind.currentText())

    def _kind_changed(self, kind: str) -> None:
        path, label = VALUE_FIELDS.get(kind, (None, ""))
        self.value.setVisible(path is not None)
        self.value_label.setVisible(path is not None)
        self.value_label.setText(label)
        if path and self._schema:
            bind(self.value, self._schema, path)

    def values(self, crs) -> dict:
        layer = self.layer.currentLayer()
        if layer is None:
            return {"boundaries": []}
        names = {name.lower(): name for name in layer.fields().names()}
        fields = {key: names[key] for key in ("kind", "value") if key in names}
        kind = self.kind.currentText()
        value = self.value.value() if kind in VALUE_FIELDS else None
        lines = []
        for feature in layer_features(layer, crs, fields):
            own = feature.properties
            chosen = {"kind": own.get("kind") or kind, "value": own.get("value", value)}
            lines.append(replace(feature, properties=chosen))
        return {"boundaries": lines}
