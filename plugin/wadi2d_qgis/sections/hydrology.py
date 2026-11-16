# Wadi2D QGIS plugin. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""3. Hydrology: an HMS project, or a basin generated from the DEM, with a mode per subbasin; the reach routing scheme
(with K, X and subreaches per reach under Muskingum, W89) and the curve number either way; hand-back lines and the
transmission loss. The rain is section 4."""

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
    ARF_BY_ELEMENT,
    CURVE_NUMBER,
    EXCLUDE_LUMPED,
    HMS_KEYS,
    LUMPED_ENTRY,
    LUMPED_ENTRY_WORDS,
    LUMPED_ONLY,
    SUBBASIN_MODE,
    hms_files,
    hms_subbasins,
)
from ..muskingum_rows import MUSKINGUM, ReachRow, hms_reaches, model_reaches
from .basin import BasinBox, HandbackBox, LossRow
from .basin_rows import (
    REACH_ROUTING,
    ROUTING_WORDS,
    HandbackRow,
    SubbasinRow,
    hms_elements,
    mode_tip,
    subbasin_rows,
)
from .common import Section, ValueOrRaster, bind
from .muskingum_table import MuskingumBox

HMS_LABELS = {"basin": "Basin file", "met": "Meteorologic file", "control": "Control file"}
REFUSED_COLOUR = "#b00000"


class HydrologySection(Section):
    heading = "3. Hydrology"
    key = "hydrology"
    state_skip = ("rain", "hours")  # the Storm section's own widgets, which older dock checks reach from here
    state_rows = (("handbacks", HandbackRow, "_fill"), ("muskingum", ReachRow, "_show"))
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
        self.lumped_entry = QComboBox()
        hms.addRow("Lumped water enters the 2D model", self.lumped_entry)
        self.lumped_only = QCheckBox("The HMS way only: the lumped network alone, no 2D model")
        hms.addRow(self.lumped_only)
        self.arf_by_element = QCheckBox("Each element at its own drainage area's area reduction (depth-area analysis)")
        hms.addRow(self.arf_by_element)
        self.lumped_only.toggled.connect(self._lumped_only_toggled)
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
        self.muskingum = MuskingumBox()
        self.form.addRow(self.muskingum)
        self.muskingum.hide()
        self._exclude_known = False
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
        self.routing.currentIndexChanged.connect(self._routing_changed)

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
        self.lumped_entry.clear()
        for key in schema.enum(LUMPED_ENTRY) or []:
            self.lumped_entry.addItem(LUMPED_ENTRY_WORDS.get(key, key), key)
        self.lumped_entry.setToolTip(schema.tip(LUMPED_ENTRY))
        self.lumped_only.setToolTip(schema.tip(LUMPED_ONLY))
        self.lumped_only.setEnabled(schema.has(LUMPED_ONLY))  # an engine from before W88 would refuse the fields
        self.arf_by_element.setToolTip(schema.tip(ARF_BY_ELEMENT))
        self.exclude.setChecked(bool(schema.default(EXCLUDE_LUMPED, False)))
        self.exclude.setToolTip(schema.tip(EXCLUDE_LUMPED))
        self._exclude_known = schema.has(EXCLUDE_LUMPED)
        self._lumped_only_toggled(self.lumped_only.isChecked())
        self.basin.apply_schema(schema)
        self.loss.apply_schema(schema)
        self._basin_changed(self.files["basin"].currentText())

    def _routing_changed(self, *_) -> None:
        """The reach table shows under Muskingum, with the reaches of the basin in use."""
        on = self.routing.currentData() == MUSKINGUM
        self.muskingum.setVisible(on)
        if on:
            self._fill_reaches()

    def reach_source(self) -> tuple[str, str | None] | None:
        """The basin file the reaches come from and, for an HMS project, its control file; None with no basin."""
        if self._use_hms():
            folder = Path(self.folder.filePath())
            basin, control = (self.files[key].currentText() for key in ("basin", "control"))
            if basin and (folder / basin).is_file():
                return str(folder / basin), str(folder / control) if control else None
        elif self.basin.in_use() and self.basin.json_path:
            return self.basin.json_path, None
        return None

    def _fill_reaches(self) -> None:
        if self._use_hms():
            source = self.reach_source()
            self.muskingum.set_reaches(hms_reaches(source[0]) if source else [], False)
        elif self.basin.in_use() and self.basin.model is not None:
            self.muskingum.set_reaches(model_reaches(self.basin.model), True)
        else:
            self.muskingum.set_reaches([], False)

    def _lumped_only_toggled(self, on: bool) -> None:
        self.arf_by_element.setEnabled(on)
        self.lumped_entry.setEnabled(not on and self.lumped_entry.count() > 0)
        self.exclude.setEnabled(not on and self._exclude_known)

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
        self._fill_reaches()

    def _generate_toggled(self, on: bool) -> None:
        self.folder.setEnabled(not on)
        self.table.setVisible(on and self.basin.model is not None)
        if on and self.basin.model is not None:  # the table may hold an HMS project's rows: back to the generated ones
            asked = self._subbasin_modes()
            self._fill_table(subbasin_rows(self.basin.model, asked))
            self.handbacks.set_choices(self.basin.element_choices())
        self._fill_reaches()

    def _basin_changed(self, name: str) -> None:
        if not name:
            return
        path = Path(self.folder.filePath()) / name
        names = hms_subbasins(path)
        self._fill_table([SubbasinRow(n, [], "lumped", mode_tip(n, [], "lumped")) for n in names])
        self.handbacks.set_choices(hms_elements(path))
        self.show_structures([], "")
        self._fill_reaches()
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
            self._fill_reaches()

    def _subbasin_modes(self) -> dict[str, str]:
        rows = range(self.table.rowCount())
        return {self.table.item(row, 0).text(): self.table.cellWidget(row, 1).currentText() for row in rows}

    # The saved model (W99): the generated basin is a file, and the mode of each subbasin a table of cell widgets.

    def extra_state(self) -> dict:
        return {"basin_json": self.basin.json_path, "modes": self._subbasin_modes()}

    def restore_extra(self, extra: dict, add_missing: bool = False) -> list[str]:
        found = []
        path = extra.get("basin_json")
        if path and not self._use_hms():
            if Path(path).is_file():
                self.basin.take({"basin": path})
            else:
                found.append(f"the generated basin is not there any more ({path}): press Generate basin")
        modes = extra.get("modes") or {}
        for row in range(self.table.rowCount()):
            name, combo = self.table.item(row, 0).text(), self.table.cellWidget(row, 1)
            if name in modes and combo.isEnabled():
                combo.setCurrentText(modes[name])
        missing = sorted(set(modes) - set(self._subbasin_modes()))
        if missing:
            found.append(f"subbasins no longer in the basin: {', '.join(missing)}")
        if self.routing.currentData() == MUSKINGUM:
            self._fill_reaches()
        return found

    def values(self, crs) -> dict:
        values = {
            "curve_number": self.cn.value() if self.cn.box.isEnabled() else None,
            "cn_raster": self.cn.path(),
            "reach_routing": self.routing.currentData(),
            "exclude_lumped": self.exclude.isChecked() and self.exclude.isEnabled(),
            "handbacks": self.handbacks.features(crs),
            "transmission": self.loss.values(),
        }
        if values["reach_routing"] == MUSKINGUM:
            values["muskingum"] = self.muskingum.values()
        if self._use_hms():
            hms = {key: combo.currentText() for key, combo in self.files.items()}
            values["hms"] = {**hms, "folder": self.folder.filePath(), "modes": self._subbasin_modes()}
            values["lumped_entry"] = self.lumped_entry.currentData() if self.lumped_entry.isEnabled() else None
            values["lumped_only"] = self.lumped_only.isChecked() and self.lumped_only.isEnabled()
            values["arf_by_element"] = values["lumped_only"] and self.arf_by_element.isChecked()
        elif self.basin.isChecked():
            values["basin"] = {**self.basin.values(crs), "modes": self._subbasin_modes()}
        return values
