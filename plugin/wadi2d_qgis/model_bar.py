# Wadi2D QGIS plugin. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""The Model box at the top of the dock: open a finished run into the dock, save the model as a named scenario, open
one. It holds widgets and words only; :mod:`model_store` does the work (W99)."""

from __future__ import annotations

from qgis.gui import QgsCollapsibleGroupBox, QgsFileWidget
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import QComboBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QWidget

HEADING = "Model: saved with the QGIS project"
SAVED_NOTE = (
    "Everything in this dock is saved with the QGIS project and comes back when the project opens. A run keeps its "
    "own copy in its folder; a scenario is a named copy in the output folder."
)
RUN_TIP = (
    "A finished run's folder: the dock is refilled with the model that made it. A run from before the model was "
    "saved has only its job, so the dock takes what the job can tell and lists the rest."
)
IMPORT_TIP = (
    "A job file the dock did not write, a script's or the engine's config.resolved.json: the dock takes every field "
    "it has a control for, writes the job's lines and polygons into a GeoPackage in the output folder, and lists by "
    "section what it cannot hold yet"
)
SCENARIO_TIP = "A named copy of the model, kept in the scenarios folder inside the output folder"
NO_SCENARIOS = "No scenario saved yet"


def _row(*widgets) -> QWidget:
    holder = QWidget()
    line = QHBoxLayout(holder)
    line.setContentsMargins(0, 0, 0, 0)
    for number, widget in enumerate(widgets):
        line.addWidget(widget, 1 if number == 0 else 0)
    return holder


class ModelBar(QgsCollapsibleGroupBox):
    def __init__(self) -> None:
        super().__init__(HEADING)
        self.setSaveCollapsedState(False)
        form = QFormLayout(self)
        form.setRowWrapPolicy(QFormLayout.WrapLongRows)
        self.saved_note = QLabel(SAVED_NOTE)
        self.saved_note.setWordWrap(True)
        self.run_folder = QgsFileWidget()
        self.run_folder.setStorageMode(QgsFileWidget.GetDirectory)
        self.run_folder.setDialogTitle("Folder of a finished run")
        self.run_folder.setToolTip(RUN_TIP)
        self.open_run_button = QPushButton("Open run")
        self.open_run_button.setToolTip(RUN_TIP)
        self.import_button = QPushButton("Import a job...")  # W101: a job the dock did not write
        self.import_button.setToolTip(IMPORT_TIP)
        self.scenario_name = QLineEdit()
        self.scenario_name.setPlaceholderText("Name of the scenario")
        self.scenario_name.setToolTip(SCENARIO_TIP)
        self.save_button = QPushButton("Save as scenario")
        self.scenarios = QComboBox()
        self.scenarios.setToolTip(SCENARIO_TIP)
        self.open_button = QPushButton("Open scenario")
        self.message = QLabel()
        self.message.setWordWrap(True)
        self.message.setTextInteractionFlags(Qt.TextSelectableByMouse)
        form.addRow(self.saved_note)
        form.addRow("Open a run", _row(self.run_folder, self.open_run_button))
        form.addRow(self.import_button)
        form.addRow("Save", _row(self.scenario_name, self.save_button))
        form.addRow("Open", _row(self.scenarios, self.open_button))
        form.addRow(self.message)
        self.setCollapsed(True)
        self.show_scenarios([])

    def show_scenarios(self, found: list[tuple[str, object]]) -> None:
        """The scenarios of the model's folder, the one shown kept where it still exists."""
        held = self.scenarios.currentText()
        self.scenarios.clear()
        for name, path in found:
            self.scenarios.addItem(name, str(path))
        if not found:
            self.scenarios.addItem(NO_SCENARIOS, None)
        self.scenarios.setCurrentIndex(max(self.scenarios.findText(held), 0))
        self.open_button.setEnabled(bool(found))

    def say(self, text: str) -> None:
        self.message.setText(text)
        if text:
            self.setCollapsed(False)
