# Wadi2D QGIS plugin. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""The first page of the dock (W99): one card per model type, or a finished run to open; and the header a model
carries once a type is chosen. Widgets and words only: :mod:`type_links` decides what a choice does."""

from __future__ import annotations

from qgis.gui import QgsFileWidget
from qgis.PyQt.QtCore import Qt, pyqtSignal
from qgis.PyQt.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from . import look
from .model_types import NO_TYPE_BADGE, NO_TYPE_MEANING, NO_TYPE_TITLE, TYPES, ModelType

CHOOSE = "CHOOSE THE MODEL TYPE"
OPEN = "OPEN A FINISHED RUN"
ALL_BUTTON = "All sections, no model type"
RUN_TIP = (
    "A finished run's folder: the dock is refilled with the model that made it, and its results are at hand."
)
BACK_TIP = "Back to the model types: nothing in the sections is lost"
SHOW_ALL = "Show all sections"
SHOW_ALL_TIP = "Also the sections a model of this type has no use for, as the dock listed them before"


def named(widget, name: str, **properties):
    """A widget with the object name the style sheet matches, and the properties it matches on."""
    widget.setObjectName(name)
    for key, value in properties.items():
        widget.setProperty(key, value)
    return widget


def words(text: str, name: str = look.WORDS) -> QLabel:
    label = named(QLabel(text), name)
    label.setWordWrap(True)
    return label


def badge(text: str, kind: str) -> QLabel:
    label = named(QLabel(text), look.BADGE, kind=kind)
    label.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Maximum)
    return label


class TypeCard(QFrame):
    """One model type: its name, its badge, what it means, and what in it is lumped and what is 2D."""

    clicked = pyqtSignal(str)

    def __init__(self, kind: ModelType) -> None:
        super().__init__()
        named(self, look.TYPE_CARD, current="false")
        self.kind = kind.key
        self.setFocusPolicy(Qt.StrongFocus)
        self.setCursor(Qt.PointingHandCursor)
        self.setAccessibleName(f"Model type {kind.title}")
        self.title = named(QLabel(kind.title), look.CARD_TITLE)
        self.badge = badge(kind.badge, kind.key)
        self.meaning = words(kind.meaning)
        top = QHBoxLayout()
        top.addWidget(self.title, 1)
        top.addWidget(self.badge)
        tags = QHBoxLayout()
        tags.setSpacing(6)
        for text, lumped in kind.parts:
            tag = named(QLabel(text), look.TAG, lumped="true" if lumped else "false")
            tag.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Maximum)
            tags.addWidget(tag)
        tags.addStretch(1)
        column = QVBoxLayout(self)
        column.setContentsMargins(14, look.PAD, 14, look.PAD)
        column.setSpacing(6)
        column.addLayout(top)
        column.addWidget(self.meaning)
        column.addLayout(tags)

    def click(self) -> None:
        self.clicked.emit(self.kind)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.LeftButton and self.rect().contains(event.pos()):
            self.click()

    def keyPressEvent(self, event) -> None:
        if event.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space):
            self.click()
        else:
            super().keyPressEvent(event)

    def set_current(self, on: bool) -> None:
        self.setProperty("current", "true" if on else "false")
        look.restyle(self)


class StartPage(QWidget):
    """Choose a model type, or open a finished run."""

    def __init__(self) -> None:
        super().__init__()
        named(self, look.START)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.cards = {key: TypeCard(kind) for key, kind in TYPES.items()}
        self.all_button = named(QPushButton(ALL_BUTTON), look.QUIET_BUTTON)
        self.all_button.setToolTip(NO_TYPE_MEANING)
        self.run_folder = QgsFileWidget()
        self.run_folder.setStorageMode(QgsFileWidget.GetDirectory)
        self.run_folder.setDialogTitle("Folder of a finished run")
        self.run_folder.setToolTip(RUN_TIP)
        self.open_run_button = named(QPushButton("Open run"), look.QUIET_BUTTON)
        self.open_run_button.setToolTip(RUN_TIP)
        self.message = words("")
        self.message.setTextInteractionFlags(Qt.TextSelectableByMouse)
        column = QVBoxLayout(self)
        column.setContentsMargins(look.PAD_PAGE, look.PAD_PAGE, look.PAD_PAGE, look.PAD_PAGE)
        column.setSpacing(10)
        column.addWidget(named(QLabel(CHOOSE), look.CAPTION))
        for card in self.cards.values():
            column.addWidget(card)
        column.addWidget(self.all_button)
        column.addSpacing(look.GAP)
        column.addWidget(named(QLabel(OPEN), look.CAPTION))
        row = QHBoxLayout()
        row.addWidget(self.run_folder, 1)
        row.addWidget(self.open_run_button)
        column.addLayout(row)
        column.addWidget(self.message)
        column.addStretch(1)

    def mark(self, kind: str | None) -> None:
        """The card of the model's own type, drawn as the chosen one."""
        for key, card in self.cards.items():
            card.set_current(key == kind)

    def say(self, text: str) -> None:
        self.message.setText(text)


class ModelHeader(QFrame):
    """What the model is, over its sections: the type in words and as a badge, the way back, the show-all switch."""

    def __init__(self, dark: bool = False) -> None:
        super().__init__()
        named(self, look.HEADER)
        self.back_button = named(
            QPushButton("\N{SINGLE LEFT-POINTING ANGLE QUOTATION MARK} Types"), look.QUIET_BUTTON
        )
        self.back_button.setToolTip(BACK_TIP)
        self.back_button.setAccessibleName("Back to the model types")
        self.title = named(QLabel(), look.HEADER_TITLE)
        self.meaning = words("")
        self.badge = badge("", "")
        self.show_all = QCheckBox(SHOW_ALL)
        self.show_all.setToolTip(SHOW_ALL_TIP)
        look.ink(self.show_all, dark)
        self.note = words("")
        self.note.hide()
        text = QVBoxLayout()
        text.setSpacing(2)
        text.addWidget(self.title)
        text.addWidget(self.meaning)
        top = QHBoxLayout()
        top.setSpacing(10)
        top.addWidget(self.back_button, 0, Qt.AlignTop)
        top.addLayout(text, 1)
        top.addWidget(self.badge, 0, Qt.AlignTop)
        column = QVBoxLayout(self)
        column.setContentsMargins(look.PAD_PAGE, look.PAD, look.PAD_PAGE, look.PAD)
        column.setSpacing(6)
        column.addLayout(top)
        column.addWidget(self.show_all)
        column.addWidget(self.note)

    def show_type(self, kind: str | None) -> None:
        known = TYPES.get(kind)
        self.title.setText(f"Model type: {known.title}" if known else NO_TYPE_TITLE)
        self.meaning.setText(known.meaning if known else NO_TYPE_MEANING)
        self.badge.setText(known.badge if known else NO_TYPE_BADGE)
        self.badge.setProperty("kind", kind or "")
        look.restyle(self.badge)
        self.show_all.setVisible(bool(known and known.hidden))

    def say(self, text: str) -> None:
        self.note.setText(text)
        self.note.setVisible(bool(text))
