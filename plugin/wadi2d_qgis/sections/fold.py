# Wadi2D QGIS plugin. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""A heading that opens and closes the rows under it: a section's Advanced settings, closed until asked for (W101).

Its own button holds no setting, so a saved model holds what the rows hold, never whether the fold was open.
"""

from __future__ import annotations

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import QFormLayout, QToolButton, QVBoxLayout, QWidget


class Fold(QWidget):
    def __init__(self, title: str) -> None:
        super().__init__()
        self.button = QToolButton()
        self.button.setText(title)
        self.button.setCheckable(True)
        self.button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.button.setArrowType(Qt.RightArrow)
        self.button.setStyleSheet("QToolButton { border: none; font-weight: bold; }")
        self.body = QWidget()
        self.form = QFormLayout(self.body)
        self.form.setRowWrapPolicy(QFormLayout.WrapLongRows)
        self.form.setContentsMargins(12, 0, 0, 0)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.button)
        layout.addWidget(self.body)
        self.body.setVisible(False)
        self.button.toggled.connect(self._toggled)

    def _toggled(self, on: bool) -> None:
        self.button.setArrowType(Qt.DownArrow if on else Qt.RightArrow)
        self.body.setVisible(on)

    def set_open(self, on: bool) -> None:
        self.button.setChecked(on)

    def is_open(self) -> bool:
        return self.button.isChecked()


def show_row(form: QFormLayout, widget: QWidget, on: bool) -> None:
    """A row of a form laid out with or without a label, shown or hidden whole."""
    label = form.labelForField(widget)
    if label is not None:
        label.setVisible(on)
    widget.setVisible(on)
