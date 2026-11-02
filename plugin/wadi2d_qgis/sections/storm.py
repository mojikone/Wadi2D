# Wadi2D QGIS plugin. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""4. Storm: what falls. The same rain reaches the 2D cells and the lumped subbasins."""

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

from ..job_builder import MINUTES_PER_HOUR, RAIN_DEPTH, RAIN_DURATION
from ..storm_rows import KIND_DESIGN, KIND_GRID, KIND_HMS, KIND_STEADY, KIND_TABLE, pasted_rows, rain_text
from .common import Section, bind, number_box

RAIN_UNITS = "storm.rain_units"
RAIN_STAMP = "storm.rain_stamp"
RAIN_INTERVAL = "storm.rain_interval_min"
RAIN_FILES = "Rain files (*.nc *.nc4 *.cdf *.netcdf *.dss);;All files (*)"
KINDS = (
    (KIND_STEADY, "Steady rain"),
    (KIND_TABLE, "Hyetograph table"),
    (KIND_DESIGN, "Design storm with area reduction"),
    (KIND_GRID, "Gridded rain: NetCDF, DSS, GeoTIFF folder"),
)
HMS_CHOICE = (KIND_HMS, "As in the HMS project")
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


class StormSection(Section):
    heading = "4. Storm"
    rain_file_changed = pyqtSignal()
    """The rain file or how it is read has changed: ask the engine what it holds."""

    def build(self) -> None:
        self.kind = QComboBox()
        self.form.addRow("Rain", self.kind)
        self.pages = QStackedWidget()
        self.form.addRow(self.pages)
        self._page_of: dict[str, int] = {}
        self._add_page(KIND_HMS, QLabel("The storm of the HMS meteorologic file, with its area reduction."))
        self._add_page(KIND_STEADY, self._steady_page())
        self._add_page(KIND_TABLE, self._table_page())
        self._add_page(KIND_DESIGN, self._design_page())
        self._add_page(KIND_GRID, self._grid_page())
        self._fill_kinds(False)
        self.kind.currentIndexChanged.connect(self._kind_changed)
        self._kind_changed()

    def _add_page(self, kind: str, page: QWidget) -> None:
        self._page_of[kind] = self.pages.addWidget(page)

    def _steady_page(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        form.setContentsMargins(0, 0, 0, 0)
        self.rain = number_box(1)
        self.hours = number_box(2)
        form.addRow("Rain, mm/h", self.rain)
        form.addRow("Lasting, hours", self.hours)
        return page

    def _table_page(self) -> QWidget:
        self.hyetograph = PairTable("End of period, min", "Depth in it, mm")
        return self.hyetograph

    def _design_page(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        form.setContentsMargins(0, 0, 0, 0)
        self.design_depth = number_box(1)
        self.design_hours = number_box(2)
        self.pattern = PairTable("Time, % of duration", "Depth, % of total")
        self.storm_area = number_box(1)
        self.storm_area.setToolTip("The area at which the reduction table is read")
        self.arf = PairTable("Area, km2", "Reduction factor")
        form.addRow("Point depth, mm", self.design_depth)
        form.addRow("Duration, hours", self.design_hours)
        form.addRow(self.pattern)
        form.addRow("Storm area, km2", self.storm_area)
        form.addRow(self.arf)
        return page

    def _grid_page(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        form.setContentsMargins(0, 0, 0, 0)
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
        self.rain_label = QLabel("")
        self.rain_label.setWordWrap(True)
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

    def _fill_kinds(self, with_hms: bool) -> None:
        held = self.kind.currentData()
        self.kind.blockSignals(True)
        self.kind.clear()
        for key, words in ((HMS_CHOICE, *KINDS) if with_hms else KINDS):
            self.kind.addItem(words, key)
        wanted = KIND_HMS if with_hms and held in (None, KIND_STEADY) else held
        index = self.kind.findData(wanted)
        self.kind.setCurrentIndex(max(index, 0))
        self.kind.blockSignals(False)
        self._kind_changed()

    def hms_changed(self, in_use: bool) -> None:
        """An HMS project brings its own storm, which can still be replaced from here."""
        self._fill_kinds(in_use)

    def _kind_changed(self) -> None:
        self.pages.setCurrentIndex(self._page_of[self.kind.currentData()])

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

    def grid_values(self) -> dict:
        count = self.variable.count()
        return {
            "kind": KIND_GRID,
            "file": self.rain_file.filePath(),
            "variable": self.variable.currentText() if count > 1 else "",
            "choices": [self.variable.itemText(n) for n in range(count)] if count > 1 else [],
            "units": self.units.currentText(),
            "interval_min": self.period.value(),
            "stamp": self.stamp.currentData(),
            "start": self.start.text().strip(),
        }

    def values(self, crs) -> dict:
        kind = self.kind.currentData()
        if kind == KIND_HMS:
            return {}
        if kind == KIND_STEADY:
            steady = {"rain_mm_h": self.rain.value(), "rain_hours": self.hours.value()}
            if self.kind.findData(KIND_HMS) < 0:
                return steady
            return {"storm": {"kind": kind, "mm_h": self.rain.value(), "hours": self.hours.value()}}
        if kind == KIND_TABLE:
            return {"storm": {"kind": kind, "rows": self.hyetograph.rows()}}
        if kind == KIND_DESIGN:
            storm = {
                "kind": kind,
                "depth_mm": self.design_depth.value(),
                "hours": self.design_hours.value(),
                "pattern": self.pattern.rows(),
                "area_km2": self.storm_area.value(),
                "arf": self.arf.rows(),
            }
            return {"storm": storm}
        return {"storm": self.grid_values()}
