# Wadi2D QGIS plugin. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""4. Storm: what falls. The same rain reaches the 2D cells and the lumped subbasins.

One Rain source and only its fields (W65, his word of 2026-11-14), the sources of his redesign since W101: a fixed
depth, a depth and a pattern, a depth grid and a pattern, a gridded file (DSS, NetCDF or GeoTIFFs), the rain gauges, a
hyetograph as received, and the HMS project's meteorologic file when one is loaded. Patterns are uniform, the four
NRCS 24-hour curves (HEC-HMS's own tables, W98) or a pattern of Data tables. The area reduction is its own section
since W101 (4b), with a lumped and a 2D part. Preview rain asks the engine what each lumped subbasin and the 2D area
take.
"""

from __future__ import annotations

from qgis.core import QgsMapLayerProxyModel
from qgis.gui import QgsFileWidget
from qgis.PyQt.QtCore import pyqtSignal
from qgis.PyQt.QtWidgets import (
    QComboBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QStackedWidget,
    QWidget,
)

from .. import section_status
from ..gauge_rows import GAP_WORDS, INVERSE_DISTANCE, METHOD_WORDS, RAIN, VALUE_WORDS, GaugeRow
from ..job_builder import MINUTES_PER_HOUR, RAIN_DEPTH, RAIN_DURATION, raster_path
from ..rain_chart import HyetographChart, PreviewTable
from ..storm_rows import (
    KIND_DEPTH,
    KIND_DEPTH_GRID,
    KIND_FIXED,
    KIND_GAUGES,
    KIND_GRID,
    KIND_HMS,
    KIND_TABLE,
    preview_text,
    rain_text,
)
from ..table_rows import PATTERN_CHOICES, SCS, SCS_HOURS, TABLE_PREFIX
from .common import Section, bind, layer_combo, number_box
from .gauge_table import GaugeTable
from .pair_table import PairTable

RAIN_UNITS = "storm.rain_units"
RAIN_STAMP = "storm.rain_stamp"
RAIN_INTERVAL = "storm.rain_interval_min"
RAIN_FILES = "Rain files (*.nc *.nc4 *.cdf *.netcdf *.dss);;All files (*)"
SOURCES = (
    (KIND_FIXED, "Fixed depth, uniform in time"),
    (KIND_DEPTH, "Depth and pattern"),
    (KIND_DEPTH_GRID, "Depth grid (a raster of mm) and pattern"),
    (KIND_GRID, "Gridded rain: DSS, NetCDF or GeoTIFFs"),
    (KIND_GAUGES, "Rain gauges"),
    (KIND_TABLE, "A hyetograph, as received"),
)
HMS_CHOICE = (KIND_HMS, "The HMS meteorologic file")
GAUGES_NOTE = (
    "Each gauge's record spread over the cells and the lumped subbasins by the method below, as received: gauged rain "
    "has no area reduction. Flow and level gauges, to compare a run with, are in the Gauges section (7b). Records "
    "written with dates are read from the run's start, in the Simulation section."
)
POSITION_TIP = "x, y in the DEM's coordinates; a gauge from the points layer stands at its point."
RADIUS_DECIMALS = 0
STAMP_WORDS = {"end": "closes its period", "start": "opens its period"}
DEPTH_DECIMALS = 3
REDUCTION_NOTE = "The area reduction of a depth, a depth grid and a grid of point depths is set in section 4b."
PATTERN_NOTE = (
    "Uniform falls at a constant rate; an SCS type is the NRCS 24-hour curve, so the duration is 24 h; a pattern of "
    "Data tables (section 3b) is stretched over the duration when its times are in percent or a fraction of it."
)


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
    key = "storm"
    state_rows = (("gauge_table", GaugeRow, "_show"),)
    state_hold = ("variable", "depth_pattern", "grid_pattern")
    """The series of a rain file, which the engine reads and answers later; a pattern of Data tables, which may be
    restored after this section."""
    state_skip = ("start", "gauge_start", "rain")
    """The run's one start is the Simulation section's widget (W99); ``rain`` is the Steady rain's mm/h, which older
    dock checks still set and a saved model no longer holds (W101)."""
    rain_file_changed = pyqtSignal()
    """The rain file or how it is read has changed: ask the engine what it holds."""
    preview_requested = pyqtSignal()
    """Preview rain: the dock writes the job and asks the engine."""
    source_changed = pyqtSignal(str)
    """The rain source: the area reduction follows it (W101)."""

    def build(self) -> None:
        self._hms_in_use = False
        self._legacy_rate = False
        self._syncing = False
        self.start = self.gauge_start = QLineEdit()  # a section used alone; in the dock, the run's one start
        self.kind = QComboBox()
        self.kind.setToolTip("Where the rain comes from; only the chosen source's fields are shown")
        self.form.addRow("Rain source", self.kind)
        self.pages = QStackedWidget()
        self.form.addRow(self.pages)
        self._page_of: dict[str, int] = {}
        self._add_page(KIND_HMS, _words("The storm of the HMS meteorologic file, with its area reduction. Preview "
                                        "rain shows what it puts on each subbasin."))  # fmt: skip
        self._add_page(KIND_FIXED, self._fixed_page())
        self._add_page(KIND_DEPTH, self._depth_page())
        self._add_page(KIND_DEPTH_GRID, self._depth_grid_page())
        self._add_page(KIND_GRID, self._grid_page())
        self._add_page(KIND_GAUGES, self._gauges_page())
        self._add_page(KIND_TABLE, self._table_page())
        self.reduction_note = _words(REDUCTION_NOTE)
        self.form.addRow(self.reduction_note)
        self.form.addRow(self._preview_block())
        self._fill_kinds(False)
        self.kind.currentIndexChanged.connect(self._kind_changed)
        self._kind_changed()

    def set_start_field(self, field) -> None:
        """The run's one start, which the gridded rain and the rain gauges read (W99): the Simulation section's
        field takes the place of the two "Run starts at" fields that sat here. A rain file is read again when it
        changes, as it was for the field of the gridded rain."""
        self.start = self.gauge_start = field
        field.editingFinished.connect(self._reading_changed)

    def _add_page(self, kind: str, page: QWidget) -> None:
        self._page_of[kind] = self.pages.addWidget(page)

    # The pages

    def _fixed_page(self) -> QWidget:
        """A depth over a duration at a constant rate. ``rain`` is the Steady rain's mm/h, out of sight: an older check
        that sets it, with ``hours``, gets the depth it gave before, to the last digit."""
        page, form = _page()
        self.fixed_depth = number_box(DEPTH_DECIMALS)
        self.hours = number_box(2)
        self.rain = number_box(1)
        form.addRow("Depth, mm", self.fixed_depth)
        form.addRow("Over, hours", self.hours)
        form.addRow(self.rain)
        self.rain.hide()
        form.addRow(_words("The same depth on every cell and every lumped subbasin, at a constant rate, before the "
                           "area reduction of section 4b."))  # fmt: skip
        self.rain.valueChanged.connect(self._rate_set)
        self.hours.valueChanged.connect(self._hours_set)
        self.fixed_depth.valueChanged.connect(self._depth_set)
        return page

    def _rate_set(self, *_) -> None:
        self._legacy_rate = True
        self._sync_depth()

    def _hours_set(self, *_) -> None:
        if self._legacy_rate:
            self._sync_depth()

    def _depth_set(self, *_) -> None:
        if not self._syncing:
            self._legacy_rate = False

    def _sync_depth(self) -> None:
        self._syncing = True
        self.fixed_depth.setValue(self.rain.value() * self.hours.value())
        self._syncing = False

    def fixed_depth_mm(self) -> float:
        """The depth a fixed rain gives: the Steady rain's mm/h times its hours when that was set last."""
        return self.rain.value() * self.hours.value() if self._legacy_rate else self.fixed_depth.value()

    def restore_extra(self, extra: dict, add_missing: bool = False) -> list[str]:
        """A saved model holds the depth itself: the Steady rain's mm/h, if an older check set it, no longer counts."""
        self._legacy_rate = False
        self.rain.blockSignals(True)  # so that an older check's next mm/h is taken, whatever it was before
        self.rain.setValue(0.0)
        self.rain.blockSignals(False)
        return []

    def _pattern_combo(self) -> QComboBox:
        combo = QComboBox()
        for key, words in PATTERN_CHOICES:
            combo.addItem(words, key)
        combo.setToolTip(PATTERN_NOTE)
        return combo

    def _depth_page(self) -> QWidget:
        page, form = _page()
        self.depth_mm = number_box(DEPTH_DECIMALS)
        self.depth_hours = number_box(2)
        self.depth_pattern = self._pattern_combo()
        form.addRow("Depth, mm", self.depth_mm)
        form.addRow("Duration, hours", self.depth_hours)
        form.addRow("Pattern", self.depth_pattern)
        form.addRow(_words(PATTERN_NOTE))
        self.depth_pattern.currentIndexChanged.connect(lambda *_: self._scs_hours(self.depth_pattern, self.depth_hours))
        return page

    def _depth_grid_page(self) -> QWidget:
        page, form = _page()
        self.depth_raster = layer_combo(QgsMapLayerProxyModel.RasterLayer, "Choose the raster of depths, mm")
        self.grid_hours = number_box(2)
        self.grid_pattern = self._pattern_combo()
        form.addRow("Depth grid, mm", self.depth_raster)
        form.addRow("Duration, hours", self.grid_hours)
        form.addRow("Pattern", self.grid_pattern)
        form.addRow(_words("Each 2D cell takes the depth under its centre, each lumped subbasin the mean over its "
                           "polygon, as HEC-HMS's gridded depth does. " + PATTERN_NOTE))  # fmt: skip
        self.grid_pattern.currentIndexChanged.connect(lambda *_: self._scs_hours(self.grid_pattern, self.grid_hours))
        return page

    @staticmethod
    def _scs_hours(combo: QComboBox, hours) -> None:
        """An NRCS curve is a 24-hour storm: its duration is set, and set back by hand if wanted."""
        if (combo.currentData() or "").startswith(f"{SCS}:"):
            hours.setValue(SCS_HOURS)

    def set_patterns(self, patterns: dict) -> None:
        """The patterns of Data tables after the four of every model; the choice held where it still is."""
        for combo in (self.depth_pattern, self.grid_pattern):
            held = combo.currentData() or combo.currentText()
            combo.blockSignals(True)
            combo.clear()
            for key, words in PATTERN_CHOICES:
                combo.addItem(words, key)
            for name in sorted(patterns):
                combo.addItem(f"{name} (Data tables)", f"{TABLE_PREFIX}{name}")
            index = combo.findData(held)
            if index < 0 and held:
                index = combo.findText(held)
            if index < 0 and held and str(held).startswith(TABLE_PREFIX):  # gone from Data tables: kept, and named
                combo.addItem(f"{held[len(TABLE_PREFIX) :]} (not in Data tables)", held)
                index = combo.count() - 1
            combo.setCurrentIndex(max(index, 0))
            combo.blockSignals(False)

    def _table_page(self) -> QWidget:
        page, form = _page()
        self.hyetograph = PairTable("End of period, min", "Depth in it, mm")
        form.addRow(self.hyetograph)
        form.addRow(_words("The same rain on every cell and every lumped subbasin, as received: no area reduction."))
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
        self.rain_label = _words("")
        form.addRow("Source", self.is_folder)
        form.addRow("Rain file", self.rain_file)
        form.addRow("Series", self.variable)
        form.addRow("Units", self.units)
        form.addRow("Period, min", self.period)
        form.addRow("A time with no period", self.stamp)
        form.addRow(self.rain_label)
        self.is_folder.currentIndexChanged.connect(self._source_changed)
        self.rain_file.fileChanged.connect(self._file_changed)
        for signal in (self.variable.activated, self.units.activated, self.stamp.activated):
            signal.connect(self._reading_changed)
        self.period.editingFinished.connect(self._reading_changed)
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
        form.addRow(_words(GAUGES_NOTE))
        form.addRow(self.gauge_table)
        form.addRow("Rain spread by", self.gauge_method)
        form.addRow("Search radius, m", self.gauge_radius)
        form.addRow("A gauge with no value", self.gauge_gaps)
        form.addRow("A rain CSV holds", self.gauge_values)
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
        for box in (self.fixed_depth, self.depth_mm):
            bind(box, schema, RAIN_DEPTH)
        for box in (self.hours, self.depth_hours, self.grid_hours):
            bind(box, schema, RAIN_DURATION, scale=1.0 / MINUTES_PER_HOUR)
        self._legacy_rate = False
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
        if held in (None, KIND_FIXED) and with_hms:
            wanted = KIND_HMS
        elif held is None or (held == KIND_HMS and not with_hms):
            wanted = KIND_FIXED
        else:
            wanted = held
        self.kind.setCurrentIndex(max(self.kind.findData(wanted), 0))
        self.kind.blockSignals(False)
        self._kind_changed()

    def hms_changed(self, in_use: bool) -> None:
        """An HMS project brings its own storm, which can still be replaced from here, and its reduction table."""
        self._hms_in_use = in_use
        self._fill_kinds(in_use)

    def _kind_changed(self, *_) -> None:
        source = self.kind.currentData()
        self.pages.setCurrentIndex(self._page_of[source])
        self.reduction_note.setVisible(source in (KIND_FIXED, KIND_DEPTH, KIND_DEPTH_GRID, KIND_GRID))
        self.preview_label.clear()
        self.preview_table.hide()
        self.preview_chart.hide()
        self.source_changed.emit(source or "")

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

    def standing(self, kind=None):
        source = self.kind.currentData()
        if source == KIND_GAUGES:  # its rows as they stand: reading its values redraws the table
            return section_status.storm(source, {}, self._hms_in_use, len(self.gauge_table.rows))
        return section_status.storm(source, {} if source == KIND_HMS else self.values(None), self._hms_in_use)

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
        source = self.kind.currentData()
        if source == KIND_HMS:
            return {}
        if source == KIND_FIXED:
            return {"storm": {"kind": KIND_FIXED, "depth_mm": self.fixed_depth_mm(), "hours": self.hours.value()}}
        if source == KIND_DEPTH:
            storm = {
                "kind": KIND_DEPTH, "depth_mm": self.depth_mm.value(), "hours": self.depth_hours.value(),
                "pattern": self.depth_pattern.currentData(),
            }  # fmt: skip
            return {"storm": storm}
        if source == KIND_DEPTH_GRID:
            storm = {
                "kind": KIND_DEPTH_GRID, "raster": raster_path(self.depth_raster.currentLayer()) or "",
                "hours": self.grid_hours.value(), "pattern": self.grid_pattern.currentData(),
            }  # fmt: skip
            return {"storm": storm}
        if source == KIND_TABLE:
            return {"storm": {"kind": KIND_TABLE, "rows": self.hyetograph.rows()}}
        if source == KIND_GAUGES:
            return {"storm": {"kind": KIND_GAUGES}, "rain_gauges": self.gauge_values_of(crs)}
        return {"storm": self.grid_values()}
