# Wadi2D QGIS plugin. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""8. Run: where the results go, estimate, run, stop, and what is happening now."""

from __future__ import annotations

from qgis.gui import QgsFileWidget
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QWidget,
)

from ..job_builder import (
    ANIMATION_MAP_S,
    BACKEND,
    BACKEND_TIP,
    BACKEND_WORDS,
    DURATION,
    MAP_EVERY,
    PIXELS_ON,
    SECONDS_PER_HOUR,
    SMOOTH_ON,
    SMOOTH_TIP,
)
from .common import Section, bind, number_box

COLOURS = {"info": "#444444", "note": "#a06000", "good": "#1a7a30", "bad": "#b00020"}
MAPS_NOTE = (
    "Peak depth and hazard do not need the shorter interval: the run keeps its own peaks. It takes three times "
    "the disk, so choose it for an animation. Estimate says how much."
)
BACKGROUNDS = (("Hillshade of the DEM", "hillshade"), ("Satellite (needs internet; check the licence)", "satellite"))


SECONDS_PER_MINUTE = 60.0


class RunSection(Section):
    heading = "8. Run"

    def build(self) -> None:
        self.folder = QgsFileWidget()
        self.folder.setStorageMode(QgsFileWidget.GetDirectory)
        self.folder.setDialogTitle("Output folder")
        self.duration = number_box(2)
        self.maps = QComboBox()
        self.maps_note = self._text_label()
        self.maps_note.setText(MAPS_NOTE)
        self.pixels = QCheckBox("Make pixel depth and hazard maps after the run")
        self.pixels.setChecked(True)
        self.smooth = QCheckBox("Smooth map polygons and depth picture (slower)")
        self.smooth.setChecked(False)
        self.smooth.setToolTip(SMOOTH_TIP)
        self._smooth_default = False
        self.pixels.toggled.connect(self._pixels_toggled)
        self.backend = QComboBox()
        self.backend.setToolTip(BACKEND_TIP)
        self._backend_default: str | None = None
        self.estimate_button = QPushButton("Estimate")
        self.run_button = QPushButton("Run")
        self.stop_button = QPushButton("Stop")
        self.stop_button.setEnabled(False)
        self.estimate_label = self._text_label()
        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.status = self._text_label()
        self.message = self._text_label()
        self.open_button = QPushButton("Open results folder")
        self.open_button.hide()
        self.background = QComboBox()
        for label, value in BACKGROUNDS:
            self.background.addItem(label, value)
        self.map_title = QLineEdit()
        self.map_title.setPlaceholderText("The name of the run")
        self.map_button = QPushButton("Make map")
        self.map_button.setEnabled(False)
        self.map_button.setToolTip(
            "Three A3 sheets from the last finished run: setup, depth, hazard, as a PDF. A run that made no smooth "
            "polygons and depth picture has them made first, from its pixel rasters"
        )
        self.frames_button = QPushButton("Time slider")
        self.frames_button.setEnabled(False)
        self.frames_button.setToolTip("The saved frames of the last finished run as one layer that moves with the Temporal Controller")
        self.pixel_frames_button = QPushButton("Time slider at the pixel")
        self.pixel_frames_button.setEnabled(False)
        self.pixel_frames_button.setToolTip(
            "The saved frames of the last finished run drawn at the terrain pixel for what is on screen, as RAS Mapper "
            "draws them: nothing is written per frame"
        )
        self.lines_button = QPushButton("Result lines")
        self.lines_button.setEnabled(False)
        self.lines_button.setToolTip("Hydrograph, depth and water surface on a line: upfront ones, or one drawn now over the saved frames")
        self.workbook_button = QPushButton("Dam workbook...")
        self.workbook_button.setToolTip(
            "The dam-site Excel workbook from finished runs, one per return period: inflow, and outflow where a "
            "reservoir routes, at the dams and design lines you tick"
        )

        buttons = QWidget()
        row = QHBoxLayout(buttons)
        row.setContentsMargins(0, 0, 0, 0)
        for button in (self.estimate_button, self.run_button, self.stop_button):
            row.addWidget(button)
        self.form.addRow("Output folder", self.folder)
        self.form.addRow("Simulated time, h", self.duration)
        self.form.addRow("Save maps", self.maps)
        self.form.addRow(self.maps_note)
        self.form.addRow(self.pixels)
        self.form.addRow(self.smooth)
        self.form.addRow("Engine", self.backend)
        self.form.addRow(buttons)
        self.form.addRow(self.estimate_label)
        self.form.addRow(self.bar)
        self.form.addRow(self.status)
        self.form.addRow(self.message)
        self.form.addRow(self.open_button)
        self.form.addRow("Map title", self.map_title)
        self.form.addRow("Map background", self.background)
        self.form.addRow(self.map_button)
        self.form.addRow(self.frames_button)
        self.form.addRow(self.pixel_frames_button)
        self.form.addRow(self.lines_button)
        self.form.addRow(self.workbook_button)

    @staticmethod
    def _text_label() -> QLabel:
        label = QLabel()
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        return label

    def apply_schema(self, schema) -> None:
        bind(self.duration, schema, DURATION, scale=1.0 / SECONDS_PER_HOUR)
        usual = schema.default(MAP_EVERY, 0.0)
        self.maps.clear()
        self.maps.addItem(f"Every {usual / SECONDS_PER_MINUTE:g} minutes, for design work", usual)
        self.maps.addItem(f"Every {ANIMATION_MAP_S / SECONDS_PER_MINUTE:g} minutes, for an animation", ANIMATION_MAP_S)
        self.maps.setToolTip(schema.tip(MAP_EVERY))
        self.pixels.setChecked(bool(schema.default(PIXELS_ON, True)))
        self.pixels.setToolTip(schema.tip(PIXELS_ON))
        self._smooth_default = bool(schema.default(SMOOTH_ON, False))
        self.smooth.setChecked(self._smooth_default)
        self._backend_default = schema.default(BACKEND)
        held = self.backend.currentData()
        self.backend.clear()
        for key in schema.enum(BACKEND):
            self.backend.addItem(BACKEND_WORDS.get(key, key), key)
        wanted = held if held is not None else self._backend_default
        self.backend.setCurrentIndex(max(self.backend.findData(wanted), 0))

    def chosen_backend(self) -> str | None:
        """The engine the user chose, or None for the engine's own default."""
        key = self.backend.currentData()
        return key if key is not None and key != self._backend_default else None

    def _pixels_toggled(self, on: bool) -> None:
        """The polygons and the picture are drawn from the pixel maps: none without them."""
        self.smooth.setEnabled(on and self.pixels.isEnabled())

    def chosen_smooth(self) -> bool | None:
        """Whether the run draws its polygons and depth picture, or None for the engine's own default."""
        wanted = self.smooth.isChecked() and self.pixels.isChecked()
        return wanted if wanted != self._smooth_default else None

    def values(self, crs) -> dict:
        return {
            "output": self.folder.filePath(),
            "duration_h": self.duration.value(),
            "map_every_s": self.maps.currentData(),
            "pixels": self.pixels.isChecked(),
            "smooth": self.chosen_smooth(),
            "backend": self.chosen_backend(),
        }

    def set_running(self, running: bool) -> None:
        self.run_button.setEnabled(not running)
        self.estimate_button.setEnabled(not running)
        self.folder.setEnabled(not running)
        self.stop_button.setEnabled(running)
        if running:
            self.frames_button.setEnabled(False)
            self.pixel_frames_button.setEnabled(False)
            self.lines_button.setEnabled(False)
        self.maps.setEnabled(not running)
        self.pixels.setEnabled(not running)
        self.smooth.setEnabled(not running and self.pixels.isChecked())
        self.backend.setEnabled(not running)
        if running:
            self.map_button.setEnabled(False)
            self.bar.setValue(0)
            self.open_button.hide()

    def show_state(self, state) -> None:
        self.bar.setValue(state.percent)
        self.status.setText(state.status)

    def say(self, text: str, tone: str = "info") -> None:
        self.message.setStyleSheet(f"color: {COLOURS[tone]};")
        self.message.setText(text)
