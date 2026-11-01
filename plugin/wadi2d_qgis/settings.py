# Wadi2D QGIS plugin. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""The plugin's few saved settings, and the one-field dialog that says where the engine is."""

from __future__ import annotations

from qgis.core import QgsSettings
from qgis.PyQt.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)

from .engine_process import EngineQuery
from .protocol import DEFAULT_ENGINE

ENGINE_KEY = "wadi2d/engine"
LAST_RUN_KEY = "wadi2d/last_run"
LAST_FOLDER_KEY = "wadi2d/last_folder"


def engine_text() -> str:
    return QgsSettings().value(ENGINE_KEY, DEFAULT_ENGINE, type=str)


def set_engine_text(text: str) -> None:
    QgsSettings().setValue(ENGINE_KEY, text)


def last_run() -> str:
    return QgsSettings().value(LAST_RUN_KEY, "", type=str)


def set_last_run(folder: str) -> None:
    QgsSettings().setValue(LAST_RUN_KEY, folder)


def last_folder() -> str:
    return QgsSettings().value(LAST_FOLDER_KEY, "", type=str)


def set_last_folder(folder: str) -> None:
    QgsSettings().setValue(LAST_FOLDER_KEY, folder)


class EngineDialog(QDialog):
    """The path of the Python or ``wadi2d`` executable, checked with ``wadi2d doctor``."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Wadi2D engine")
        self.resize(560, 320)
        self.path = QLineEdit(engine_text())
        self.report = QPlainTextEdit()
        self.report.setReadOnly(True)
        self.check_button = QPushButton("Check engine")
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Python or wadi2d executable, with its arguments"))
        layout.addWidget(self.path)
        layout.addWidget(self.check_button)
        layout.addWidget(self.report)
        layout.addWidget(buttons)
        self.check_button.clicked.connect(self.check)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        self._query: EngineQuery | None = None

    def check(self) -> None:
        self.check_button.setEnabled(False)
        self.report.setPlainText("Checking...")
        self._query = EngineQuery(self.path.text(), self)
        self._query.done.connect(self._checked)
        self._query.start(["doctor"])

    def _checked(self, code: int, out: str, err: str) -> None:
        self.check_button.setEnabled(True)
        verdict = "Engine found." if code == 0 else "This engine does not answer."
        self.report.setPlainText("\n".join(part for part in (verdict, out.strip(), err.strip()) if part))

    def accept(self) -> None:
        set_engine_text(self.path.text().strip())
        super().accept()
