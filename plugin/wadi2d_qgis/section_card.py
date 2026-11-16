# Wadi2D QGIS plugin. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""A section of the dock as a card (W99): the section itself, untouched, with its status as a pill on the line of its
title and one line of words under the title, whether the section is open or closed.

The section stays the collapsible box it was: its title, its arrow and its form are its own. The card adds a frame
round it, lays the pill over the right end of the title line, and keeps two labels with the same words: one as the first
row of the section's form, seen while it is open, one under the closed box.
"""

from __future__ import annotations

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import QFrame, QGridLayout, QLabel, QSizePolicy

from . import look
from .section_status import OPTIONAL, STATE_WORDS, Status

EDGE = 1
"""The card's border, which the section must not paint over."""


def _words() -> QLabel:
    label = QLabel()
    label.setObjectName(look.STATUS_WORDS)
    label.setWordWrap(True)
    label.setSizePolicy(
        QSizePolicy.Ignored, QSizePolicy.Preferred
    )  # a long line wraps: it never widens the dock
    label.setTextInteractionFlags(Qt.TextSelectableByMouse)
    return label


class SectionCard(QFrame):
    def __init__(self, section) -> None:
        super().__init__()
        self.setObjectName(look.SECTION_CARD)
        self.section = section
        self.status = Status(OPTIONAL, "")
        self.pill = QLabel()
        self.pill.setObjectName(look.PILL)
        self.pill.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Maximum)
        self.open_words, self.closed_words = _words(), _words()
        section.form.insertRow(0, self.open_words)
        grid = QGridLayout(self)
        grid.setContentsMargins(EDGE + look.CARD_PAD, EDGE + 2, EDGE + look.CARD_PAD, EDGE + look.CARD_PAD)
        grid.setVerticalSpacing(2)
        grid.addWidget(section, 0, 0)
        grid.addWidget(self.pill, 0, 0, Qt.AlignTop | Qt.AlignRight)
        grid.addWidget(self.closed_words, 1, 0)
        self.closed_words.setContentsMargins(look.PAD + 8, 0, look.PAD, 2)
        self.pill.setContentsMargins(0, look.PILL_TOP, 2, 0)
        section.collapsedStateChanged.connect(self._collapsed)
        self._collapsed(section.isCollapsed())
        self.show_status(self.status, force=True)

    def _collapsed(self, collapsed: bool) -> None:
        """Which of the two labels shows. A closed box hides and shows its own children, so the open one is only
        touched while the box is open."""
        try:
            self.closed_words.setVisible(bool(collapsed) and bool(self.status.words))
            if not collapsed:
                self.open_words.setVisible(bool(self.status.words))
        except RuntimeError:
            return  # the dock is being taken down, and the labels went before the box said it closed

    def show_status(self, status: Status, force: bool = False) -> None:
        """The pill, the border and the words; nothing is redrawn while nothing has changed."""
        if status == self.status and not force:
            return
        moved = status.state != self.status.state or force
        self.status = status
        self.pill.setText(STATE_WORDS[status.state])
        self.pill.setAccessibleName(f"{self.section.heading}: {STATE_WORDS[status.state]}")
        for label in (self.open_words, self.closed_words):
            label.setText(status.words)
        self._collapsed(self.section.isCollapsed())
        if moved:
            for widget in (self, self.pill, self.open_words, self.closed_words):
                widget.setProperty("status", status.state)
                look.restyle(widget)
