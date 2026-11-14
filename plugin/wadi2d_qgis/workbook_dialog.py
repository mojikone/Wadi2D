# Wadi2D QGIS plugin. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""The dam workbook dialog (W60 in the dock): one finished run, or one depth-area study's folder (W74), per return period,
the elements with the name of each one's sheet, the target period.

The engine writes the workbook (``wadi2d workbook``); this side only asks for what it needs and says where it went.
"""

from __future__ import annotations

from pathlib import Path

from qgis.gui import QgsFileWidget
from qgis.PyQt.QtCore import Qt, QUrl
from qgis.PyQt.QtGui import QDesktopServices
from qgis.PyQt.QtWidgets import (
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from . import settings
from .engine_process import EngineQuery
from .protocol import engine_error_text, exit_message
from .workbook_rows import (
    DEFAULT_TARGET,
    WORKBOOK_FILE,
    WORKBOOK_TIMEOUT_S,
    common_elements,
    workbook_args,
    workbook_problems,
    workbook_reply,
)

PERIOD_COLUMN, RUN_COLUMN = range(2)
ELEMENT_COLUMN, SHEET_COLUMN = range(2)
TITLE = "Wadi2D dam workbook"


class WorkbookDialog(QDialog):
    """``first_run`` fills the first row; the rest the user adds, one finished run per return period."""

    def __init__(self, first_run: Path | None = None, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(TITLE)
        self.query: EngineQuery | None = None
        self.written: str | None = None
        self.runs = QTableWidget(0, 2)
        self.runs.setHorizontalHeaderLabels(["Return period", "Finished run or depth-area study folder"])
        self.runs.horizontalHeader().setSectionResizeMode(RUN_COLUMN, QHeaderView.Stretch)
        self.runs.verticalHeader().hide()
        self.add_button = QPushButton("Add run...")
        self.remove_button = QPushButton("Remove run")
        self.elements = QTableWidget(0, 2)
        self.elements.setHorizontalHeaderLabels(["Element", "Sheet name"])
        self.elements.horizontalHeader().setSectionResizeMode(SHEET_COLUMN, QHeaderView.Stretch)
        self.elements.verticalHeader().hide()
        self.elements.setToolTip(
            "Dams, reservoirs and design lines every run wrote a series of; ticked ones get a sheet, named as typed in "
            "Sheet name (the element's own name until changed)"
        )
        self.target = QLineEdit(DEFAULT_TARGET)
        self.target.setToolTip("The return period of the side-by-side sheet: 200yr, 100yr, PMP ...")
        self.project = QLineEdit()
        self.project.setPlaceholderText("named in the titles, e.g. Block 02")
        self.out = QgsFileWidget()
        self.out.setStorageMode(QgsFileWidget.SaveFile)
        self.out.setFilter("Excel workbook (*.xlsx)")
        self.write_button = QPushButton("Write workbook")
        self.open_button = QPushButton("Open it")
        self.open_button.hide()
        self.message = QLabel()
        self.message.setWordWrap(True)
        self.message.setTextInteractionFlags(Qt.TextSelectableByMouse)

        buttons = QHBoxLayout()
        buttons.addWidget(self.add_button)
        buttons.addWidget(self.remove_button)
        buttons.addStretch(1)
        form = QFormLayout()
        form.addRow("Element sheets", self.elements)
        form.addRow("Target return period", self.target)
        form.addRow("Project", self.project)
        form.addRow("Workbook", self.out)
        column = QVBoxLayout(self)
        column.addWidget(QLabel("One finished run, or one depth-area study's folder, per return period, each with the same elements (2yr ... 10000yr or PMP)."))
        column.addWidget(self.runs)
        column.addLayout(buttons)
        column.addLayout(form)
        row = QHBoxLayout()
        row.addWidget(self.write_button)
        row.addWidget(self.open_button)
        row.addStretch(1)
        column.addLayout(row)
        column.addWidget(self.message)

        self.add_button.clicked.connect(self.pick_run)
        self.remove_button.clicked.connect(self.remove_run)
        self.write_button.clicked.connect(self.write)
        self.open_button.clicked.connect(self.open_workbook)
        self.runs.itemChanged.connect(lambda *_: self.refresh_elements())
        if first_run is not None:
            self.add_run(str(first_run))
            self.out.setFilePath(str(Path(first_run).parent / WORKBOOK_FILE))
        self.resize(640, 520)

    def add_run(self, folder: str, period: str = "") -> None:
        number = self.runs.rowCount()
        self.runs.blockSignals(True)
        self.runs.insertRow(number)
        self.runs.setItem(number, PERIOD_COLUMN, QTableWidgetItem(period))
        path = QTableWidgetItem(folder)
        path.setFlags(path.flags() & ~Qt.ItemIsEditable)
        self.runs.setItem(number, RUN_COLUMN, path)
        self.runs.blockSignals(False)
        self.refresh_elements()

    def pick_run(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "A finished run or a depth-area study folder", settings.last_folder())
        if folder:
            self.add_run(folder)

    def remove_run(self) -> None:
        number = self.runs.currentRow()
        self.runs.removeRow(number if number >= 0 else self.runs.rowCount() - 1)
        self.refresh_elements()

    def rows(self) -> list[tuple[str, str]]:
        out = []
        for number in range(self.runs.rowCount()):
            period, run = self.runs.item(number, PERIOD_COLUMN), self.runs.item(number, RUN_COLUMN)
            out.append((period.text() if period else "", run.text() if run else ""))
        return out

    def refresh_elements(self) -> None:
        """The elements every run has; a ticked element keeps its tick and the sheet name typed for it."""
        ticked, sheets = set(self.chosen()), self.sheets()
        self.elements.setRowCount(0)
        for number, name in enumerate(common_elements([run for _rp, run in self.rows()])):
            self.elements.insertRow(number)
            item = QTableWidgetItem(name)
            item.setFlags((item.flags() | Qt.ItemIsUserCheckable) & ~Qt.ItemIsEditable)
            item.setCheckState(Qt.Checked if name in ticked else Qt.Unchecked)
            self.elements.setItem(number, ELEMENT_COLUMN, item)
            self.elements.setItem(number, SHEET_COLUMN, QTableWidgetItem(sheets.get(name, name)))
        self.elements.resizeColumnToContents(ELEMENT_COLUMN)

    def _element_rows(self):
        for number in range(self.elements.rowCount()):
            element, sheet = self.elements.item(number, ELEMENT_COLUMN), self.elements.item(number, SHEET_COLUMN)
            if element is not None:
                yield element, (sheet.text() if sheet is not None else element.text())

    def chosen(self) -> list[str]:
        return [element.text() for element, _sheet in self._element_rows() if element.checkState() == Qt.Checked]

    def sheets(self) -> dict[str, str]:
        """Each listed element's sheet name as typed."""
        return {element.text(): sheet for element, sheet in self._element_rows()}

    def say(self, text: str) -> None:
        self.message.setText(text)

    def write(self) -> None:
        rows, elements, target, out = self.rows(), self.chosen(), self.target.text(), self.out.filePath()
        sheets = self.sheets()
        found = workbook_problems(rows, elements, target, out, sheets)
        if found:
            self.say(" ".join(found))
            return
        self.write_button.setEnabled(False)
        self.open_button.hide()
        self.say("Writing the workbook...")
        self.query = EngineQuery(settings.engine_text(), self)
        self.query.done.connect(self._written)
        args = workbook_args(rows, elements, target, out, self.project.text().strip(), sheets)
        self.query.start(args, WORKBOOK_TIMEOUT_S)

    def _written(self, code: int, out: str, err: str) -> None:
        self.query = None
        self.write_button.setEnabled(True)
        path = workbook_reply(out) if code == 0 else None
        if path is None:
            self.say(f"The workbook was not written. {exit_message(code)} {engine_error_text(err)}".strip())
            return
        self.written = path
        self.open_button.show()
        self.say(f"Workbook written: {path}")

    def open_workbook(self) -> None:
        if self.written:
            QDesktopServices.openUrl(QUrl.fromLocalFile(self.written))
