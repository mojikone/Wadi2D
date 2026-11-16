# Wadi2D QGIS plugin. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""9. Depth-area study: one 2D run per storm area, and a design flow for each design line and lumped element at its
own drainage area.

Everything above it makes the job, with Run's output folder and engine; this section adds the storm areas and runs
the study. It never adds anything to a plain run's job.
"""

from __future__ import annotations

from qgis.core import QgsMapLayerProxyModel
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QWidget,
)

from ..job_builder import raster_path
from ..study_rows import (
    AREA_COUNT,
    AREA_MAX,
    AREA_MIN,
    ARF_STEP,
    ARF_STEP_MAX,
    BRACKET,
    BRACKET_MAX,
    BRACKET_RATIO,
    COLUMNS,
    LISTED,
    SPACED,
    UNIT_WORDS,
    UNITS,
    areas_text,
    arf_step_areas,
    arf_step_text,
    form_problems,
    on_grid_text,
    study_areas,
    table_cells,
)
from .common import Section, bind, layer_combo, number_box
from .run import COLOURS

SPACINGS = (
    (BRACKET, "Around the drainage areas"),
    (SPACED, "Log-spaced between two areas"),
    (LISTED, "Listed"),
    (ARF_STEP, "By the change of area reduction"),
)
ARF_STEP_TIP = (
    "Largest change of the area reduction factor between neighbouring storm-area runs, as a fraction: 0.05 lets it go "
    "from 0.987 to 0.937 between two runs. The runs span the design lines' drainage areas, as few as keep every step "
    "within it, in equal steps."
)
INTRO = (
    "One 2D run per storm area, the storm's depth read from its area reduction table at that area, on lumped and 2D "
    "parts alike. Each design line then reads log Q against log A between the two runs either side of its own drainage "
    "area. It uses everything above, with the output folder and the engine of Run, and writes beside the output folder."
)
LINES_TIP = (
    "Hydrograph, depth and water surface on a line drawn or picked now, read from the two runs either side of its "
    "own drainage area, as the study reads its design points"
)
LISTED_TIP = "Storm areas in km2, separated by commas or spaces, as 10, 30, 90"
ACCUMULATION_TIP = (
    "Each cell's drainage area: a line drawn or picked after the study reads the two runs either side of its own "
    "area, and the composite map reads it per cell. None: such a line reads the smallest run alone."
)
COMPOSITE_TIP = (
    "Experimental: each cell of the depth, speed and hazard maps reads the two runs either side of its own drainage "
    "area, from a flow accumulation raster. Off until a composite map has been checked."
)


class StudySection(Section):
    heading = "9. Depth-area study (optional)"
    start_collapsed = True
    key = "study"

    def build(self) -> None:
        intro = self._text_label()
        intro.setText(INTRO)
        self.spacing = QComboBox()
        for key, words in SPACINGS:
            self.spacing.addItem(words, key)
        self.count = QSpinBox()
        self.smallest = number_box(1)
        self.largest = number_box(1)
        self.spaced_box = QWidget()
        spaced = QFormLayout(self.spaced_box)
        spaced.setContentsMargins(0, 0, 0, 0)
        spaced.addRow("Number of areas", self.count)
        spaced.addRow("Smallest, km2", self.smallest)
        spaced.addRow("Largest, km2", self.largest)
        self.listed = QLineEdit()
        self.listed.setPlaceholderText("10, 30, 90")
        self.listed.setToolTip(LISTED_TIP)
        self.listed_box = QWidget()
        listed = QFormLayout(self.listed_box)
        listed.setContentsMargins(0, 0, 0, 0)
        listed.addRow("Areas, km2", self.listed)
        self.arf_step = number_box(3)
        self.arf_step.setRange(0.001, 0.999)
        self.arf_step.setSingleStep(0.01)
        self.arf_step.setValue(0.05)
        self.arf_step.setToolTip(ARF_STEP_TIP)
        self.arf_step_box = QWidget()
        stepped = QFormLayout(self.arf_step_box)
        stepped.setContentsMargins(0, 0, 0, 0)
        stepped.addRow("Largest ARF change between runs", self.arf_step)
        self.context = lambda: None
        """The dock's values the ARF-step rule needs, design lines and storm; None when they cannot be read."""
        self.areas_label = self._text_label()
        self._ratio, self._most = 2.0, 6

        self.composite = QCheckBox("Composite map (experimental)")
        self.composite.setToolTip(COMPOSITE_TIP)
        self.accumulation = layer_combo(QgsMapLayerProxyModel.RasterLayer, "None")
        self.accumulation.setToolTip(ACCUMULATION_TIP)
        self.units = QComboBox()
        self.accumulation_box = QWidget()
        accumulation = QFormLayout(self.accumulation_box)
        accumulation.setContentsMargins(0, 0, 0, 0)
        accumulation.addRow("Flow accumulation", self.accumulation)
        accumulation.addRow("Its values are", self.units)

        self.start_button = QPushButton("Start study")
        self.stop_button = QPushButton("Stop study")
        self.stop_button.setEnabled(False)
        buttons = QWidget()
        row = QHBoxLayout(buttons)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(self.start_button)
        row.addWidget(self.stop_button)
        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.status = self._text_label()
        self.message = self._text_label()
        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(list(COLUMNS))
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.verticalHeader().hide()
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.hide()
        self.file_label = self._text_label()
        self.open_button = QPushButton("Open study folder")
        self.open_button.hide()
        self.lines_button = QPushButton("Result lines")
        self.lines_button.setToolTip(LINES_TIP)
        self.lines_button.hide()

        self.form.addRow(intro)
        self.form.addRow("Storm areas", self.spacing)
        self.form.addRow(self.spaced_box)
        self.form.addRow(self.listed_box)
        self.form.addRow(self.arf_step_box)
        self.form.addRow(self.areas_label)
        self.form.addRow(self.accumulation_box)
        self.form.addRow(self.composite)
        self.form.addRow(buttons)
        self.form.addRow(self.bar)
        self.form.addRow(self.status)
        self.form.addRow(self.message)
        self.form.addRow(self.table)
        self.form.addRow(self.file_label)
        self.form.addRow(self.open_button)
        self.form.addRow(self.lines_button)

        self.spacing.currentIndexChanged.connect(self._spacing_changed)
        for box in (self.count, self.smallest, self.largest, self.arf_step):
            box.valueChanged.connect(self._refresh_areas)
        self.collapsedStateChanged.connect(self._refresh_areas)  # the design lines and the storm may have changed
        self.listed.textChanged.connect(self._refresh_areas)
        self._spacing_changed()

    @staticmethod
    def _text_label() -> QLabel:
        label = QLabel()
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        return label

    def apply_schema(self, schema) -> None:
        low, high = schema.bounds(AREA_COUNT)
        self.count.setRange(int(low or 2), int(high or 32))
        self.count.setValue(int(schema.default(AREA_COUNT, 6)))
        self.count.setToolTip(schema.tip(AREA_COUNT))
        bind(self.smallest, schema, AREA_MIN)
        bind(self.largest, schema, AREA_MAX)
        self._ratio = float(schema.default(BRACKET_RATIO, self._ratio))
        self._most = int(schema.default(BRACKET_MAX, self._most))
        bind(self.arf_step, schema, ARF_STEP_MAX)
        self.units.clear()
        for key in schema.enum(UNITS):
            self.units.addItem(UNIT_WORDS.get(key, key), key)
        self.units.setToolTip(schema.tip(UNITS))
        self._refresh_areas()

    def values(self, crs) -> dict:
        return {}  # a plain run takes nothing from here; the dock asks form_values() for a study

    def form_values(self) -> dict:
        return {
            "spacing": self.spacing.currentData(),
            "listed": self.listed.text(),
            "count": self.count.value(),
            "smallest": self.smallest.value(),
            "largest": self.largest.value(),
            "arf_step": self.arf_step.value(),
            "composite": self.composite.isChecked(),
            "accumulation": raster_path(self.accumulation.currentLayer()),
            "units": self.units.currentData(),
        }

    def _spacing_changed(self) -> None:
        kind = self.spacing.currentData()
        self.spaced_box.setVisible(kind == SPACED)
        self.listed_box.setVisible(kind == LISTED)
        self.arf_step_box.setVisible(kind == ARF_STEP)
        self._refresh_areas()

    def _refresh_areas(self, *_) -> None:
        form = {**self.form_values(), "composite": False}
        found = form_problems(form)
        if found:
            self.areas_label.setText(" ".join(found))
        elif form["spacing"] == ARF_STEP:
            values = self.context()
            areas = arf_step_areas(form, values) if values else None
            self.areas_label.setText(arf_step_text(areas, form["arf_step"]))
        else:
            self.areas_label.setText(areas_text(study_areas(form), self._ratio, self._most))

    def set_running(self, running: bool) -> None:
        self.start_button.setEnabled(not running)
        self.stop_button.setEnabled(running)
        widgets = (self.spacing, self.spaced_box, self.listed_box, self.arf_step_box, self.accumulation_box, self.composite)
        for widget in widgets:
            widget.setEnabled(not running)
        if running:
            self.bar.setValue(0)
            self.status.clear()
            self.table.hide()
            self.table.setRowCount(0)
            self.file_label.clear()
            self.open_button.hide()
            self.lines_button.hide()

    def show_state(self, state) -> None:
        self.bar.setValue(state.percent)
        self.status.setText(state.status)

    def say(self, text: str, tone: str = "info") -> None:
        self.message.setStyleSheet(f"color: {COLOURS[tone]};")
        self.message.setText(text)

    def show_table(self, rows: list[dict], table_type: str, on_grid: list[str], path) -> None:
        """The design flows, one row per design line and lumped element, and where the study wrote them."""
        self.table.setRowCount(len(rows))
        for number, row in enumerate(rows):
            for column, text in enumerate(table_cells(row)):
                item = QTableWidgetItem(text)
                if 0 < column < len(COLUMNS) - 1:
                    item.setTextAlignment(int(Qt.AlignRight | Qt.AlignVCenter))
                self.table.setItem(number, column, item)
        self.table.setVisible(bool(rows))
        words = [f"Written to {path}."]
        if table_type:
            words.append(f"Area reduction table: {table_type}.")
        if on_grid:
            words.append(on_grid_text(on_grid))
        self.file_label.setText(" ".join(words))
        self.open_button.show()
        self.lines_button.show()
