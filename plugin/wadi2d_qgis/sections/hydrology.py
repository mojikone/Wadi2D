# Wadi2D QGIS plugin. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""3. Hydrology: an HMS project with a mode per subbasin, or plain rain; the curve number either way."""

from __future__ import annotations

from pathlib import Path

from qgis.gui import QgsFileWidget
from qgis.PyQt.QtWidgets import QComboBox, QFormLayout, QHeaderView, QTableWidget, QTableWidgetItem, QWidget

from ..job_builder import (
    CURVE_NUMBER,
    HMS_KEYS,
    MINUTES_PER_HOUR,
    RAIN_DEPTH,
    RAIN_DURATION,
    SUBBASIN_MODE,
    hms_files,
    hms_subbasins,
)
from .common import Section, ValueOrRaster, bind, number_box

HMS_LABELS = {"basin": "Basin file", "met": "Meteorologic file", "control": "Control file"}


class HydrologySection(Section):
    heading = "3. Hydrology"

    def build(self) -> None:
        self.folder = QgsFileWidget()
        self.folder.setStorageMode(QgsFileWidget.GetDirectory)
        self.folder.setDialogTitle("HEC-HMS project folder")
        self.form.addRow("HMS project (optional)", self.folder)

        self.rain_box = QWidget()
        rain = QFormLayout(self.rain_box)
        rain.setContentsMargins(0, 0, 0, 0)
        self.rain = number_box(1)
        self.hours = number_box(2)
        rain.addRow("Rain, mm/h", self.rain)
        rain.addRow("Lasting, hours", self.hours)
        self.form.addRow(self.rain_box)

        self.hms_box = QWidget()
        hms = QFormLayout(self.hms_box)
        hms.setContentsMargins(0, 0, 0, 0)
        self.files = {key: QComboBox() for key in HMS_KEYS}
        for key in HMS_KEYS:
            hms.addRow(HMS_LABELS[key], self.files[key])
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["Subbasin", "Treated as"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.verticalHeader().hide()
        hms.addRow(self.table)
        self.form.addRow(self.hms_box)
        self.hms_box.hide()

        self.cn = ValueOrRaster(1, "Same value everywhere")
        self.cn.box.setSpecialValueText("No losses")
        self.form.addRow("Curve number", self.cn)

        self._modes: list[str] = []
        self.folder.fileChanged.connect(self._folder_changed)
        self.files["basin"].currentTextChanged.connect(self._basin_changed)

    def apply_schema(self, schema) -> None:
        bind(self.rain, schema, RAIN_DEPTH)
        bind(self.hours, schema, RAIN_DURATION, scale=1.0 / MINUTES_PER_HOUR)
        bind(self.cn.box, schema, CURVE_NUMBER)
        self._modes = schema.enum(SUBBASIN_MODE)
        self._basin_changed(self.files["basin"].currentText())

    def _use_hms(self) -> bool:
        path = self.folder.filePath()
        return bool(path) and Path(path).is_dir()

    def _folder_changed(self, path: str) -> None:
        use_hms = self._use_hms()
        self.hms_box.setVisible(use_hms)
        self.rain_box.setVisible(not use_hms)
        found = hms_files(path) if use_hms else {}
        for key, combo in self.files.items():
            combo.clear()
            combo.addItems(found.get(key, []))

    def _basin_changed(self, name: str) -> None:
        names = hms_subbasins(Path(self.folder.filePath()) / name) if name else []
        self.table.setRowCount(len(names))
        for row, subbasin in enumerate(names):
            self.table.setItem(row, 0, QTableWidgetItem(subbasin))
            mode = QComboBox()
            mode.addItems(self._modes)
            self.table.setCellWidget(row, 1, mode)

    def _subbasin_modes(self) -> dict[str, str]:
        rows = range(self.table.rowCount())
        return {self.table.item(row, 0).text(): self.table.cellWidget(row, 1).currentText() for row in rows}

    def values(self, crs) -> dict:
        values = {
            "curve_number": self.cn.value() if self.cn.box.isEnabled() else None,
            "cn_raster": self.cn.path(),
        }
        if self._use_hms():
            hms = {key: combo.currentText() for key, combo in self.files.items()}
            values["hms"] = {**hms, "folder": self.folder.filePath(), "modes": self._subbasin_modes()}
        else:
            values["rain_mm_h"] = self.rain.value()
            values["rain_hours"] = self.hours.value()
        return values
