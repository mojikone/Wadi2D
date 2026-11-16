# Wadi2D QGIS plugin. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""The two bars round the sections (W99): the step strip over them, one step a section, and the footer under them
with how many sections still need the user and the Check and run button. Widgets and words only: :mod:`status_links`
fills them."""

from __future__ import annotations

from qgis.PyQt.QtCore import Qt, pyqtSignal
from qgis.PyQt.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QSizePolicy

from . import look
from .section_status import MISSING, READY, STATE_MARKS, STATE_WORDS, STEP_NAMES, Status, footer_words

MOST_COLUMNS = 4
"""Steps on a line at most: at the width of a dock a fifth would clip the longer names. The rows are as even as they
go: ten sections lie 4, 4 and 2, eight lie 4 and 4."""
CHECK_AND_RUN = "Check and run"
CHECK_TIP = (
    "Checks the whole model as the job will hold it and, if nothing stops it, starts the run: what Run does in the "
    "Run section, where the answer and the progress show."
)


class StepStrip(QFrame):
    """One small button a section, in the dock's order: its name, a mark and a colour for its status; a click opens it."""

    step_clicked = pyqtSignal(str)

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName(look.STRIP)
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(look.PAD_PAGE, look.GAP, look.PAD_PAGE, look.GAP)
        self.grid.setSpacing(4)
        self.steps: dict[str, QPushButton] = {}
        self._shown: tuple[str, ...] = ()
        self._current = ""

    def _step(self, key: str) -> QPushButton:
        button = QPushButton()
        button.setObjectName(look.STEP)
        button.setFlat(True)
        button.setCursor(Qt.PointingHandCursor)
        button.setSizePolicy(
            QSizePolicy.Ignored, QSizePolicy.Fixed
        )  # a narrow dock clips a name, it is not held wide
        button.clicked.connect(lambda _checked=False, name=key: self.step_clicked.emit(name))
        return button

    def lay_out(self, shown: tuple[str, ...]) -> None:
        """The steps of the sections now shown, in rows as even as they go."""
        if shown == self._shown:
            return
        self._shown = shown
        for button in self.steps.values():
            self.grid.removeWidget(button)
            button.hide()
        rows = max(-(-len(shown) // MOST_COLUMNS), 1)
        columns = max(-(-len(shown) // rows), 1)
        for number, key in enumerate(shown):
            if key not in self.steps:
                self.steps[key] = self._step(key)
            button = self.steps[key]
            self.grid.addWidget(button, number // columns, number % columns)
            button.show()

    def show_status(self, statuses: dict[str, Status]) -> None:
        for key, button in self.steps.items():
            status = statuses.get(key)
            if status is None:
                continue
            button.setText(f"{STATE_MARKS[status.state]} {STEP_NAMES.get(key, key)}")
            words = f"{STEP_NAMES.get(key, key)}: {STATE_WORDS[status.state]}. {status.words}".strip()
            button.setToolTip(words)
            button.setAccessibleName(words)
            if button.property("status") != status.state:
                button.setProperty("status", status.state)
                look.restyle(button)

    def mark(self, key: str) -> None:
        """The step of the section last opened from the strip."""
        if key == self._current:
            return
        self._current = key
        for name, button in self.steps.items():
            button.setProperty("current", "true" if name == key else "false")
            look.restyle(button)


class Footer(QFrame):
    """Under the sections, always in sight: how many still need the user, and Check and run."""

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName(look.FOOTER)
        self.needs = QLabel()
        self.needs.setObjectName(look.NEEDS)
        self.needs.setWordWrap(True)
        self.run_button = QPushButton(CHECK_AND_RUN)
        self.run_button.setObjectName(look.PRIMARY_BUTTON)
        self.run_button.setToolTip(CHECK_TIP)
        row = QHBoxLayout(self)
        row.setContentsMargins(look.PAD_PAGE, look.PAD, look.PAD_PAGE, look.PAD)
        row.setSpacing(look.GAP)
        row.addWidget(self.needs, 1)
        row.addWidget(self.run_button)

    def show_needing(self, names: list[str]) -> None:
        """``names``: the short names of the sections that are missing something."""
        words = footer_words(len(names))
        text = f"{words}: {', '.join(names)}" if names else words
        if text != self.needs.text():
            self.needs.setText(text)
            self.needs.setProperty("status", MISSING if names else READY)
            look.restyle(self.needs)
