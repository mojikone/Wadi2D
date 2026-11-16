# Wadi2D QGIS plugin. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""The status of the sections, kept in sight (W99): each section says where it stands, and the cards, the step strip
and the footer show it.

A timer asks the sections while the model page shows; a section answers from its own widgets, so nothing is read
feature by feature and nothing waits for the engine. A step of the strip opens its section and brings it to the top.
Check and run is Run's own check and start, reached from the footer: it makes the whole check on the job itself, which
the quick statuses do not replace.
"""

from __future__ import annotations

import traceback

from qgis.core import Qgis, QgsMessageLog
from qgis.PyQt.QtCore import QObject, QTimer

from . import look
from .model_types import sections_shown
from .section_status import OPTIONAL, STEP_NAMES, Status, needing

REFRESH_MS = 1000
MODEL_PAGE = 1
LOG_TAG = "Wadi2D"
UNKNOWN = "The status of this section could not be worked out; the Wadi2D log panel says why. Check and run still checks it."


class StatusLinks(QObject):
    def __init__(self, dock) -> None:
        super().__init__(dock)
        self.dock = dock
        self.strip, self.footer = dock.strip, dock.footer
        self.statuses: dict[str, Status] = {}
        self._logged: set[str] = set()
        self._timer = QTimer(self)
        self._timer.setInterval(REFRESH_MS)
        self._timer.timeout.connect(self._tick)
        self.strip.step_clicked.connect(self.open_section)
        self.footer.run_button.clicked.connect(self.check_and_run)
        self._timer.start()

    def shown(self) -> tuple[str, ...]:
        types = self.dock.types
        return sections_shown(types.kind, self.dock.header.show_all.isChecked())

    def _tick(self) -> None:
        if self.dock.pages.currentIndex() == MODEL_PAGE and self.dock.isVisible():
            self.refresh()

    def refresh(self) -> dict[str, Status]:
        """Ask every section, and show the answers on the cards, the strip and the footer."""
        dock = self.dock
        kind = dock.types.kind
        for section in dock.sections:
            try:
                self.statuses[section.key] = section.standing(kind)
            except RuntimeError:  # a layer that left the project while its widget still names it
                self.statuses[section.key] = Status(OPTIONAL, "")
            except (
                Exception
            ):  # a status is a guide: its own fault must never stop the dock, and is not hidden
                self.statuses[section.key] = Status(OPTIONAL, UNKNOWN)
                if section.key not in self._logged:
                    self._logged.add(section.key)
                    QgsMessageLog.logMessage(
                        f"{section.heading}: {traceback.format_exc()}", LOG_TAG, Qgis.Warning
                    )
            dock.cards[section.key].show_status(self.statuses[section.key])
        shown = self.shown()
        self.strip.lay_out(shown)
        self.strip.show_status(self.statuses)
        self.footer.show_needing([STEP_NAMES.get(key, key) for key in needing(self.statuses, shown)])
        self.footer.run_button.setEnabled(dock.panel.run_button.isEnabled())
        return self.statuses

    def open_section(self, key: str) -> None:
        """Open a section and bring its card to the top of the sections."""
        card = self.dock.cards.get(key)
        if card is None or not card.isVisibleTo(self.dock):
            return
        card.section.setCollapsed(False)
        self.strip.mark(key)
        bar = self.dock.scroll.verticalScrollBar()
        QTimer.singleShot(
            0, lambda: bar.setValue(max(card.y() - look.GAP, 0))
        )  # after the opened box has its height

    def check_and_run(self) -> None:
        self.open_section("run")
        self.dock.start_run()
        self.refresh()

    def release(self) -> None:
        self._timer.stop()
