# Wadi2D QGIS plugin. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""6. Run: where the results go, estimate, run, stop, and what is happening now."""

from __future__ import annotations

from qgis.gui import QgsFileWidget
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import QHBoxLayout, QLabel, QProgressBar, QPushButton, QWidget

from ..job_builder import DURATION, SECONDS_PER_HOUR
from .common import Section, bind, number_box

COLOURS = {"info": "#444444", "note": "#a06000", "good": "#1a7a30", "bad": "#b00020"}


class RunSection(Section):
    heading = "6. Run"

    def build(self) -> None:
        self.folder = QgsFileWidget()
        self.folder.setStorageMode(QgsFileWidget.GetDirectory)
        self.folder.setDialogTitle("Output folder")
        self.duration = number_box(2)
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

        buttons = QWidget()
        row = QHBoxLayout(buttons)
        row.setContentsMargins(0, 0, 0, 0)
        for button in (self.estimate_button, self.run_button, self.stop_button):
            row.addWidget(button)
        self.form.addRow("Output folder", self.folder)
        self.form.addRow("Simulated time, h", self.duration)
        self.form.addRow(buttons)
        self.form.addRow(self.estimate_label)
        self.form.addRow(self.bar)
        self.form.addRow(self.status)
        self.form.addRow(self.message)
        self.form.addRow(self.open_button)

    @staticmethod
    def _text_label() -> QLabel:
        label = QLabel()
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        return label

    def apply_schema(self, schema) -> None:
        bind(self.duration, schema, DURATION, scale=1.0 / SECONDS_PER_HOUR)

    def values(self, crs) -> dict:
        return {"output": self.folder.filePath(), "duration_h": self.duration.value()}

    def set_running(self, running: bool) -> None:
        self.run_button.setEnabled(not running)
        self.estimate_button.setEnabled(not running)
        self.folder.setEnabled(not running)
        self.stop_button.setEnabled(running)
        if running:
            self.bar.setValue(0)
            self.open_button.hide()

    def show_state(self, state) -> None:
        self.bar.setValue(state.percent)
        self.status.setText(state.status)

    def say(self, text: str, tone: str = "info") -> None:
        self.message.setStyleSheet(f"color: {COLOURS[tone]};")
        self.message.setText(text)
