# Wadi2D QGIS plugin. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Water standing when the run starts: a table of the dams of the Structures layers, and polygons of other ponds."""

from __future__ import annotations

from functools import partial

from qgis.core import QgsMapLayerProxyModel
from qgis.PyQt.QtCore import QSignalBlocker, Qt
from qgis.PyQt.QtWidgets import (
    QComboBox,
    QFormLayout,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QWidget,
)

from ..dam_rows import START_LEVEL, START_WORDS, DamRow, dam_levels, dam_names, merge_dams
from ..job_builder import DAM_LEVELS, layer_features
from .common import field_combo, layer_combo, number_box

COLUMNS = ["Dam", "Start", "Level, m"]
NAME_COLUMN, START_COLUMN, LEVEL_COLUMN = range(3)
NAME_FIELDS = ("name", "Name", "NAME")
DAM_KINDS = ("crest_line", "embankment")
SHOWN_ROWS = 5
LEVEL_DECIMALS = 2
UNSET = -1.0e4
"""The level box's floor: shown as "not set"."""


class StartWater(QWidget):
    """The dams of ``pickers`` (crest lines and embankments by kind) and a polygon layer of initial water."""

    def __init__(self, pickers: dict) -> None:
        super().__init__()
        self.pickers = {kind: pickers[kind] for kind in DAM_KINDS if kind in pickers}
        self.rows: list[DamRow] = []
        self._watched: list = []
        form = QFormLayout(self)
        form.setContentsMargins(0, 0, 0, 0)
        form.setRowWrapPolicy(QFormLayout.WrapLongRows)
        self.note = QLabel("Dams start empty unless set here; a scenario (a breach, say) sets a level.")
        self.note.setWordWrap(True)
        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.verticalHeader().hide()
        self.table.setToolTip("Each named crest line or embankment. A lumped reservoir of the same name takes the start; else the pool behind the line on the grid.")
        self.ponds = layer_combo(QgsMapLayerProxyModel.PolygonLayer, "None")
        self.pond_level = field_combo(self.ponds)
        form.addRow(self.note)
        form.addRow("Dam start levels", self.table)
        form.addRow("Initial water, polygons", self.ponds)
        form.addRow("Water level field", self.pond_level)
        for picker in self.pickers.values():
            picker.layerChanged.connect(self._layers_changed)
        self._layers_changed()

    def apply_schema(self, schema) -> None:
        self.table.setToolTip(schema.tip(DAM_LEVELS + ".start"))

    def _layers_changed(self, *_) -> None:
        for layer in self._watched:
            layer.dataChanged.disconnect(self.fill)
        self._watched = [p.currentLayer() for p in self.pickers.values() if p.currentLayer() is not None]
        for layer in self._watched:
            layer.dataChanged.connect(self.fill)
        self.fill()

    def _names(self) -> list[str]:
        found = []
        for layer in self._watched:
            field = next((f for f in NAME_FIELDS if f in layer.fields().names()), None)
            if field is not None:
                found.extend(feature[field] for feature in layer.getFeatures())
        return dam_names(found)

    def fill(self, *_) -> None:
        self.rows = merge_dams(self._names(), self.rows)
        self.table.setRowCount(len(self.rows))
        for number, row in enumerate(self.rows):
            name = QTableWidgetItem(row.name)
            name.setFlags(name.flags() & ~Qt.ItemIsEditable)  # the name is the layer's
            self.table.setItem(number, NAME_COLUMN, name)
            start = QComboBox()
            for key, words in START_WORDS.items():
                start.addItem(words, key)
            start.setCurrentIndex(start.findData(row.start))
            start.currentIndexChanged.connect(partial(self._start, row, start))
            self.table.setCellWidget(number, START_COLUMN, start)
            level = number_box(LEVEL_DECIMALS)
            level.setMinimum(UNSET)
            level.setSpecialValueText("not set")
            with QSignalBlocker(level):
                level.setValue(UNSET if row.level is None else row.level)
            level.setEnabled(row.start == START_LEVEL)
            level.valueChanged.connect(partial(self._level, row))
            self.table.setCellWidget(number, LEVEL_COLUMN, level)
        high = self.table.horizontalHeader().height() + self.table.verticalHeader().defaultSectionSize() * SHOWN_ROWS
        self.table.setMaximumHeight(high + 2 * self.table.frameWidth())
        self.table.setVisible(bool(self.rows))

    def _start(self, row: DamRow, combo: QComboBox, *_) -> None:
        row.start = combo.currentData()
        number = self.rows.index(row)
        self.table.cellWidget(number, LEVEL_COLUMN).setEnabled(row.start == START_LEVEL)

    def _level(self, row: DamRow, value: float) -> None:
        row.level = None if value <= UNSET else value

    def values(self, crs) -> dict:
        self.fill()
        layer = self.ponds.currentLayer()
        ponds = []
        if layer is not None:
            ponds = layer_features(layer, crs, {"level": self.pond_level.currentField()})
        return {"dam_rows": list(self.rows), "dam_levels": dam_levels(self.rows), "initial_water": ponds}
