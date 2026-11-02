# Wadi2D QGIS plugin. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""The profile editor: one structure at a time, as in HEC-RAS. Drag points or type the table, undo, preview, save.

It stays open beside the map, so the preview's rasters can be looked at while editing. It writes a section table and
nothing else (see ``profile_table``); the preview below the plot is the engine's own result through ``wadi2d terrain``,
drawn by the canvas of Preview terrain, so what is judged here is what a run builds.
"""

from __future__ import annotations

import contextlib
import math
import os
import tempfile
from copy import deepcopy
from pathlib import Path

from qgis.core import QgsPointXY
from qgis.gui import QgsFileWidget
from qgis.PyQt.QtCore import QSignalBlocker, Qt, pyqtSignal
from qgis.PyQt.QtGui import QFont, QKeySequence
from qgis.PyQt.QtWidgets import (
    QApplication,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QShortcut,
    QSlider,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .job_builder import LayerError
from .profile_canvas import EditCanvas
from .profile_model import ProfileModel
from .profile_table import (
    CREST,
    FOLDER_PROPERTY,
    LEFT,
    RIGHT,
    Line,
    ProfileStore,
    point_at,
    profile_folder,
    profile_path,
    read_rows,
    seed,
    write_rows,
)
from .profile_view import ProfileCanvas
from .shaped import LABELS as SHAPED_LABELS

MAX_SAMPLES = 4000
"""Ground points along a line, whatever its length."""
SIZE = (1180, 900)
PREVIEW_MIN = (480, 300)
PLOT_SHARE = 0.48
"""Of the height, what the editing plot keeps once a preview shares it."""
TABLE_WIDTH = 330
DRAFT_PREFIX = "wadi2d_draft_"
NAMES = {**SHAPED_LABELS, "crest_line": "crest line", "spillway": "spillway", "burn_line": "burn line"}
CREST_WORDS = {"burn_line": "invert"}
STALE = "You have edited since this preview: press Preview terrain to bring it up to date."
EMPTY = "Press Preview terrain to see the engine's result for these points here, and on the map."


def ground_along(dem, line: Line) -> list[tuple[float, float]]:
    """(station, level) from the DEM along a line in its CRS, a pixel apart. Holes in the DEM are left out."""
    stations = line.stations()
    pixel = abs(dem.rasterUnitsPerPixelX()) or 1.0
    count = min(max(int(line.length / pixel), 1), MAX_SAMPLES) + 1
    provider = dem.dataProvider()
    found = []
    for n in range(count):
        s = line.length * n / (count - 1)
        value, known = provider.sample(QgsPointXY(*point_at(line.coordinates, stations, s)), 1)
        if known and math.isfinite(value):
            found.append((s, value))
    return found


def ask_unsaved(parent, text: str):
    buttons = QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel
    return QMessageBox.question(parent, "Wadi2D: unsaved profile", text, buttons, QMessageBox.Save)


class PasteTable(QTableWidget):
    """A table that takes cells from a spreadsheet."""

    pasted = pyqtSignal(str)

    def keyPressEvent(self, event) -> None:
        if event.matches(QKeySequence.Paste):
            self.pasted.emit(QApplication.clipboard().text())
            return
        super().keyPressEvent(event)


class PreviewPane(QWidget):
    """The engine's long profile and cross-sections of the last preview, with a slider along the sections."""

    def __init__(self) -> None:
        super().__init__()
        self.item: dict | None = None
        self.banner = QLabel(EMPTY)
        self.banner.setWordWrap(True)
        self.slider = QSlider(Qt.Horizontal)
        self.slider.hide()
        self.station = QLabel()
        self.canvas = ProfileCanvas()
        self.canvas.setMinimumSize(*PREVIEW_MIN)
        self.canvas.hide()
        row = QHBoxLayout()
        row.addWidget(self.banner, 1)
        row.addWidget(self.slider, 1)
        row.addWidget(self.station)
        column = QVBoxLayout(self)
        column.setContentsMargins(0, 0, 0, 0)
        column.addLayout(row)
        column.addWidget(self.canvas, 1)
        self.slider.valueChanged.connect(self._section)

    def show_item(self, item: dict) -> None:
        """The first look starts mid-line: a section exactly on the end of a line draws in teeth, see W22."""
        first = self.item is None
        self.item = item
        with QSignalBlocker(self.slider):
            self.slider.show()
            self.canvas.show()
            self.slider.setRange(0, len(item["sections"]) - 1)
            self.slider.setValue(self.slider.maximum() // 2 if first else self.slider.value())
        self.banner.setText("The engine's result for these points.")
        self._section(self.slider.value())

    def clear(self) -> None:
        self.item = None
        self.canvas.item = None
        self.canvas.hide()
        self.slider.hide()
        self.station.clear()
        self.banner.setText(EMPTY)

    def stale(self) -> None:
        if self.item is not None:
            self.banner.setText(STALE)

    def go_to(self, station: float) -> None:
        """The section nearest a station."""
        if self.item is not None:
            sections = self.item["sections"]
            self.slider.setValue(min(range(len(sections)), key=lambda n: abs(sections[n]["station"] - station)))

    def _section(self, index: int) -> None:
        self.station.setText(f"Section at station {self.item['sections'][index]['station']:,.0f} m")
        self.canvas.show_item(self.item, index)


class ProfileEditor(QDialog):
    """``fetch`` gives the layer's lines of one kind, afresh each time, as the dock's fields can change while this is open.

    Saving writes a file; the dock reads it at the next job.
    """

    preview_wanted = pyqtSignal(str, str, str)
    """kind, line key, the table to preview in place of what is saved."""
    saved = pyqtSignal()
    closed = pyqtSignal()

    def __init__(self, kind: str, layer, fetch, dem, store: ProfileStore, map_canvas=None, parent=None) -> None:
        super().__init__(parent)
        self.kind, self.layer, self.fetch, self.dem, self.store = kind, layer, fetch, dem, store
        self.lines: list[Line] = fetch()
        self.map_canvas = map_canvas
        self.model: ProfileModel | None = None
        self.ask = ask_unsaved
        self.waiting = False
        self._draft: str | None = None
        self._grounds: dict[tuple, list] = {}
        self._shown_stations: list[float] = []
        self._previewed: dict | None = None
        self._index = 0
        self.setWindowTitle(f"Wadi2D profile editor: {NAMES[kind]}[*]")
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setModal(False)
        self._build()
        self._load(0)

    def _build(self) -> None:
        self.line_box = QComboBox()
        self.series_row = QHBoxLayout()
        self.series_group = QButtonGroup(self)
        self.radios: dict[str, QRadioButton] = {}
        self.tied = QCheckBox("Both tops together")
        self.tied.setToolTip("Points at the same station on both tops move, appear and go as one.")
        self.undo_button = QPushButton("Undo")
        self.redo_button = QPushButton("Redo")
        self.fit_button = QPushButton("Whole line")
        top = QHBoxLayout()
        top.addWidget(QLabel("Line"))
        top.addWidget(self.line_box, 1)
        top.addLayout(self.series_row)
        top.addWidget(self.tied)
        top.addStretch(1)
        for button in (self.undo_button, self.redo_button, self.fit_button):
            top.addWidget(button)

        self.canvas = EditCanvas()
        self.table = PasteTable(0, 1)
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setToolTip("Type levels here, or paste from a spreadsheet. Type a station in the last row to add a row.")
        self.delete_row = QPushButton("Delete row")
        side = QWidget()
        side.setMinimumWidth(TABLE_WIDTH)
        side_column = QVBoxLayout(side)
        side_column.setContentsMargins(0, 0, 0, 0)
        side_column.addWidget(self.table, 1)
        side_column.addWidget(self.delete_row)
        upper = QSplitter(Qt.Horizontal)
        upper.addWidget(self.canvas)
        upper.addWidget(side)
        upper.setStretchFactor(0, 1)
        self.pane = PreviewPane()
        self.splitter = QSplitter(Qt.Vertical)
        self.splitter.addWidget(upper)
        self.splitter.addWidget(self.pane)
        self.splitter.setStretchFactor(0, 3)
        self.splitter.setStretchFactor(1, 2)

        self.readout = QLabel(" ")
        font = QFont(self.readout.font())
        font.setPointSizeF(font.pointSizeF() - 0.5)
        self.readout.setFont(font)
        self.words = QLabel()
        self.words.setWordWrap(True)
        self.words.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.route = QLabel()
        self.route.setWordWrap(True)
        self.folder = QgsFileWidget()
        self.folder.setStorageMode(QgsFileWidget.GetDirectory)
        self.folder.setDialogTitle("Folder for this layer's profiles")
        self.folder.setToolTip("Saved profiles are kept here as CSV section tables, one per line of the layer.")
        with QSignalBlocker(self.folder):
            self.folder.setFilePath(str(profile_folder(self.layer)))
        self.preview_button = QPushButton("Preview terrain")
        self.save_button = QPushButton("Save")
        self.drop_button = QPushButton("Drop saved profile")
        self.close_button = QPushButton("Close")
        buttons = QHBoxLayout()
        for button in (self.preview_button, self.save_button, self.drop_button):
            buttons.addWidget(button)
        buttons.addStretch(1)
        buttons.addWidget(self.close_button)
        folder_row = QHBoxLayout()
        folder_row.addWidget(QLabel("Saved in"))
        folder_row.addWidget(self.folder, 1)

        column = QVBoxLayout(self)
        column.addLayout(top)
        column.addWidget(self.splitter, 1)
        for widget in (self.readout, self.words, self.route):
            column.addWidget(widget)
        column.addLayout(folder_row)
        column.addLayout(buttons)
        self.resize(*self._size())

        self.line_box.currentIndexChanged.connect(self._line_chosen)
        self.undo_button.clicked.connect(self.undo)
        self.redo_button.clicked.connect(self.redo)
        self.fit_button.clicked.connect(self.canvas.fit)
        self.tied.toggled.connect(self._tie)
        self.canvas.edited.connect(self.refresh)
        self.canvas.readout.connect(self.readout.setText)
        self.canvas.activated.connect(self._series_in_hand)
        self.canvas.refused.connect(self.say)
        self.canvas.selected_point.connect(self.pane.go_to)
        self.table.itemChanged.connect(self._cell_changed)
        self.table.pasted.connect(self._paste)
        self.delete_row.clicked.connect(self.remove_row)
        self.folder.fileChanged.connect(self._folder_chosen)
        self.preview_button.clicked.connect(self.preview)
        self.save_button.clicked.connect(self.save)
        self.drop_button.clicked.connect(self.drop)
        self.close_button.clicked.connect(self.close)
        QShortcut(QKeySequence.Undo, self, self.undo)
        QShortcut(QKeySequence.Redo, self, self.redo)
        QShortcut(QKeySequence.Save, self, self.save)

    def _size(self) -> tuple[int, int]:
        """The wanted size, kept on the screen."""
        screen = QApplication.primaryScreen()
        if screen is None:
            return SIZE
        room = screen.availableGeometry()
        return min(SIZE[0], room.width()), min(SIZE[1], room.height() - 40)

    @property
    def line(self) -> Line:
        """The line in the plot, which is not always the one in the box: while it changes, this is still the old one."""
        return self.lines[self._index]

    def say(self, text: str) -> None:
        self.words.setText(text)

    # One line.

    def _load(self, index: int) -> None:
        self._read_lines(index)
        line = self.line
        table = self.store.table(self.layer, line.kind, line.key) or line.table
        rows: list[dict] = []
        said = ""
        if table:
            try:
                rows = read_rows(table)
            except (OSError, ValueError) as error:
                said = f"{error}. Showing the line without it."
        where = tuple(tuple(point[:2]) for point in line.coordinates)
        ground = self._grounds.get(where)
        if ground is None:
            ground = self._grounds[where] = ground_along(self.dem, line)
        start = seed(line, ground, rows)
        labels = {CREST: CREST_WORDS.get(line.kind, "crest")}
        self.model = ProfileModel(start, line.length, labels)
        self.model.tied = self.model.tops_alike()
        self._series_buttons()
        with QSignalBlocker(self.tied):
            self.tied.setChecked(self.model.tied)
        self.tied.setVisible(LEFT in self.model.keys and RIGHT in self.model.keys)
        self.canvas.show_model(self.model, ground, sorted(set(line.stations())))
        self._previewed = None
        self.pane.clear()
        self.say(said or start.note or ("" if ground else "The DEM has no ground under this line."))
        self._set_route(table)
        self.refresh()
        if self.map_canvas is not None:
            self.map_canvas.flashFeatureIds(self.layer, [line.fid])

    def _read_lines(self, index: int) -> None:
        """The layer as it stands, with this line in hand; an empty layer leaves the last lines in place."""
        try:
            self.lines = self.fetch() or self.lines
        except LayerError as error:
            self.say(str(error))
        self._index = min(index, len(self.lines) - 1)
        with QSignalBlocker(self.line_box):
            self.line_box.clear()
            self.line_box.addItems([line.label for line in self.lines])
            self.line_box.setCurrentIndex(self._index)

    def _series_buttons(self) -> None:
        for radio in self.radios.values():
            self.series_group.removeButton(radio)
            self.series_row.removeWidget(radio)
            radio.deleteLater()
        self.radios = {}
        for key in self.model.keys:
            radio = QRadioButton(self.model.labels[key])
            radio.toggled.connect(lambda on, name=key: on and self.canvas.take(name))
            self.series_group.addButton(radio)
            self.series_row.addWidget(radio)
            self.radios[key] = radio
        self.radios[self.model.keys[0]].setChecked(True)

    def _series_in_hand(self, key: str) -> None:
        with QSignalBlocker(self.radios[key]):
            self.radios[key].setChecked(True)

    def _tie(self, on: bool) -> None:
        self.model.tied = on

    def _line_chosen(self, index: int) -> None:
        if self._settled():
            self._load(index)
            return
        with QSignalBlocker(self.line_box):
            self.line_box.setCurrentIndex(self._index)

    def _set_route(self, table: str | None) -> None:
        saved = self.store.table(self.layer, self.line.kind, self.line.key)
        if saved:
            words = f"In use: the saved profile {Path(saved).name}. For this line it outranks the fields and the section table."
        elif table:
            words = f"In use: the section table {Path(table).name}. Save keeps these points for this line alone; the table stays as it is."
        else:
            words = "In use: the fields of the layer. Nothing changes until you press Save."
        self.route.setText(words)
        self.drop_button.setEnabled(saved is not None)

    def _settled(self) -> bool:
        """Nothing unsaved stands in the way: saved, thrown away, or none to begin with."""
        if self.model is None or not self.model.dirty:
            return True
        answer = self.ask(self, "This profile has edits that are not saved.")
        if answer == QMessageBox.Save:
            return self.save()
        return answer == QMessageBox.Discard

    # After every edit.

    def refresh(self) -> None:
        self._fill_table()
        self.undo_button.setEnabled(self.model.can_undo)
        self.redo_button.setEnabled(self.model.can_redo)
        self.setWindowModified(self.model.dirty)
        self.canvas.update()
        if self._previewed is not None and self._previewed != self.model.points:
            self.pane.stale()
        elif self._previewed is not None:
            self.pane.banner.setText("The engine's result for these points.")

    def _fill_table(self) -> None:
        model = self.model
        self._shown_stations = model.stations()
        headers = ["Station, m", *(model.labels[key].capitalize() for key in model.keys)]
        with QSignalBlocker(self.table):
            self.table.setColumnCount(len(headers))
            self.table.setHorizontalHeaderLabels(headers)
            self.table.setRowCount(len(self._shown_stations) + 1)
            for row, s in enumerate(self._shown_stations):
                self._set_cell(row, 0, format(s, ".10g"))
                for column, key in enumerate(model.keys, start=1):
                    index = model.at(key, s)
                    self._set_cell(row, column, "" if index is None else format(model.points[key][index][1], ".10g"))
            for column in range(len(headers)):
                self._set_cell(len(self._shown_stations), column, "")

    def _set_cell(self, row: int, column: int, text: str) -> None:
        item = self.table.item(row, column)
        if item is None:
            self.table.setItem(row, column, QTableWidgetItem(text))
        else:
            item.setText(text)

    def _cell_changed(self, item) -> None:
        text = item.text().strip()
        try:
            value = float(text) if text else None
        except ValueError:
            self.say(f'"{text}" is not a number.')
            self.refresh()
            return
        self.model.begin()
        words = self._typed(item.row(), item.column(), value)
        self.model.end()
        self.say(words)
        self.refresh()

    def _typed(self, row: int, column: int, value: float | None) -> str:
        if row >= len(self._shown_stations):
            if column != 0:
                return "Type the station first."
            return "" if value is None else self.model.add_station(value)
        station = self._shown_stations[row]
        if column == 0:
            return "A row needs a station: use Delete row." if value is None else self.model.move_station(station, value)
        return self.model.set_level(self.model.keys[column - 1], station, value)

    def _paste(self, text: str) -> None:
        lines = [line.split("\t") for line in text.strip("\r\n").splitlines()]
        self.model.begin()
        words = self.model.paste(lines, max(self.table.currentRow(), 0), max(self.table.currentColumn(), 0))
        self.model.end()
        self.say(words)
        self.refresh()

    def remove_row(self) -> None:
        row = self.table.currentRow()
        if not 0 <= row < len(self._shown_stations):
            self.say("Click a row of the table first.")
            return
        self.model.begin()
        words = self.model.remove_station(self._shown_stations[row])
        self.model.end()
        self.say(words)
        self.refresh()

    def undo(self) -> None:
        if self.model.undo():
            self.canvas.selected = None
            self.say("")
            self.refresh()

    def redo(self) -> None:
        if self.model.redo():
            self.canvas.selected = None
            self.say("")
            self.refresh()

    # Save, drop, preview.

    def _folder_chosen(self, path: str) -> None:
        if path:
            self.layer.setCustomProperty(FOLDER_PROPERTY, path)
        else:
            self.layer.removeCustomProperty(FOLDER_PROPERTY)
        self._set_route(self.line.table)
        self.saved.emit()

    def save(self) -> bool:
        found = self.model.problems()
        if found:
            self.say(" ".join(found) + " Not saved.")
            return False
        path = profile_path(profile_folder(self.layer), self.line.kind, self.line.key)
        try:
            write_rows(path, self.model.rows())
        except OSError as error:
            self.say(f"The profile could not be written: {error}. Choose another folder below.")
            return False
        self.model.mark_saved()
        self.say(f"Saved. The next preview and the next run use it. {path}")
        self._set_route(str(path))
        self.refresh()
        self.saved.emit()
        return True

    def drop(self) -> None:
        """Back to what the line had before. The file stays in the folder under another name."""
        line = self.line
        self.store.drop(self.layer, line.kind, line.key)
        self.saved.emit()
        self.model.mark_saved()
        self._load(self._index)
        self.say("Dropped. This line reads its fields or its section table again.")

    def preview(self) -> None:
        found = self.model.problems()
        if found:
            self.say(" ".join(found))
            return
        handle, name = tempfile.mkstemp(prefix=DRAFT_PREFIX, suffix=".csv")
        os.close(handle)
        write_rows(name, self.model.rows())
        self._draft = name
        self._previewed = deepcopy(self.model.points)
        self.waiting = True
        self.preview_button.setEnabled(False)
        self.say("Working out the terrain...")
        self.preview_wanted.emit(self.line.kind, self.line.key, name)

    def previewed(self, text: str, worked: bool, data: list[dict]) -> None:
        """The engine has answered: its words, and its long profile and sections when this kind has them."""
        self.waiting = False
        self.preview_button.setEnabled(True)
        if self._draft is not None:
            with contextlib.suppress(OSError):
                Path(self._draft).unlink()
            self._draft = None
        self.say(text)
        items = [item for item in data if item.get("kind") == self.line.kind]
        if worked and self._index < len(items):
            first = self.pane.item is None
            self.pane.show_item(items[self._index])
            if first:
                high = self.splitter.height()
                self.splitter.setSizes([int(PLOT_SHARE * high), int((1.0 - PLOT_SHARE) * high)])
            self.refresh()
        else:
            self._previewed = None
            self.pane.clear()

    def reject(self) -> None:
        self.close()  # Esc asks about unsaved edits too

    def closeEvent(self, event) -> None:
        if self._settled():
            event.accept()
            self.closed.emit()
        else:
            event.ignore()
