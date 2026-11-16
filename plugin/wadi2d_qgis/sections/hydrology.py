# Wadi2D QGIS plugin. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""3. Hydrology: an HMS project, or a basin generated from the DEM, with a mode per subbasin, and on an HMS project its
own storm area, entry and outlet (W103); the point inflows of lumped elements (W103); the reach routing scheme (with K,
X and subreaches per reach under Muskingum, W89) and the curve number either way; hand-back lines and the transmission
loss. The rain is section 4."""

from __future__ import annotations

from functools import partial
from pathlib import Path

from qgis.core import QgsMapLayerProxyModel
from qgis.gui import QgsFileWidget
from qgis.PyQt.QtCore import QSignalBlocker, pyqtSignal
from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QTableWidget,
    QTableWidgetItem,
    QWidget,
)

from .. import entry_rows, section_status
from ..hms_structure_rows import COLUMNS as STRUCTURE_COLUMNS
from ..hms_structure_rows import ReservoirRow
from ..job_builder import (
    CURVE_NUMBER,
    EXCLUDE_LUMPED,
    HMS_KEYS,
    LUMPED_ENTRY,
    LUMPED_ENTRY_WORDS,
    LUMPED_ONLY,
    SUBBASIN_MODE,
    hms_files,
    hms_subbasins,
    raster_path,
)
from ..land_rows import BY_LAND, CN_COLUMNS, CN_WORDS, NONE, by_rows, cn_problems, cn_words
from ..model_types import HYBRID_LUMPED, LUMPED, TWO_D
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
from .class_table import ClassTable
from .common import Section, ValueOrRaster, bind, layer_combo
from .inflow_table import InflowTable
from .muskingum_table import MuskingumBox

HMS_LABELS = {"basin": "Basin file", "met": "Meteorologic file", "control": "Control file"}
REFUSED_COLOUR = "#b00000"
SUBBASIN_COLUMNS = ["Subbasin", "Treated as", "Storm area, km2", "Enters", "Outlet x, y"]
NAME, MODE, AREA, ENTRY, OUTLET = range(len(SUBBASIN_COLUMNS))
EDIT_COLUMNS = (AREA, ENTRY, OUTLET)
"""The columns of each subbasin's own storm area, entry and outlet (W103): shown on an HMS project, whose import the
job's subbasins come from. A generated basin's subbasins take neither storm area nor entry in this engine."""
AREA_DECIMALS = 4
AREA_MOST = 1.0e7
OWN_STORM = "the storm's"
BASIN_GIVES = "the basin's"
EDIT_TIPS = {
    AREA: (
        "The area at which this lumped subbasin's rain reads the area-reduction curve, in place of the storm's: a "
        "subbasin above a dam at the dam's drainage area, as HMS's depth-area analysis at the dam reads it. Empty: the "
        "storm's own area, or the lumped curve's entry area (4b)."
    ),
    ENTRY: (
        "Where the lumped hydrograph enters the grid: at the wadi outlet of the subbasin's polygon (the HMS import's way, "
        "since HMS icons are schematic), or at its outlet point as given. 'As the basin gives' writes nothing."
    ),
    OUTLET: (
        'The outlet point, x, y in the DEM\'s coordinates. "none": no outlet of its own, for a subbasin whose water a '
        "point inflow below it carries (it would otherwise enter twice). Empty: the HMS import's."
    ),
}


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
        self.lumped_box = QWidget()  # every row of the lumped part: a 2D model hides them in one go (W99)
        lumped = QFormLayout(self.lumped_box)
        lumped.setContentsMargins(0, 0, 0, 0)
        lumped.setRowWrapPolicy(QFormLayout.WrapLongRows)
        self.folder = QgsFileWidget()
        self.folder.setStorageMode(QgsFileWidget.GetDirectory)
        self.folder.setDialogTitle("HEC-HMS project folder")
        lumped.addRow("HMS project (optional)", self.folder)

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
        self.lumped_only.toggled.connect(self._lumped_only_toggled)
        lumped.addRow(self.hms_box)
        self.hms_box.hide()

        self.basin = BasinBox()
        lumped.addRow(self.basin)

        self.table = QTableWidget(0, len(SUBBASIN_COLUMNS))
        self.table.setHorizontalHeaderLabels(SUBBASIN_COLUMNS)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.verticalHeader().hide()
        for column, tip in EDIT_TIPS.items():
            self.table.horizontalHeaderItem(column).setToolTip(tip)
        lumped.addRow(self.table)
        self.table.hide()
        self._edits: dict[str, dict] = {}
        """Each subbasin's own storm area, entry and outlet, by name (W103): what the job writes over the import's."""
        self._edit_problems: dict[str, str] = {}
        """An outlet cell that holds no point, in words, by subbasin."""
        self.inflows = InflowTable()  # W103: hydrology.inflows, saved with the model as a pair table
        lumped.addRow(self.inflows)

        self.routing = QComboBox()
        lumped.addRow("Reach routing", self.routing)
        self.muskingum = MuskingumBox()
        lumped.addRow(self.muskingum)
        self.muskingum.hide()
        self._exclude_known = False
        self.exclude = QCheckBox("Leave the catchments the lumped network carries out of the 2D mesh")
        lumped.addRow(self.exclude)

        self.handbacks = HandbackBox()
        lumped.addRow(self.handbacks)
        self.form.addRow(self.lumped_box)
        self.loss = LossRow()
        self.form.addRow(self.loss)

        self.cn = ValueOrRaster(1, "Same value everywhere")
        self.cn.box.setSpecialValueText("No losses")
        self.form.addRow("Curve number", self.cn)
        self.cn_by = QComboBox()  # W101 item 2: the CN override (W96's hydrology.cn_override)
        for key, words in CN_WORDS.items():
            self.cn_by.addItem(words, key)
        self.cn_by.setToolTip(
            "CN in place of what the CN grid, the value above and the basin give, on rain-on-grid cells and lumped "
            "subbasins alike"
        )
        self.cn_landuse = layer_combo(QgsMapLayerProxyModel.RasterLayer, "Choose the land-use raster")
        self.cn_table = ClassTable(*CN_COLUMNS[BY_LAND])
        self.form.addRow("CN override", self.cn_by)
        self.form.addRow("Land-use raster", self.cn_landuse)
        self.form.addRow(self.cn_table)
        self.cn_by.currentIndexChanged.connect(self._cn_shown)
        self._cn_shown()

        self._modes: list[str] = []
        self._cn_by_shown = None
        self.folder.fileChanged.connect(self._folder_changed)
        self.files["basin"].currentTextChanged.connect(self._basin_changed)
        self.basin.toggled.connect(self._generate_toggled)
        self.basin.subbasins_changed.connect(self._fill_table)
        self.routing.currentIndexChanged.connect(self._routing_changed)

    def _cn_shown(self, *_) -> None:
        if not hasattr(self, "_cn_by_shown"):
            self._cn_by_shown = None
        by = self.cn_by.currentData()
        self.cn_landuse.setVisible(by == BY_LAND)
        self.form.labelForField(self.cn_landuse).setVisible(by == BY_LAND)
        self.cn_table.setVisible(by != NONE)
        if by != NONE:
            held = self.cn_table.rows()
            self.cn_table.set_headers(*CN_COLUMNS[by])
            if self._cn_by_shown not in (None, by):  # another kind of table: its rows do not carry over
                held = []
            self.cn_table.set_rows(held)
        self._cn_by_shown = by

    def cn_override(self) -> dict:
        by = self.cn_by.currentData()
        rows = self.cn_table.rows() if by != NONE else []
        found = {"by": by, "land_use": raster_path(self.cn_landuse.currentLayer()) or ""}
        if by != NONE:
            found[by_rows(by)] = rows
        return found

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
        self.exclude.setChecked(bool(schema.default(EXCLUDE_LUMPED, False)))
        self.exclude.setToolTip(schema.tip(EXCLUDE_LUMPED))
        self._exclude_known = schema.has(EXCLUDE_LUMPED)
        self._lumped_only_toggled(self.lumped_only.isChecked())
        self.basin.apply_schema(schema)
        self.loss.apply_schema(schema)
        self._basin_changed(self.files["basin"].currentText())

    def set_model_type(self, kind: str | None) -> None:
        """What the model type leaves to choose here (W99). A 2D model has no lumped part. A type sets the HMS way
        only and the catchments left out of the mesh, and Hybrid 2D the entry at the outlets: those three show only
        where a real choice is left. The two ticks follow the type, so what they switch on and off follows too; the
        entry keeps the user's choice for the day the type is Hybrid Lumped again (the job takes the type's,
        ``model_types.apply_type``). With no type every row shows, as before."""
        typed = kind is not None
        self.lumped_box.setVisible(kind != TWO_D)
        self.lumped_only.setVisible(not typed)
        self.exclude.setVisible(not typed)
        entry = not typed or kind == HYBRID_LUMPED
        self.lumped_entry.setVisible(entry)
        self.hms_box.layout().labelForField(self.lumped_entry).setVisible(entry)
        if not typed:
            return
        self.lumped_only.setChecked(kind == LUMPED)
        self.exclude.setChecked(kind == HYBRID_LUMPED)

    def standing(self, kind=None):
        use_hms = self._use_hms()
        modes = self._subbasin_modes()
        raster = self.cn.raster.currentLayer()
        curve = self.cn.value() if self.cn.box.isEnabled() and self.cn.value() > self.cn.box.minimum() else None
        override = self.cn_override()
        found = cn_problems(override)
        if found:  # the CN override (W101 item 2)
            return section_status.Status(section_status.MISSING, found[0])
        status = section_status.hydrology(
            kind,
            Path(self.folder.filePath()).name if use_hms else None,
            all(self.files[key].currentText() for key in HMS_KEYS),
            self.basin.isChecked() and not use_hms,
            bool(self.basin.json_path),
            len(modes),
            sum(1 for mode in modes.values() if mode == LUMPED),
            curve,
            raster.name() if raster is not None else None,
            self.loss.rate.value() if self.loss.enabled.isChecked() else None,
        )
        edits = self.subbasin_edits() if kind != TWO_D else {}
        rows = self.inflows.rows() if kind != TWO_D else []
        found = self.entry_problems() + entry_rows.edit_problems(edits, modes) + entry_rows.inflow_problems(rows)
        if found and status.state != section_status.MISSING:  # W103: what the table holds, in words
            return section_status.Status(section_status.MISSING, found[0])
        words = section_status.join(status.words, cn_words(override), entry_rows.words(edits, rows))
        return section_status.Status(status.state, words)

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
        self._show_edit_columns()
        self._fill_reaches()

    def _generate_toggled(self, on: bool) -> None:
        self.folder.setEnabled(not on)
        self.table.setVisible(on and self.basin.model is not None)
        if on and self.basin.model is not None:  # the table may hold an HMS project's rows: back to the generated ones
            asked = self._subbasin_modes()
            self._fill_table(subbasin_rows(self.basin.model, asked))
            self.handbacks.set_choices(self.basin.element_choices())
            self.inflows.set_choices(self.basin.element_choices())
        self._show_edit_columns()
        self._fill_reaches()

    def _basin_changed(self, name: str) -> None:
        if not name:
            return
        path = Path(self.folder.filePath()) / name
        names = hms_subbasins(path)
        self._fill_table([SubbasinRow(n, [], "lumped", mode_tip(n, [], "lumped")) for n in names])
        self.handbacks.set_choices(hms_elements(path))
        self.inflows.set_choices(hms_elements(path))
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
            self._edit_cells(number, row.name)
        self.table.setVisible(bool(rows))
        self._show_edit_columns()
        if self.basin.in_use():
            self.handbacks.set_choices(self.basin.element_choices())
            self.inflows.set_choices(self.basin.element_choices())
            self._fill_reaches()

    def _subbasin_modes(self) -> dict[str, str]:
        rows = range(self.table.rowCount())
        return {self.table.item(row, 0).text(): self.table.cellWidget(row, 1).currentText() for row in rows}

    # Each subbasin's own storm area, entry and outlet (W103): cells of the subbasin table over a dict by name.

    def _show_edit_columns(self) -> None:
        for column in EDIT_COLUMNS:
            self.table.setColumnHidden(column, not self._use_hms())

    def _edit_cells(self, number: int, name: str) -> None:
        """The three cells of one subbasin, from what ``_edits`` holds for it."""
        edit = self._edits.get(name, {})
        area = QDoubleSpinBox()
        area.setDecimals(AREA_DECIMALS)
        area.setRange(0.0, AREA_MOST)
        area.setSpecialValueText(OWN_STORM)
        area.setToolTip(EDIT_TIPS[AREA])
        with QSignalBlocker(area):
            area.setValue(edit.get("storm_area_km2") or 0.0)
        area.valueChanged.connect(partial(self._area_changed, name))
        self.table.setCellWidget(number, AREA, area)
        entry = QComboBox()
        for key, words in entry_rows.ENTRY_WORDS.items():
            entry.addItem(words, key)
        entry.setToolTip(EDIT_TIPS[ENTRY])
        with QSignalBlocker(entry):
            entry.setCurrentIndex(max(entry.findData(edit.get("entry")), 0) if edit.get("entry") else 0)
        entry.currentIndexChanged.connect(partial(self._entry_changed, name, entry))
        self.table.setCellWidget(number, ENTRY, entry)
        outlet = QLineEdit(entry_rows.outlet_text(edit.get("outlet")))
        outlet.setPlaceholderText(BASIN_GIVES)
        outlet.setToolTip(EDIT_TIPS[OUTLET])
        outlet.editingFinished.connect(partial(self._outlet_changed, name, outlet))
        self.table.setCellWidget(number, OUTLET, outlet)

    def _set_edit(self, name: str, key: str, value) -> None:
        edit = {**self._edits.get(name, {}), key: value}
        edit = entry_rows.clean(edit)
        if edit:
            self._edits[name] = edit
        else:
            self._edits.pop(name, None)

    def _area_changed(self, name: str, value: float) -> None:
        self._set_edit(name, "storm_area_km2", value if value > 0.0 else None)

    def _entry_changed(self, name: str, combo: QComboBox, _index: int) -> None:
        self._set_edit(name, "entry", combo.currentData())

    def _outlet_changed(self, name: str, cell: QLineEdit) -> None:
        held = self._edits.get(name, {}).get("outlet")
        if cell.text().strip() == entry_rows.outlet_text(held):  # what it showed: the point to the last digit stays
            self._edit_problems.pop(name, None)
            cell.setStyleSheet("")
            return
        try:
            outlet = entry_rows.parse_outlet(cell.text(), name)
        except ValueError as problem:
            self._edit_problems[name] = str(problem)
            cell.setStyleSheet(f"color: {REFUSED_COLOUR}")
            cell.setToolTip(str(problem))
            return
        self._edit_problems.pop(name, None)
        cell.setStyleSheet("")
        cell.setToolTip(EDIT_TIPS[OUTLET])
        self._set_edit(name, "outlet", outlet)

    def subbasin_edits(self) -> dict[str, dict]:
        """The edits of the subbasins the table shows, on an HMS project; none on a generated basin."""
        if not self._use_hms():
            return {}
        shown = set(self._subbasin_modes())
        return {name: edit for name, edit in entry_rows.clean_all(self._edits).items() if name in shown}

    def entry_problems(self) -> list[str]:
        return list(self._edit_problems.values()) if self._use_hms() else []

    def set_edits(self, edits: dict) -> None:
        """Every subbasin's edit at once, the cells shown again."""
        self._edits = {name: dict(edit) for name, edit in entry_rows.clean_all(edits).items()}
        self._edit_problems = {}
        for number in range(self.table.rowCount()):
            self._edit_cells(number, self.table.item(number, NAME).text())

    # The saved model (W99): the generated basin is a file, and the mode of each subbasin a table of cell widgets.

    def extra_state(self) -> dict:
        return {
            "basin_json": self.basin.json_path,
            "modes": self._subbasin_modes(),
            "edits": entry_rows.clean_all(self._edits),  # W103, format 5
        }

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
        edits = extra.get("edits")
        if edits is not None:  # a model from before format 5 holds none: the cells keep what the reset left
            self.set_edits(edits)
            lost = sorted(set(entry_rows.clean_all(edits)) - set(self._subbasin_modes()))
            if lost and self._use_hms():
                found.append(f"storm areas, entries or outlets of subbasins no longer in the basin: {', '.join(lost)}")
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
            "cn_override": self.cn_override(),
            "inflows": self.inflows.rows(),  # W103: written only when there are rows
            "entry_problems": self.entry_problems(),
        }
        if values["reach_routing"] == MUSKINGUM:
            values["muskingum"] = self.muskingum.values()
        if self._use_hms():
            hms = {key: combo.currentText() for key, combo in self.files.items()}
            values["hms"] = {
                **hms, "folder": self.folder.filePath(), "modes": self._subbasin_modes(), "edits": self.subbasin_edits(),
            }  # fmt: skip
            values["lumped_entry"] = self.lumped_entry.currentData() if self.lumped_entry.isEnabled() else None
            values["lumped_only"] = self.lumped_only.isChecked() and self.lumped_only.isEnabled()
        elif self.basin.isChecked():
            values["basin"] = {**self.basin.values(crs), "modes": self._subbasin_modes()}
        return values
