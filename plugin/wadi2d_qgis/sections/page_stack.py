# Wadi2D QGIS plugin. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Pages of which one shows, each at its own height (W101, his fault of 2026-11-16).

A ``QStackedWidget`` is as tall as its tallest page, so Storm's short pages stood over a gap of some 350 px. Here the
pages lie in a column and all but the shown one are hidden, and a hidden widget takes no room in a layout. The calls
are the stacked widget's that the dock uses.
"""

from __future__ import annotations

from qgis.PyQt.QtWidgets import QVBoxLayout, QWidget


class PageStack(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self._pages: list[QWidget] = []
        self._current = -1
        self._column = QVBoxLayout(self)
        self._column.setContentsMargins(0, 0, 0, 0)

    def addWidget(self, page: QWidget) -> int:
        self._pages.append(page)
        self._column.addWidget(page)
        page.setVisible(len(self._pages) - 1 == self._current)
        return len(self._pages) - 1

    def setCurrentIndex(self, index: int) -> None:
        self._current = index
        for number, page in enumerate(self._pages):
            page.setVisible(number == index)
        self.updateGeometry()

    def currentIndex(self) -> int:
        return self._current

    def currentWidget(self) -> QWidget | None:
        return self._pages[self._current] if 0 <= self._current < len(self._pages) else None

    def widget(self, index: int) -> QWidget:
        return self._pages[index]

    def count(self) -> int:
        return len(self._pages)
