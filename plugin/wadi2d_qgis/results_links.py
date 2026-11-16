# Wadi2D QGIS plugin. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""The results page at work (W101 item 6): a run's elements of record listed, filtered, searched and pinned, each
opening its hydrograph chart; runs compared side by side, on one chart, and into Excel.

The engine reads the runs (``wadi2d lines``, W21: QGIS must not load a second HDF5 library); this side lists, keeps the
pins with the project and draws. The chart a row opens is the Result lines panel's (W21, W64), on that element.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from qgis.core import QgsProject
from qgis.PyQt.QtCore import QObject, Qt
from qgis.PyQt.QtWidgets import QListWidgetItem, QTableWidgetItem

from . import settings
from .engine_process import EngineQuery
from .layer_groups import model_name
from .line_view import FLOW_TITLE, UPFRONT, Chart, Curve, View
from .protocol import LINES_LIST, PROGRESS_FILE, engine_error_text, exit_message, lines_args
from .results_page import PIN_COLUMN
from .results_rows import ALL, KIND_WORDS, compare, default_kind, filtered, rows_of, write_table

SCOPE = "wadi2d"
PINS = "pinned/{model}"
"""The project entry of a model's pinned elements: one list per model, its runs share their element names."""
RESULTS_FILE = "results.h5"
COLOURS = ("#1a5f9a", "#c8560a", "#2e7d32", "#7b1fa2", "#b71c1c", "#00838f", "#5d4037", "#455a64")
EXPORT_NAME = "compare_runs.xlsx"


def run_job(run: Path) -> dict | None:
    """The run's job, ``job.json`` or the engine's ``config.resolved.json`` (W101), or None."""
    from .job_import import find_job

    found = find_job(run)
    try:
        return json.loads(found.read_text(encoding="utf-8")) if found is not None else None
    except (OSError, ValueError):
        return None


def is_run(folder: Path) -> bool:
    return (folder / RESULTS_FILE).is_file() and (folder / PROGRESS_FILE).is_file()


def sibling_runs(run: Path) -> list[Path]:
    """The finished runs beside a run, itself first: a model's runs land as numbered siblings (``next_run_dir``)."""
    parent = run.parent
    found = sorted((p for p in parent.iterdir() if p.is_dir() and p != run and is_run(p)), key=lambda p: p.name) if parent.is_dir() else []
    return [run, *found]


