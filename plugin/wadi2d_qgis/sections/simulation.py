# Wadi2D QGIS plugin. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""7c. Simulation: when the run starts and how long it lasts, the 2D step, the lumped step, how often maps and series
are saved, and which engine runs it (W99).

One place for what was spread: the simulated time, the saved maps and the engine choice came from Run, and the one
start replaces the three "Run starts at" fields of the gridded rain, the rain gauges and the observed gauges, which
now read this one. The 2D step is automatic unless a fixed one is asked for; the lumped step shows only for a model
with a lumped part. Every number left at the engine's default stays out of the job.
"""

from __future__ import annotations

from qgis.PyQt.QtWidgets import QComboBox, QFormLayout, QLabel, QLineEdit, QWidget

from .. import section_status
from ..job_builder import (
    ANIMATION_MAP_S,
    BACKEND,
    BACKEND_TIP,
    BACKEND_WORDS,
    DURATION,
    MAP_EVERY,
    SECONDS_PER_HOUR,
)
from ..model_types import LUMPED, TYPES
from ..simulation_rows import (
    CFL,
    DT_MAX,
    DT_MIN,
    FIXED_NOTE,
    FIXED_START,
    LUMPED_STEP,
    MAPS_NOTE,
    SERIES_EVERY,
    START_PLACEHOLDER,
    START_TIP,
    STEP_AUTO,
    STEP_FIXED,
    STEP_WORDS,
    numerics_of,
)
from .common import Section, bind, number_box

SECONDS_PER_MINUTE = 60.0


def _words(text: str = "") -> QLabel:
    label = QLabel(text)
    label.setWordWrap(True)
    return label


def _box() -> tuple[QWidget, QFormLayout]:
    box = QWidget()
    form = QFormLayout(box)
    form.setContentsMargins(0, 0, 0, 0)
    return box, form


class SimulationSection(Section):
    heading = "7c. Simulation"
    key = "simulation"

    def build(self) -> None:
        self.start = QLineEdit()
        self.start.setPlaceholderText(START_PLACEHOLDER)
        self.start.setToolTip(START_TIP)
        self.duration = number_box(2)
        self.step_mode = QComboBox()
        for key, words in STEP_WORDS.items():
            self.step_mode.addItem(words, key)
        self.auto_box, auto = _box()
        self.cfl, self.dt_max, self.dt_min = number_box(2), number_box(3), number_box(4)
        auto.addRow("Courant number", self.cfl)
        auto.addRow("Largest step, s", self.dt_max)
        auto.addRow("Smallest step, s", self.dt_min)
        self.fixed_box, fixed = _box()
        self.fixed_step = number_box(3)
        self.fixed_note = _words()
        fixed.addRow("Step, s", self.fixed_step)
        fixed.addRow(self.fixed_note)
        self.lumped_step = number_box(2)
        self.maps = QComboBox()
        self.maps_note = _words(MAPS_NOTE)
        self.series = number_box(0)
        self.backend = QComboBox()
        self.backend.setToolTip(BACKEND_TIP)
        self._backend_default: str | None = None
        self._defaults: dict[str, float] = {}
        self._lumped, self._two_d = True, True
        self.form.addRow("Run starts at", self.start)
        self.form.addRow("Simulated time, h", self.duration)
        self.form.addRow("2D time step", self.step_mode)
        self.form.addRow(self.auto_box)
        self.form.addRow(self.fixed_box)
        self.form.addRow("Lumped step, min", self.lumped_step)
        self.form.addRow("Save maps", self.maps)
        self.form.addRow(self.maps_note)
        self.form.addRow("Save series every, s", self.series)
        self.form.addRow("Engine", self.backend)
        self.step_mode.currentIndexChanged.connect(self._shown)
        self._shown()

    def apply_schema(self, schema) -> None:
        bind(self.duration, schema, DURATION, scale=1.0 / SECONDS_PER_HOUR)
        usual = schema.default(MAP_EVERY, 0.0)
        self.maps.clear()
        self.maps.addItem(f"Every {usual / SECONDS_PER_MINUTE:g} minutes, for design work", usual)
        self.maps.addItem(
            f"Every {ANIMATION_MAP_S / SECONDS_PER_MINUTE:g} minutes, for an animation", ANIMATION_MAP_S
        )
        self.maps.setToolTip(schema.tip(MAP_EVERY))
        boxes = {"cfl": (self.cfl, CFL), "dt_max": (self.dt_max, DT_MAX), "dt_min": (self.dt_min, DT_MIN),
                 "lumped": (self.lumped_step, LUMPED_STEP), "series": (self.series, SERIES_EVERY)}  # fmt: skip
        for name, (box, path) in boxes.items():
            bind(box, schema, path)
            self._defaults[name] = box.value()
        low, high = schema.bounds(DT_MAX)[0], schema.bounds(DT_MIN)[1]
        if (
            low is not None and high is not None
        ):  # a fixed step is both bounds at once: it must be allowed as each
            self.fixed_step.setRange(low, high)
            self.fixed_step.setValue(min(max(FIXED_START, low), high))
            self.fixed_note.setText(FIXED_NOTE.format(low=low, high=high))
        self.fixed_step.setToolTip(f"{schema.tip(DT_MAX)}; {schema.tip(DT_MIN)}")
        self._backend_default = schema.default(BACKEND)
        held = self.backend.currentData()
        self.backend.clear()
        for key in schema.enum(BACKEND):
            self.backend.addItem(BACKEND_WORDS.get(key, key), key)
        wanted = held if held is not None else self._backend_default
        self.backend.setCurrentIndex(max(self.backend.findData(wanted), 0))

    def _row(self, widget, shown: bool) -> None:
        widget.setVisible(shown)
        label = self.form.labelForField(widget)
        if label is not None:
            label.setVisible(shown)

    def _shown(self, *_) -> None:
        """What shows: the 2D step, with the numbers of the chosen way, only where there is a 2D model; the lumped
        step only where there is a lumped part."""
        mode = self.step_mode.currentData()
        self._row(self.step_mode, self._two_d)
        self.auto_box.setVisible(self._two_d and mode == STEP_AUTO)
        self.fixed_box.setVisible(self._two_d and mode == STEP_FIXED)
        self._row(self.maps, self._two_d)
        self.maps_note.setVisible(self._two_d)
        self._row(self.lumped_step, self._lumped)

    def set_model_type(self, kind: str | None) -> None:
        self._lumped = kind is None or TYPES[kind].needs_lumped
        self._two_d = kind != LUMPED
        self._shown()

    def set_running(self, running: bool) -> None:
        self.maps.setEnabled(not running)
        self.backend.setEnabled(not running)

    def chosen_backend(self) -> str | None:
        """The engine the user chose, or None for the engine's own default."""
        key = self.backend.currentData()
        return key if key is not None and key != self._backend_default else None

    def fixed(self) -> float | None:
        return self.fixed_step.value() if self._two_d and self.step_mode.currentData() == STEP_FIXED else None

    def standing(self, kind=None):
        return section_status.simulation(
            self.start.text().strip(),
            self.duration.value(),
            self.fixed(),
            self.cfl.value(),
            (self.maps.currentData() or 0.0) / SECONDS_PER_MINUTE if self._two_d else None,
            self.lumped_step.value() if self._lumped else None,
            (self.dt_min.value(), self.dt_max.value()) if self.fixed() is None and self._two_d else None,
        )

    def values(self, crs) -> dict:
        out = {
            "start": self.start.text().strip(),
            "duration_h": self.duration.value(),
            "map_every_s": self.maps.currentData(),
            "backend": self.chosen_backend(),
        }
        if self._two_d and self._defaults:  # the engine's defaults are known: only what left them is written
            held = {"cfl": self.cfl.value(), "dt_max": self.dt_max.value(), "dt_min": self.dt_min.value()}
            numerics = numerics_of(
                self.step_mode.currentData(), self.fixed_step.value(), held, self._defaults
            )
            if numerics:
                out["numerics"] = numerics
            if self.fixed() is None:
                out["step_bounds"] = (held["dt_min"], held["dt_max"])
        if self._lumped and self.lumped_step.value() != self._defaults.get("lumped"):
            out["lumped_step_min"] = self.lumped_step.value()
        if self.series.value() != self._defaults.get("series"):
            out["series_every_s"] = self.series.value()
        return out
