# Wadi2D QGIS plugin. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""3. Hydrology: an HMS project, or a basin generated from the DEM, with a mode per subbasin; the curve number either
way; hand-back lines and the transmission loss. The rain is section 4."""

from __future__ import annotations

from pathlib import Path

from qgis.gui import QgsFileWidget
from qgis.PyQt.QtCore import pyqtSignal
from qgis.PyQt.QtWidgets import QComboBox, QFormLayout, QHeaderView, QTableWidget, QTableWidgetItem, QWidget

from ..job_builder import (
    CURVE_NUMBER,
    HMS_KEYS,
    SUBBASIN_MODE,
    hms_files,
    hms_subbasins,
)
from .basin import BasinBox, HandbackBox, LossRow
from .basin_rows import SubbasinRow, hms_elements, mode_tip
from .common import Section, ValueOrRaster, bind

HMS_LABELS = {"basin": "Basin file", "met": "Meteorologic file", "control": "Control file"}


class HydrologySection(Section):
    heading = "3. Hydrology"
    hms_changed = pyqtSignal(bool)
    """Whether an HMS project is in use."""

    def build(self) -> None:
        self.folder = QgsFileWidget()
        self.folder.setStorageMode(QgsFileWidget.GetDirectory)
        self.folder.setDialogTitle("HEC-HMS project folder")
        self.form.addRow("HMS project (optional)", self.folder)

        self.hms_box = QWidget()
        hms = QFormLayout(self.hms_box)
        hms.setContentsMargins(0, 0, 0, 0)
        self.files = {key: QComboBox() for key in HMS_KEYS}
        for key in HMS_KEYS:
            hms.addRow(HMS_LABELS[key], self.files[key])
        self.form.addRow(self.hms_box)
        self.hms_box.hide()

        self.basin = BasinBox()
        self.form.addRow(self.basin)

        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["Subbasin", "Treated as"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.verticalHeader().hide()
        self.form.addRow(self.table)
        self.table.hide()

        self.handbacks = HandbackBox()
        self.form.addRow(self.handbacks)
        self.loss = LossRow()
        self.form.addRow(self.loss)

        self.cn = ValueOrRaster(1, "Same value everywhere")
        self.cn.box.setSpecialValueText("No losses")
        self.form.addRow("Curve number", self.cn)

        self._modes: list[str] = []
        self.folder.fileChanged.connect(self._folder_changed)
        self.files["basin"].currentTextChanged.connect(self._basin_changed)
        self.basin.toggled.connect(self._generate_toggled)
        self.basin.subbasins_changed.connect(self._fill_table)

    def apply_schema(self, schema) -> None:
        bind(self.cn.box, schema, CURVE_NUMBER)
        self._modes = schema.enum(SUBBASIN_MODE)
        self.basin.apply_schema(schema)
        self.loss.apply_schema(schema)
        self._basin_changed(self.files["basin"].currentText())

    def _use_hms(self) -> bool:
        path = self.folder.filePath()
        return bool(path) and Path(path).is_dir()

    def _folder_changed(self, path: str) -> None:
        use_hms = self._use_hms()
        self.hms_box.setVisible(use_hms)
        if use_hms:
            self.basin.setChecked(False)
        self.basin.setEnabled(not use_hms)
        self.hms_changed.emit(use_hms)
        found = hms_files(path) if use_hms else {}
        for key, combo in self.files.items():
            combo.clear()
            combo.addItems(found.get(key, []))
        if not use_hms:
            self.table.setVisible(self.basin.in_use())

    def _generate_toggled(self, on: bool) -> None:
        self.folder.setEnabled(not on)
        self.table.setVisible(on and self.basin.model is not None)
        if on and self.basin.model is not None:
            self.handbacks.set_choices(self.basin.element_choices())

    def _basin_changed(self, name: str) -> None:
        if not name:
            return
        path = Path(self.folder.filePath()) / name
        names = hms_subbasins(path)
        self._fill_table([SubbasinRow(n, [], "lumped", mode_tip(n, [], "lumped")) for n in names])
        self.handbacks.set_choices(hms_elements(path))

    def _fill_table(self, rows: list[SubbasinRow]) -> None:
        """Every subbasin with its mode: a choice where the parameters are complete, rain-on-grid where not."""
        self.table.setRowCount(len(rows))
        for number, row in enumerate(rows):
            item = QTableWidgetItem(row.name)
            item.setToolTip(row.tip)
            self.table.setItem(number, 0, item)
            mode = QComboBox()
            mode.addItems(self._modes)
            mode.setCurrentText(row.mode)
            mode.setToolTip(row.tip)
            mode.setEnabled(not row.missing)
            self.table.setCellWidget(number, 1, mode)
        self.table.setVisible(bool(rows))
        if self.basin.in_use():
            self.handbacks.set_choices(self.basin.element_choices())

    def _subbasin_modes(self) -> dict[str, str]:
        rows = range(self.table.rowCount())
        return {self.table.item(row, 0).text(): self.table.cellWidget(row, 1).currentText() for row in rows}

    def values(self, crs) -> dict:
        values = {
            "curve_number": self.cn.value() if self.cn.box.isEnabled() else None,
            "cn_raster": self.cn.path(),
            "handbacks": self.handbacks.features(crs),
            "transmission": self.loss.values(),
        }
        if self._use_hms():
            hms = {key: combo.currentText() for key, combo in self.files.items()}
            values["hms"] = {**hms, "folder": self.folder.filePath(), "modes": self._subbasin_modes()}
        elif self.basin.isChecked():
            values["basin"] = {**self.basin.values(crs), "modes": self._subbasin_modes()}
        return values
