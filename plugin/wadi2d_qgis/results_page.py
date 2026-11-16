# Wadi2D QGIS plugin. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""The results page of a finished run (W101 item 6): its maps and tools, its elements of record, and runs compared.

Widgets only; :mod:`results_links` fills them and answers their clicks, :mod:`results_rows` holds the rules. The map
tools are the Run section's own buttons, laid out here by the dock, so a check that clicks them finds them as before.
"""

from __future__ import annotations

from qgis.gui import QgsFileWidget
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from . import look
from .line_plot import LinePlot
from .results_rows import COLUMNS, KIND_WORDS

PIN_COLUMN = 0
HEADERS = ("Pin", *COLUMNS)
ROWS_SHOWN = 10
PIN_TIP = "Pinned elements come first whatever the filter, and are saved with the project"
CHART_TIP = "Click a row for its hydrograph chart, with the rain bar where the run has one"


def _words() -> QLabel:
    label = QLabel()
    label.setWordWrap(True)
    label.setTextInteractionFlags(Qt.TextSelectableByMouse)
    return label


def _table(columns) -> QTableWidget:
    table = QTableWidget(0, len(columns))
    table.setHorizontalHeaderLabels(list(columns))
    table.verticalHeader().hide()
    table.setEditTriggers(QAbstractItemView.NoEditTriggers)
    table.setSelectionBehavior(QAbstractItemView.SelectRows)
    table.setSelectionMode(QAbstractItemView.SingleSelection)
    table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
    table.setMinimumHeight(ROWS_SHOWN * 24)
    table.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)  # the dock's width, the table scrolls inside it
    return table


class ResultsPage(QScrollArea):
    def __init__(self) -> None:
        super().__init__()
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        body = QWidget()
        column = QVBoxLayout(body)
        column.setContentsMargins(look.PAD, look.GAP, look.PAD, look.GAP)
        column.setSpacing(look.GAP)

        top = QHBoxLayout()
        self.back_button = QPushButton("\N{SINGLE LEFT-POINTING ANGLE QUOTATION MARK} Model")
        self.back_button.setToolTip("Back to the model's sections")
        self.title = QLabel()
        self.title.setWordWrap(True)
        top.addWidget(self.back_button)
        top.addWidget(self.title, 1)
        column.addLayout(top)

        self.tools_box = QGroupBox("Maps and tools")
        self.tools = QVBoxLayout(self.tools_box)
        column.addWidget(self.tools_box)

        self.elements_box = QGroupBox("Elements of record")
        elements = QVBoxLayout(self.elements_box)
        row = QHBoxLayout()
        self.kind = QComboBox()
        for key, words in KIND_WORDS.items():
            self.kind.addItem(words, key)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search by name")
        self.search.setClearButtonEnabled(True)
        row.addWidget(self.kind, 1)
        row.addWidget(self.search, 1)
        elements.addLayout(row)
        self.table = _table(HEADERS)
        self.table.setToolTip(CHART_TIP)
        self.table.horizontalHeaderItem(PIN_COLUMN).setToolTip(PIN_TIP)
        elements.addWidget(self.table)
        self.words = _words()
        elements.addWidget(self.words)
        column.addWidget(self.elements_box)

        self.compare_box = QGroupBox("Compare runs")
        compare = QVBoxLayout(self.compare_box)
        self.runs = QListWidget()
        self.runs.setToolTip("The runs beside this one, and any added; tick the ones to compare")
        self.runs.setMaximumHeight(110)
        compare.addWidget(self.runs)
        self.add_run = QgsFileWidget()
        self.add_run.setStorageMode(QgsFileWidget.GetDirectory)
        self.add_run.setDialogTitle("Folder of another finished run")
        add = QHBoxLayout()
        add.addWidget(QLabel("Add a run"))
        add.addWidget(self.add_run, 1)
        compare.addLayout(add)
        buttons = QHBoxLayout()
        self.compare_button = QPushButton("Compare")
        self.export_button = QPushButton("Export the table to Excel...")
        self.export_button.setEnabled(False)
        buttons.addWidget(self.compare_button)
        buttons.addWidget(self.export_button)
        compare.addLayout(buttons)
        self.compare_table = _table(("Element", "Kind"))
        self.compare_table.setToolTip("Click a row for its hydrographs of every run on one chart")
        compare.addWidget(self.compare_table)
        self.plot = LinePlot()
        self.plot.setMinimumSize(0, 300)  # the Result lines panel's plot asks 900 px: here it takes the dock's width
        compare.addWidget(self.plot)
        self.compare_words = _words()
        compare.addWidget(self.compare_words)
        column.addWidget(self.compare_box)
        column.addStretch(1)
        self.setWidget(body)

    def _fit(self) -> None:
        """The page as wide as the dock: tables and the chart scroll or squeeze inside it. Left to the scroll area, a
        page shown after the dock changed width kept the width it was laid out at (W101's checks)."""
        body = self.widget()
        if body is not None:
            body.setFixedWidth(max(self.viewport().width(), body.minimumSizeHint().width()))

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._fit()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._fit()


__all__ = ["HEADERS", "PIN_COLUMN", "ResultsPage"]