class ResultsLinks(QObject):
    def __init__(self, dock) -> None:
        super().__init__(dock)
        self.dock = dock
        self.page = page = dock.results_page
        self.run: Path | None = None
        self.rows: list = []
        self.shown: list = []
        self.listings: dict[str, list] = {}
        self.comparison = None
        self.query: EngineQuery | None = None
        self.queue: list[Path] = []
        self.folder = tempfile.mkdtemp(prefix="wadi2d_results_")
        self._filling = False
        page.back_button.clicked.connect(dock.types.show_model)
        page.kind.currentIndexChanged.connect(self.show_rows)
        page.search.textChanged.connect(self.show_rows)
        page.table.cellClicked.connect(self._clicked)
        page.table.itemChanged.connect(self._pin_changed)
        page.compare_button.clicked.connect(self.compare_runs)
        page.export_button.clicked.connect(self._export_asked)
        page.compare_table.cellClicked.connect(self._compared_clicked)
        page.add_run.fileChanged.connect(self._add_run)
        dock.panel.results_button.clicked.connect(lambda: self.open(dock.results_dir))

    # The run.

    def open(self, run: Path | str | None) -> None:
        """The page, on the run: its elements read by the engine, the runs beside it offered for comparison."""
        if run is None:
            return
        self.run = Path(run)
        self.dock.types.show_results()
        self.page.title.setText(f"Results of run {self.run.name}")
        self.page.words.setText("Reading the run's elements of record...")
        self.rows, self.listings, self.comparison = [], {}, None
        self.page.compare_table.setRowCount(0)
        self.page.plot.show_view(None)
        self.page.export_button.setEnabled(False)
        self.page.runs.clear()
        for folder in sibling_runs(self.run):
            self._offer(folder, folder == self.run)
        self._read(self.run, self._listed)

    def _offer(self, folder: Path, checked: bool) -> None:
        item = QListWidgetItem(folder.name)
        item.setData(Qt.UserRole, str(folder))
        item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
        item.setCheckState(Qt.Checked if checked else Qt.Unchecked)
        self.page.runs.addItem(item)

    def _add_run(self, path: str) -> None:
        folder = Path(path) if path else None
        if folder is None or not is_run(folder):
            if path:
                self.page.compare_words.setText(f"{path} holds no finished run.")
            return
        known = [self.page.runs.item(i).data(Qt.UserRole) for i in range(self.page.runs.count())]
        if str(folder) not in known:
            self._offer(folder, True)

    def _read(self, run: Path, then) -> None:
        out = Path(self.folder) / f"{len(self.listings)}_{run.name}_{LINES_LIST}"
        self.query = EngineQuery(settings.engine_text(), self)
        self.query.done.connect(lambda code, _out, err: self._answered(run, out, code, err, then))
        self.query.start(lines_args(run, out))

    def _answered(self, run: Path, out: Path, code: int, err: str, then) -> None:
        self.query = None
        if code != 0:
            words = f"Run {run.name} could not be read. {exit_message(code)} {engine_error_text(err)}".strip()
            then(run, None, words)
            return
        then(run, rows_of(json.loads(out.read_text(encoding="utf-8")), run_job(run)), "")

    def _listed(self, run: Path, rows, words: str) -> None:
        if rows is None:
            self.page.words.setText(words)
            return
        self.rows = rows
        self.listings[str(run)] = rows
        pinned = self.pinned()
        kind = ALL if pinned else default_kind(rows)
        self.page.kind.blockSignals(True)
        self.page.kind.setCurrentIndex(self.page.kind.findData(kind))
        self.page.kind.blockSignals(False)
        self.show_rows()

    # The list.

    def _model(self) -> str:
        return model_name(self.dock.panel.folder.filePath())

    def pinned(self) -> list[str]:
        found, _ok = QgsProject.instance().readListEntry(SCOPE, PINS.format(model=self._model()))
        return list(found or [])

    def set_pinned(self, keys: list[str]) -> None:
        QgsProject.instance().writeEntry(SCOPE, PINS.format(model=self._model()), keys)

    def show_rows(self, *_) -> None:
        pinned = self.pinned()
        self.shown = filtered(self.rows, self.page.kind.currentData(), self.page.search.text(), pinned)
        table = self.page.table
        self._filling = True
        table.setRowCount(len(self.shown))
        for number, row in enumerate(self.shown):
            pin = QTableWidgetItem()
            pin.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            pin.setCheckState(Qt.Checked if row.key in pinned else Qt.Unchecked)
            table.setItem(number, PIN_COLUMN, pin)
            for column, text in enumerate(row.cells(), start=1):
                item = QTableWidgetItem(text)
                if column > 2:
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                table.setItem(number, column, item)
        self._filling = False
        kind = KIND_WORDS[self.page.kind.currentData()].lower()
        words = f"{len(self.shown)} of {len(self.rows)} elements of record shown ({kind}"
        words += f", {len(pinned)} pinned first)." if pinned else ")."
        self.page.words.setText(words + " Click a row for its chart." if self.shown else words)

    def _pin_changed(self, item) -> None:
        if self._filling or item.column() != PIN_COLUMN or not 0 <= item.row() < len(self.shown):
            return
        key = self.shown[item.row()].key
        keys = [k for k in self.pinned() if k != key]
        if item.checkState() == Qt.Checked:
            keys.append(key)
        self.set_pinned(keys)
        self.show_rows()

    def _clicked(self, number: int, column: int) -> None:
        if column == PIN_COLUMN or not 0 <= number < len(self.shown):
            return
        self.open_chart(self.shown[number])

    def open_chart(self, row) -> None:
        """The element's hydrograph chart: the Result lines panel, on this run and this element."""
        self.dock.result_lines(self.run, row.entry.label)

    # Comparing runs.

    def checked_runs(self) -> list[Path]:
        runs = self.page.runs
        return [Path(runs.item(i).data(Qt.UserRole)) for i in range(runs.count()) if runs.item(i).checkState() == Qt.Checked]

    def compare_runs(self) -> None:
        chosen = self.checked_runs()
        if len(chosen) < 2:
            self.page.compare_words.setText("Tick two runs at least.")
            return
        self.queue = [run for run in chosen if str(run) not in self.listings]
        self.page.compare_words.setText("Reading the runs...")
        self._next()

    def _next(self) -> None:
        if self.queue:
            self._read(self.queue.pop(0), self._compared_read)
            return
        chosen = self.checked_runs()
        keys = [row.key for row in self.shown]
        self.comparison = compare({run.name: self.listings[str(run)] for run in chosen if str(run) in self.listings}, keys)
        self._fill_comparison()

    def _compared_read(self, run: Path, rows, words: str) -> None:
        if rows is None:
            self.page.compare_words.setText(words)
            self.queue = []
            return
        self.listings[str(run)] = rows
        self._next()

    def _fill_comparison(self) -> None:
        comparison, table = self.comparison, self.page.compare_table
        header = comparison.header()
        lines = comparison.table()
        table.clear()
        table.setColumnCount(len(header))
        table.setHorizontalHeaderLabels(header)
        table.setRowCount(len(lines))
        digits = [1, 2, 3, 1] * len(comparison.runs)
        for number, line in enumerate(lines):
            table.setItem(number, 0, QTableWidgetItem(line[0]))
            table.setItem(number, 1, QTableWidgetItem(line[1]))
            for column, (value, places) in enumerate(zip(line[2:], digits, strict=False), start=2):
                item = QTableWidgetItem("" if value is None else f"{value:,.{places}f}")
                item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                table.setItem(number, column, item)
        self.page.export_button.setEnabled(bool(lines))
        self.page.compare_words.setText(
            f"{len(comparison.runs)} runs side by side on the {len(lines)} elements shown above: peak, time to peak, "
            "volume and peak outflow. Click a row for its hydrographs on one chart."
        )
        if lines:
            self._compared_clicked(0, 0)

    def _compared_clicked(self, number: int, _column: int) -> None:
        if self.comparison is None or not 0 <= number < len(self.comparison.keys):
            return
        key = self.comparison.keys[number]
        curves = []
        for index, run in enumerate(self.comparison.runs):
            row = next((r for r in self.listings.get(self._folder_of(run), []) if r.key == key), None)
            if row is not None and row.flow:
                curves.append(Curve(f"{run}: flow of record", UPFRONT, COLOURS[index % len(COLOURS)], row.times_h, row.flow))
        name = self.comparison.names[key]
        chart = Chart(FLOW_TITLE, "flow", "m3/s", curves)
        heading = f"{name}: {len(curves)} runs on one chart."
        note = "" if curves else "No flow of record here: a point has depth and level only."
        self.page.plot.show_view(View(heading, "", [chart] if curves else [], None, [], note=note))

    def _folder_of(self, run_name: str) -> str:
        return next((key for key in self.listings if Path(key).name == run_name), "")

    def _export_asked(self) -> None:
        from qgis.PyQt.QtWidgets import QFileDialog

        start = str((self.run or Path.home()) / EXPORT_NAME)
        path, _filter = QFileDialog.getSaveFileName(self.page, "The comparison, as Excel", start, "Excel (*.xlsx)")
        if path:
            self.export_to(path)

    def export_to(self, path: str | Path) -> Path | None:
        if self.comparison is None:
            return None
        written = write_table(Path(path), self.comparison)
        kind = "an Excel workbook" if written.suffix == ".xlsx" else "CSV: this QGIS has no openpyxl"
        self.page.compare_words.setText(f"The table is written as {kind}: {written}")
        return written


__all__ = ["ResultsLinks", "sibling_runs"]
