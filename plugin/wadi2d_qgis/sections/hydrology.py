# Wadi2D QGIS plugin. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""3. Hydrology: an HMS project, or a basin generated from the DEM, with a mode per subbasin; the reach routing scheme
and the curve number either way; hand-back lines and the transmission loss. The rain is section 4."""

from __future__ import annotations

from pathlib import Path

from qgis.gui import QgsFileWidget
from qgis.PyQt.QtCore import pyqtSignal
from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QWidget,
)

from ..hms_structure_rows import COLUMNS as STRUCTURE_COLUMNS
from ..hms_structure_rows import ReservoirRow
from ..job_builder import (
    CURVE_NUMBER,
    EXCLUDE_LUMPED,
    HMS_KEYS,
    SUBBASIN_MODE,
    hms_files,
    hms_subbasins,
)
from .basin import BasinBox, HandbackBox, LossRow
from .basin_rows import REACH_ROUTING, ROUTING_WORDS, SubbasinRow, hms_elements, mode_tip, subbasin_rows
from .common import Section, ValueOrRaster, bind

HMS_LABELS = {"basin": "Basin file", "met": "Meteorologic file", "control": "Control file"}
REFUSED_COLOUR = "#b00000"


class HydrologySection(Section):
    heading = "3. Hydrology"
    hms_changed = pyqtSignal(bool)
    """Whether an HMS project is in use."""
    structures_requested = pyqtSignal(str)
    """An HMS basin file was chosen: the dock asks the engine what its reservoirs route by (W75)."""

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
        self.reservoirs = QTableWidget(0, len(STRUCTURE_COLUMNS))
        self.reservoirs.setHorizontalHeaderLabels(STRUCTURE_COLUMNS)
        self.reservoirs.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.reservoirs.verticalHeader().hide()
        self.reservoirs.setEditTriggers(QTableWidget.NoEditTriggers)
        self.reservoirs.setToolTip(
            "Read only: each reservoir of the HMS basin, its outlets and options as the file holds them (culverts, "
            "orifices, gates, pumps, spillways, dam tops, seepage, evaporation) and the engine's word, the run's own. "
            "Edit them in HEC-HMS."
        )
        self.reservoirs_note = QLabel("")
        self.reservoirs_note.setWordWrap(True)
        hms.addRow(self.reservoirs)
        hms.addRow(self.reservoirs_note)
        self.reservoirs.hide()
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

        self.routing = QComboBox()
        self.form.addRow("Reach routing", self.routing)
        self.exclude = QCheckBox("Leave the catchments the lumped network carries out of the 2D mesh")
        self.form.addRow(self.exclude)

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
        self.routing.clear()
        for key in schema.enum(REACH_ROUTING):
            self.routing.addItem(ROUTING_WORDS.get(key, key), key)
        self.routing.setToolTip(schema.tip(REACH_ROUTING))
        default = schema.default(REACH_ROUTING)
        if default is not None:
            self.routing.setCurrentIndex(max(self.routing.findData(default), 0))
        self.exclude.setChecked(bool(schema.default(EXCLUDE_LUMPED, False)))
        self.exclude.setToolTip(schema.tip(EXCLUDE_LUMPED))
        self.exclude.setEnabled(schema.has(EXCLUDE_LUMPED))  # an engine from before W88 would refuse the field
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
        if on and self.basin.model is not None:  # the table may hold an HMS project's rows: back to the generated ones
            asked = self._subbasin_modes()
            self._fill_table(subbasin_rows(self.basin.model, asked))
            self.handbacks.set_choices(self.basin.element_choices())

    def _basin_changed(self, name: str) -> None:
        if not name:
            return
        path = Path(self.folder.filePath()) / name
        names = hms_subbasins(path)
        self._fill_table([SubbasinRow(n, [], "lumped", mode_tip(n, [], "lumped")) for n in names])
        self.handbacks.set_choices(hms_elements(path))
        self.show_structures([], "")
        if path.is_file():
            self.structures_requested.emit(str(path))

    def say_structures(self, text: str) -> None:
        self.reservoirs_note.setText(text)

    def show_structures(self, rows: list[ReservoirRow], note: str) -> None:
        """The engine's answer on the basin's reservoirs, read only."""
        self.reservoirs.setRowCount(len(rows))
        for number, row in enumerate(rows):
            for column, text in enumerate((row.name, row.method, row.structures, row.word)):
                item = QTableWidgetItem(text)
                item.setToolTip(text)
                if row.refused and column == len(STRUCTURE_COLUMNS) - 1:
                    item.setForeground(QColor(REFUSED_COLOUR))
                self.reservoirs.setItem(number, column, item)
        self.reservoirs.setVisible(bool(rows))
        self.reservoirs_note.setText(note)

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
            "reach_routing": self.routing.currentData(),
            "exclude_lumped": self.exclude.isChecked() and self.exclude.isEnabled(),
            "handbacks": self.handbacks.features(crs),
            "transmission": self.loss.values(),
        }
        if self._use_hms():
            hms = {key: combo.currentText() for key, combo in self.files.items()}
            values["hms"] = {**hms, "folder": self.folder.filePath(), "modes": self._subbasin_modes()}
        elif self.basin.isChecked():
            values["basin"] = {**self.basin.values(crs), "modes": self._subbasin_modes()}
        return values
