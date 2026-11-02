# Wadi2D QGIS plugin. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""6. Run: where the results go, estimate, run, stop, and what is happening now."""

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

from ..job_builder import ANIMATION_MAP_S, DURATION, MAP_EVERY, PIXELS_ON, SECONDS_PER_HOUR
from .common import Section, bind, number_box

COLOURS = {"info": "#444444", "note": "#a06000", "good": "#1a7a30", "bad": "#b00020"}
MAPS_NOTE = (
    "Peak depth and hazard do not need the shorter interval: the run keeps its own peaks. It takes three times "
    "the disk, so choose it for an animation. Estimate says how much."
)
BACKGROUNDS = (("Hillshade of the DEM", "hillshade"), ("Satellite (needs internet; check the licence)", "satellite"))


SECONDS_PER_MINUTE = 60.0


class RunSection(Section):
    heading = "6. Run"

    def build(self) -> None:
        self.folder = QgsFileWidget()
        self.folder.setStorageMode(QgsFileWidget.GetDirectory)
        self.folder.setDialogTitle("Output folder")
        self.duration = number_box(2)
        self.maps = QComboBox()
        self.maps_note = self._text_label()
        self.maps_note.setText(MAPS_NOTE)
        self.pixels = QCheckBox("Make pixel depth, hazard and their drawing after the run")
        self.pixels.setChecked(True)
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
        self.map_button.setToolTip("Three A3 sheets from the last finished run: setup, depth, hazard, as a PDF")

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
        self.form.addRow(buttons)
        self.form.addRow(self.estimate_label)
        self.form.addRow(self.bar)
        self.form.addRow(self.status)
        self.form.addRow(self.message)
        self.form.addRow(self.open_button)
        self.form.addRow("Map title", self.map_title)
        self.form.addRow("Map background", self.background)
        self.form.addRow(self.map_button)

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

    def values(self, crs) -> dict:
        return {
            "output": self.folder.filePath(),
            "duration_h": self.duration.value(),
            "map_every_s": self.maps.currentData(),
            "pixels": self.pixels.isChecked(),
        }

    def set_running(self, running: bool) -> None:
        self.run_button.setEnabled(not running)
        self.estimate_button.setEnabled(not running)
        self.folder.setEnabled(not running)
        self.stop_button.setEnabled(running)
        self.maps.setEnabled(not running)
        self.pixels.setEnabled(not running)
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
