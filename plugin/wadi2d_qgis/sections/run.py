# Wadi2D QGIS plugin. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""8. Run: where the results go, estimate, run, stop, and what is happening now. The simulated time, the saved maps
and the engine choice moved to the Simulation section (W99)."""

from __future__ import annotations

from qgis.gui import QgsFileWidget
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QWidget,
)

from .. import section_status, settings, style
from ..job_builder import (
    DV_RASTER,
    PIXEL_M,
    PIXELS_ON,
    SMOOTH_ON,
    SMOOTH_TIP,
    STEP_LIMITER,
)
from .common import Section

WINDOW_WORDS = "Map a window at the terrain's finest resolution"
"""His item 7 (W101): named for the terrain's own pixel, which differs between projects; the tooltip gives it."""
COLOURS = {"info": "#444444", "note": "#a06000", "good": "#1a7a30", "bad": "#b00020"}
BACKGROUNDS = (("Hillshade of the DEM", "hillshade"), ("Satellite (needs internet; check the licence)", "satellite"))


class RunSection(Section):
    heading = "8. Run"
    key = "run"
    state_skip = ("cutoff", "duration", "maps", "backend")
    """The depth cutoff is a display setting, kept with QGIS; the other three are the Simulation section's widgets,
    which older dock checks reach from here."""

    def build(self) -> None:
        self.folder = QgsFileWidget()
        self.folder.setStorageMode(QgsFileWidget.GetDirectory)
        self.folder.setDialogTitle("Output folder")
        self.pixels = QCheckBox("Make pixel depth and hazard maps after the run")
        self.pixels.setChecked(True)
        self.smooth = QCheckBox("Smooth map polygons and depth picture (slower)")
        self.smooth.setChecked(False)
        self.smooth.setToolTip(SMOOTH_TIP)
        self._smooth_default = False
        self.pixels.toggled.connect(self._pixels_toggled)
        self._has_maps = True
        self.map_pixel = QDoubleSpinBox()  # his item 7 (W101): the pixel of the maps of record, empty the rule
        self.map_pixel.setDecimals(2)
        self.map_pixel.setRange(-1.0, 1000.0)  # -1 is Automatic; 0 is the DEM's own pixel, as the engine reads it
        self.map_pixel.setSpecialValueText("Automatic")
        self.map_pixel.setValue(-1.0)
        self.map_pixel.setSuffix(" m")
        self.dv_raster = QCheckBox("Depth x speed raster")
        self.dv_raster.setChecked(False)
        self.limiter = QCheckBox("Name the cell that sets the time step")
        self.limiter.setChecked(False)
        self._has_limiter = True
        self.on_running = lambda _running: None
        """Told when a run starts and ends: the dock passes it on to the Simulation section, whose maps and engine
        choices are held while a run is going, as they were when they sat here."""
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
        self.cutoff = QDoubleSpinBox()
        self.cutoff.setDecimals(3)
        self.cutoff.setSingleStep(0.01)
        self.cutoff.setRange(0.0, style.DEPTH_CUTOFF_MAX_M)
        self.cutoff.setSuffix(" m")
        self.cutoff.setValue(settings.depth_cutoff())
        self.cutoff.setToolTip(
            "Depth layers, cell maps, the aligned cells, the time slider and Make map draw nothing shallower than this. "
            "A display choice: the rasters keep their numbers. 0 draws every wet cell"
        )
        self.cutoff.valueChanged.connect(self._cutoff_changed)
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
        self.window_button = QPushButton(WINDOW_WORDS)
        self.window_button.setEnabled(False)
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
        self.form.addRow(self.pixels)
        self.form.addRow("Map pixel", self.map_pixel)
        self.form.addRow(self.dv_raster)
        self.form.addRow(self.smooth)
        self.form.addRow(self.limiter)
        self.form.addRow(buttons)
        self.form.addRow(self.estimate_label)
        self.form.addRow(self.bar)
        self.form.addRow(self.status)
        self.form.addRow(self.message)
        self.form.addRow(self.open_button)
        self.form.addRow("Draw depth from", self.cutoff)
        self.form.addRow("Map title", self.map_title)
        self.form.addRow("Map background", self.background)
        self.form.addRow(self.map_button)
        self.form.addRow(self.frames_button)
        self.form.addRow(self.pixel_frames_button)
        self.form.addRow(self.window_button)
        self.form.addRow(self.lines_button)
        self.form.addRow(self.workbook_button)

    @staticmethod
    def _text_label() -> QLabel:
        label = QLabel()
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        return label

    def apply_schema(self, schema) -> None:
        self.pixels.setChecked(bool(schema.default(PIXELS_ON, True)))
        self.pixels.setToolTip(schema.tip(PIXELS_ON))
        self.limiter.setToolTip(schema.tip(STEP_LIMITER))
        self._has_limiter = schema.has(STEP_LIMITER)  # an engine from before W85 would refuse the field
        self.limiter.setEnabled(self._has_limiter)
        self._smooth_default = bool(schema.default(SMOOTH_ON, False))
        self.smooth.setChecked(self._smooth_default)
        self.map_pixel.setToolTip(f"{schema.tip(PIXEL_M)}. Automatic leaves it to that rule; 0 is the DEM's own pixel")
        self.dv_raster.setToolTip(schema.tip(DV_RASTER))
        self.dv_raster.setChecked(bool(schema.default(DV_RASTER, False)))
        self._has_maps = schema.has(PIXEL_M) and schema.has(DV_RASTER)  # an engine before W100 would refuse them
        self._pixels_toggled(self.pixels.isChecked())

    def _pixels_toggled(self, on: bool) -> None:
        """The polygons and the picture are drawn from the pixel maps: none without them; nor a pixel or a raster."""
        self.smooth.setEnabled(on and self.pixels.isEnabled())
        for widget in (self.map_pixel, self.dv_raster):
            widget.setEnabled(on and self.pixels.isEnabled() and self._has_maps)

    def _cutoff_changed(self, value: float) -> None:
        settings.set_depth_cutoff(value)
        style.restyle_depth_layers()

    def chosen_smooth(self) -> bool | None:
        """Whether the run draws its polygons and depth picture, or None for the engine's own default."""
        wanted = self.smooth.isChecked() and self.pixels.isChecked()
        return wanted if wanted != self._smooth_default else None

    def standing(self, kind=None):
        return section_status.run(self.folder.filePath(), self.pixels.isChecked())

    def values(self, crs) -> dict:
        return {
            "output": self.folder.filePath(),
            "pixels": self.pixels.isChecked(),
            "smooth": self.chosen_smooth(),
            "step_limiter": self.limiter.isChecked() and self._has_limiter,
            "map_pixel": self.map_pixel.value() if self._has_maps and self.map_pixel.value() >= 0.0 else None,
            "dv_raster": self._has_maps and self.dv_raster.isChecked(),
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
            self.window_button.setEnabled(False)
        self.on_running(running)
        self.pixels.setEnabled(not running)
        self.smooth.setEnabled(not running and self.pixels.isChecked())
        for widget in (self.map_pixel, self.dv_raster):
            widget.setEnabled(not running and self.pixels.isChecked() and self._has_maps)
        self.limiter.setEnabled(not running and self._has_limiter)
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
