# Wadi2D QGIS plugin. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""4. Storm: what falls. The same rain reaches the 2D cells and the lumped subbasins.

One Rain source and only its fields (W65, his word of 2026-11-14): a design storm, a gridded file, the rain gauges, or
a single hyetograph for the whole model; the HMS project's storm when one is loaded. A design storm and a grid of point
depths share one area reduction block. Preview rain asks the engine what each lumped subbasin and the 2D area take.
"""

from __future__ import annotations

from qgis.gui import QgsFileWidget
from qgis.PyQt.QtCore import pyqtSignal
from qgis.PyQt.QtWidgets import (
    QApplication,
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QWidget,
)

from ..gauge_rows import GAP_WORDS, INVERSE_DISTANCE, METHOD_WORDS, RAIN, VALUE_WORDS
from ..job_builder import MINUTES_PER_HOUR, RAIN_DEPTH, RAIN_DURATION
from ..rain_chart import HyetographChart, PreviewTable
from ..storm_rows import (
    ARF_AREA,
    ARF_NONE,
    ARF_STUDY,
    KIND_DESIGN,
    KIND_GAUGES,
    KIND_GRID,
    KIND_HMS,
    KIND_STEADY,
    KIND_TABLE,
    SOURCE_SINGLE,
    pasted_rows,
    preview_text,
    rain_text,
)
from .common import Section, bind, number_box
from .gauge_table import GaugeTable

RAIN_UNITS = "storm.rain_units"
RAIN_STAMP = "storm.rain_stamp"
RAIN_INTERVAL = "storm.rain_interval_min"
RAIN_FILES = "Rain files (*.nc *.nc4 *.cdf *.netcdf *.dss);;All files (*)"
SOURCES = (
    (KIND_DESIGN, "Design storm with area reduction"),
    (KIND_GRID, "Gridded file with area reduction"),
    (KIND_GAUGES, "Rain gauges"),
    (SOURCE_SINGLE, "Single hyetograph"),
)
HMS_CHOICE = (KIND_HMS, "As in the HMS project")
REDUCED = (KIND_DESIGN, KIND_GRID)
"""The sources the area reduction block belongs to."""
ARF_CHOICES = (
    (ARF_NONE, "None"),
    (ARF_AREA, "At one storm area"),
    (ARF_STUDY, "By the depth-area study (section 9)"),
)
SINGLE_CHOICES = ((KIND_STEADY, "Constant rain"), (KIND_TABLE, "A table of periods"))
GAUGES_NOTE = (
    "Each gauge's record spread over the cells and the lumped subbasins by the method below, as received: gauged rain "
    "has no area reduction. Flow and level gauges, to compare a run with, are in the Gauges section (7b)."
)
POSITION_TIP = "x, y in the DEM's coordinates; a gauge from the points layer stands at its point."
RADIUS_DECIMALS = 0
STUDY_NOTE = (
    "The depth-area study reads the table at each of its storm areas, run by run. The storm area above is that of a "
    "single Run."
)
GRID_ARF_NOTE = "Leave it at None for observed rain: only grids of point depths are reduced."
HMS_TABLE_NOTE = "Left empty, the table of the HMS project is used."
STAMP_WORDS = {"end": "closes its period", "start": "opens its period"}
TABLE_ROWS = 8


class PairTable(QWidget):
    """A two-column table of numbers: add a row, drop one, or paste from a spreadsheet."""

    def __init__(self, first: str, second: str) -> None:
        super().__init__()
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels([first, second])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.verticalHeader().hide()
        self.table.setMinimumHeight(self.table.fontMetrics().height() * TABLE_ROWS)
        self.add_button = QPushButton("Add row")
        self.drop_button = QPushButton("Remove row")
        self.paste_button = QPushButton("Paste")
        self.paste_button.setToolTip("Two columns from a spreadsheet or a text file; a heading line is left out")
        buttons = QHBoxLayout()
        for button in (self.add_button, self.drop_button, self.paste_button):
            buttons.addWidget(button)
        column = QFormLayout(self)
        column.setContentsMargins(0, 0, 0, 0)
        column.addRow(self.table)
        column.addRow(buttons)
        self.add_button.clicked.connect(lambda: self.table.insertRow(self.table.rowCount()))
        self.drop_button.clicked.connect(self._drop)
        self.paste_button.clicked.connect(lambda: self.set_rows(pasted_rows(QApplication.clipboard().text())))

    def _drop(self) -> None:
        row = self.table.currentRow()
        self.table.removeRow(row if row >= 0 else self.table.rowCount() - 1)

    def set_rows(self, rows: list[tuple[float, ...]]) -> None:
        self.table.setRowCount(len(rows))
        for n, row in enumerate(rows):
            for m, value in enumerate(row):
                self.table.setItem(n, m, QTableWidgetItem(f"{value:g}"))

    def rows(self) -> list[tuple[float, float]]:
        """The filled rows; a cell that is not a number leaves its row out, and the check on the table says so."""
        found = []
        for row in range(self.table.rowCount()):
            cells = [self.table.item(row, m) for m in (0, 1)]
            text = [cell.text().strip() if cell is not None else "" for cell in cells]
            try:
                found.append((float(text[0]), float(text[1])))
            except ValueError:
                continue
        return found


def _page() -> tuple[QWidget, QFormLayout]:
    page = QWidget()
    form = QFormLayout(page)
    form.setContentsMargins(0, 0, 0, 0)
    return page, form


def _words(text: str) -> QLabel:
    label = QLabel(text)
    label.setWordWrap(True)
    return label


class StormSection(Section):
    heading = "4. Storm"
    rain_file_changed = pyqtSignal()
    """The rain file or how it is read has changed: ask the engine what it holds."""
    preview_requested = pyqtSignal()
    """Preview rain: the dock writes the job and asks the engine."""
    study_areas_requested = pyqtSignal()
    """The depth-area study's storm areas are wanted, read only."""

    def build(self) -> None:
        self._hms_in_use = False
        self.kind = QComboBox()
        self.kind.setToolTip("Where the rain comes from; only the chosen source's fields are shown")
        self.form.addRow("Rain source", self.kind)
        self.pages = QStackedWidget()
        self.form.addRow(self.pages)
        self._page_of: dict[str, int] = {}
        self._add_page(KIND_HMS, _words("The storm of the HMS meteorologic file, with its area reduction. Preview "
                                        "rain shows what it puts on each subbasin."))  # fmt: skip
        self._add_page(KIND_DESIGN, self._design_page())
        self._add_page(KIND_GRID, self._grid_page())
        self._add_page(KIND_GAUGES, self._gauges_page())
        self._add_page(SOURCE_SINGLE, self._single_page())
        self.reduction = self._reduction_block()
        self.form.addRow(self.reduction)
        self.form.addRow(self._preview_block())
        self._fill_kinds(False)
        self.kind.currentIndexChanged.connect(self._kind_changed)
        self._kind_changed()

    def _add_page(self, kind: str, page: QWidget) -> None:
        self._page_of[kind] = self.pages.addWidget(page)

    # The pages

    def _single_page(self) -> QWidget:
        page, form = _page()
        self.single = QComboBox()
        for key, words in SINGLE_CHOICES:
            self.single.addItem(words, key)
        self.single_pages = QStackedWidget()
        steady, steady_form = _page()
        self.rain = number_box(1)
        self.hours = number_box(2)
        steady_form.addRow("Rain, mm/h", self.rain)
        steady_form.addRow("Lasting, hours", self.hours)
        self.hyetograph = PairTable("End of period, min", "Depth in it, mm")
        self.single_pages.addWidget(steady)
        self.single_pages.addWidget(self.hyetograph)
        form.addRow("Rain", self.single)
        form.addRow(self.single_pages)
        form.addRow(_words("The same rain on every cell and every lumped subbasin, as received: no area reduction."))
        self.single.currentIndexChanged.connect(self.single_pages.setCurrentIndex)
        return page

    def _design_page(self) -> QWidget:
        page, form = _page()
        self.design_depth = number_box(1)
        self.design_hours = number_box(2)
        self.pattern = PairTable("Time, % of duration", "Depth, % of total")
        form.addRow("Point depth, mm", self.design_depth)
        form.addRow("Duration, hours", self.design_hours)
        form.addRow(self.pattern)
        return page

    def _grid_page(self) -> QWidget:
        page, form = _page()
        self.is_folder = QComboBox()
        self.is_folder.addItems(["A NetCDF or DSS file", "A folder of GeoTIFFs, one per period"])
        self.rain_file = QgsFileWidget()
        self.rain_file.setFilter(RAIN_FILES)
        self.rain_file.setDialogTitle("Rain file")
        self.variable = QComboBox()
        self.units = QComboBox()
        self.period = number_box(1)
        self.period.setSpecialValueText("As in the file")
        self.stamp = QComboBox()
        self.start = QLineEdit()
        self.start.setPlaceholderText("Start of the first period")
        self.start.setToolTip("Date and time the run starts at, as 2021-10-03 06:00; rain before it is left out")
        self.rain_label = _words("")
        form.addRow("Source", self.is_folder)
        form.addRow("Rain file", self.rain_file)
        form.addRow("Series", self.variable)
        form.addRow("Units", self.units)
        form.addRow("Period, min", self.period)
        form.addRow("A time with no period", self.stamp)
        form.addRow("Run starts at", self.start)
        form.addRow(self.rain_label)
        self.is_folder.currentIndexChanged.connect(self._source_changed)
        self.rain_file.fileChanged.connect(self._file_changed)
        for signal in (self.variable.activated, self.units.activated, self.stamp.activated):
            signal.connect(self._reading_changed)
        self.period.editingFinished.connect(self._reading_changed)
        self.start.editingFinished.connect(self._reading_changed)
        return page

    def _gauges_page(self) -> QWidget:
        """The rain gauges themselves (W77; W54 had them in the Gauges section) and how their rain is spread."""
        page, form = _page()
        self.gauge_table = GaugeTable((RAIN,), "Position, x, y", POSITION_TIP, points=True)
        self.gauge_method = QComboBox()
        for key, words in METHOD_WORDS.items():
            self.gauge_method.addItem(words, key)
        self.gauge_radius = number_box(RADIUS_DECIMALS)
        self.gauge_radius.setRange(0.0, 1e7)
        self.gauge_radius.setSpecialValueText("Every gauge")
        self.gauge_gaps = QComboBox()
        for key, words in GAP_WORDS.items():
            self.gauge_gaps.addItem(words, key)
        self.gauge_values = QComboBox()
        for key, words in VALUE_WORDS.items():
            self.gauge_values.addItem(words, key)
        self.gauge_start = QLineEdit()
        self.gauge_start.setPlaceholderText("Start of the first period of rain")
        self.gauge_start.setToolTip("Date and time the run starts at, as 2021-10-04 00:00, for records written with dates")
        form.addRow(_words(GAUGES_NOTE))
        form.addRow(self.gauge_table)
        form.addRow("Rain spread by", self.gauge_method)
        form.addRow("Search radius, m", self.gauge_radius)
        form.addRow("A gauge with no value", self.gauge_gaps)
        form.addRow("A rain CSV holds", self.gauge_values)
        form.addRow("Run starts at", self.gauge_start)
        self.gauge_method.currentIndexChanged.connect(self._method_changed)
        self._method_changed()
        return page

    def _method_changed(self, *_) -> None:
        self.gauge_radius.setEnabled(self.gauge_method.currentData() == INVERSE_DISTANCE)

    def gauge_values_of(self, crs) -> dict:
        """The rain gauges and their reading rules, as W54's Gauges section gave them."""
        rows = self.gauge_table.current_rows(crs)
        for row in rows:
            row.values = self.gauge_values.currentData()
        radius = self.gauge_radius.value()
        settings = {
            "method": self.gauge_method.currentData(),
            "radius_m": radius if radius > 0.0 else None,
            "gaps": self.gauge_gaps.currentData(),
            "start": self.gauge_start.text().strip(),
        }
        return {"rows": rows, "settings": settings}

    def _reduction_block(self) -> QWidget:
        """One area reduction for a design storm and a grid of point depths: none, at one area, or by the study."""
        block, form = _page()
        self.arf_mode = QComboBox()
        for key, words in ARF_CHOICES:
            self.arf_mode.addItem(words, key)
        self.arf_mode.setToolTip(
            "The factor multiplies every depth, on the 2D cells and the lumped subbasins alike"
        )
        self.arf_detail = QWidget()
        inner = QFormLayout(self.arf_detail)
        inner.setContentsMargins(0, 0, 0, 0)
        self.storm_area = number_box(3)
        self.storm_area.setRange(0.0, 1e7)
        self.storm_area.setToolTip("The area at which the reduction table is read: the design point's drainage area")
        self.arf = PairTable("Area, km2", "Reduction factor")
        self.hms_note = _words(HMS_TABLE_NOTE)
        self.study_label = _words("")
        inner.addRow("Storm area, km2", self.storm_area)
        inner.addRow(self.arf)
        inner.addRow(self.hms_note)
        inner.addRow(self.study_label)
        self.grid_note = _words(GRID_ARF_NOTE)
        form.addRow("Area reduction", self.arf_mode)
        form.addRow(self.grid_note)
        form.addRow(self.arf_detail)
        self.arf_mode.currentIndexChanged.connect(self._reduction_shown)
        return block

    def _preview_block(self) -> QWidget:
        block, form = _page()
        self.preview_button = QPushButton("Preview rain")
        self.preview_button.setToolTip(
            "What each lumped subbasin and the 2D area take, after the area reduction, from the engine; no run"
        )
        self.preview_label = _words("")
        self.preview_table = PreviewTable()
        self.preview_chart = HyetographChart()
        self.preview_table.hide()
        self.preview_chart.hide()
        form.addRow(self.preview_button)
        form.addRow(self.preview_label)
        form.addRow(self.preview_table)
        form.addRow(self.preview_chart)
        self.preview_button.clicked.connect(self.preview_requested.emit)
        self.preview_table.itemSelectionChanged.connect(self._preview_row)
        return block

    # Schema and the HMS project

    def apply_schema(self, schema) -> None:
        bind(self.rain, schema, RAIN_DEPTH)
        bind(self.hours, schema, RAIN_DURATION, scale=1.0 / MINUTES_PER_HOUR)
        bind(self.design_depth, schema, RAIN_DEPTH)
        bind(self.design_hours, schema, RAIN_DURATION, scale=1.0 / MINUTES_PER_HOUR)
        self.units.clear()
        self.units.addItems(schema.enum(RAIN_UNITS))
        self.stamp.clear()
        for key in schema.enum(RAIN_STAMP):
            self.stamp.addItem(STAMP_WORDS[key], key)
        self.units.setToolTip(schema.tip(RAIN_UNITS))
        self.stamp.setToolTip(schema.tip(RAIN_STAMP))
        self.period.setToolTip(schema.tip(RAIN_INTERVAL))
        self.period.setRange(0.0, 1e6)
        for path, widget in (
            ("storm.gauges.method", self.gauge_method), ("storm.gauges.search_radius_m", self.gauge_radius),
            ("storm.gauges.gaps", self.gauge_gaps),
        ):  # fmt: skip
            if schema.has(path):
                widget.setToolTip(schema.tip(path))

    def _fill_kinds(self, with_hms: bool) -> None:
        held = self.kind.currentData()
        self.kind.blockSignals(True)
        self.kind.clear()
        for key, words in ((HMS_CHOICE, *SOURCES) if with_hms else SOURCES):
            self.kind.addItem(words, key)
        if held in (None, SOURCE_SINGLE) and with_hms:
            wanted = KIND_HMS
        elif held is None or (held == KIND_HMS and not with_hms):
            wanted = SOURCE_SINGLE
        else:
            wanted = held
        self.kind.setCurrentIndex(max(self.kind.findData(wanted), 0))
        self.kind.blockSignals(False)
        self._kind_changed()

    def hms_changed(self, in_use: bool) -> None:
        """An HMS project brings its own storm, which can still be replaced from here, and its reduction table."""
        self._hms_in_use = in_use
        self._fill_kinds(in_use)

    def _kind_changed(self) -> None:
        source = self.kind.currentData()
        self.pages.setCurrentIndex(self._page_of[source])
        self.reduction.setVisible(source in REDUCED)
        self._reduction_shown()
        self.preview_label.clear()
        self.preview_table.hide()
        self.preview_chart.hide()

    def _reduction_shown(self) -> None:
        mode = self.arf_mode.currentData()
        grid = self.kind.currentData() == KIND_GRID
        self.arf_detail.setVisible(mode != ARF_NONE)
        self.grid_note.setVisible(grid and mode == ARF_NONE)
        self.hms_note.setVisible(grid and self._hms_in_use)
        self.study_label.setVisible(mode == ARF_STUDY)
        if mode == ARF_STUDY:
            self.study_label.setText(STUDY_NOTE)
            self.study_areas_requested.emit()

    def show_study_areas(self, text: str) -> None:
        """The study's storm areas, read only: they are set in section 9."""
        self.study_label.setText(f"{STUDY_NOTE} {text}".strip())

    # The rain file, through the engine

    def _source_changed(self) -> None:
        folder = self.is_folder.currentIndex() == 1
        self.rain_file.setStorageMode(QgsFileWidget.GetDirectory if folder else QgsFileWidget.GetFile)
        self.rain_file.setFilePath("")

    def _file_changed(self) -> None:
        self.variable.clear()
        self.rain_label.clear()
        self._reading_changed()

    def _reading_changed(self) -> None:
        if self.rain_file.filePath():
            self.rain_label.setText("Reading the rain file...")
            self.rain_file_changed.emit()

    def show_rain(self, info: dict) -> None:
        """What the engine found in the file."""
        held = self.variable.currentText()
        self.variable.clear()
        self.variable.addItems(info["choices"])
        if held in info["choices"]:
            self.variable.setCurrentText(held)
        self.rain_label.setText(rain_text(info))
        if not info["frames"] and len(info["choices"]) > 1 and held not in info["choices"]:
            self.variable.setCurrentIndex(-1)

    def show_rain_problem(self, text: str) -> None:
        self.rain_label.setText(text)

    # The preview, through the engine

    def say_preview(self, text: str, _tone: str = "info") -> None:
        self.preview_label.setText(text)

    def set_previewing(self, busy: bool) -> None:
        self.preview_button.setEnabled(not busy)
        if busy:
            self.preview_label.setText("Asking the engine what falls where...")

    def show_preview(self, preview: dict) -> None:
        self.preview_label.setText(preview_text(preview))
        self.preview_table.show_rows(preview["areas"])
        self.preview_table.setVisible(bool(preview["areas"]))
        self.preview_chart.setVisible(bool(preview["areas"]))
        self._preview_row()

    def _preview_row(self) -> None:
        rows = self.preview_table.rows
        picked = self.preview_table.currentRow()
        self.preview_chart.show_row(rows[picked] if 0 <= picked < len(rows) else None)

    # Values

    def _reduction(self) -> dict:
        mode = self.arf_mode.currentData()
        rows = self.arf.rows() if mode != ARF_NONE else []
        return {"arf_mode": mode, "area_km2": self.storm_area.value(), "arf": rows}

    def grid_values(self) -> dict:
        count = self.variable.count()
        reduction = self._reduction()
        return {
            "kind": KIND_GRID,
            "file": self.rain_file.filePath(),
            "variable": self.variable.currentText() if count > 1 else "",
            "choices": [self.variable.itemText(n) for n in range(count)] if count > 1 else [],
            "units": self.units.currentText(),
            "interval_min": self.period.value(),
            "stamp": self.stamp.currentData(),
            "start": self.start.text().strip(),
            "arf_on": reduction["arf_mode"] != ARF_NONE,
            "area_km2": reduction["area_km2"],
            "arf": reduction["arf"],
            "arf_from_hms": self._hms_in_use,
            "arf_mode": reduction["arf_mode"],
        }

    def values(self, crs) -> dict:
        source = self.kind.currentData()
        if source == KIND_HMS:
            return {}
        if source == SOURCE_SINGLE and self.single.currentData() == KIND_STEADY:
            steady = {"rain_mm_h": self.rain.value(), "rain_hours": self.hours.value()}
            if not self._hms_in_use:
                return steady
            return {"storm": {"kind": KIND_STEADY, "mm_h": self.rain.value(), "hours": self.hours.value()}}
        if source == SOURCE_SINGLE:
            return {"storm": {"kind": KIND_TABLE, "rows": self.hyetograph.rows()}}
        if source == KIND_DESIGN:
            storm = {
                "kind": KIND_DESIGN,
                "depth_mm": self.design_depth.value(),
                "hours": self.design_hours.value(),
                "pattern": self.pattern.rows(),
                **self._reduction(),
            }
            return {"storm": storm}
        if source == KIND_GAUGES:
            return {"storm": {"kind": KIND_GAUGES}, "rain_gauges": self.gauge_values_of(crs)}
        return {"storm": self.grid_values()}
