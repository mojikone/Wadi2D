# Wadi2D QGIS plugin. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""The plugin shell: one toolbar button for the dock, one menu entry for the engine path."""

from __future__ import annotations

from qgis.core import QgsApplication
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import QAction

from . import settings
from .dock import Wadi2DDock
from .progress import run_is_live

MENU = "&Wadi2D"
ICON = "/mIconRasterLayer.svg"


class Wadi2DPlugin:
    def __init__(self, iface) -> None:
        self.iface = iface
        self.dock: Wadi2DDock | None = None
        self.toggle_action: QAction | None = None
        self.engine_action: QAction | None = None

    def initGui(self) -> None:  # the name QGIS calls
        window = self.iface.mainWindow()
        self.toggle_action = QAction(QgsApplication.getThemeIcon(ICON), "Wadi2D", window)
        self.toggle_action.setCheckable(True)
        self.toggle_action.toggled.connect(self.show_dock)
        self.engine_action = QAction("Engine...", window)
        self.engine_action.triggered.connect(self.open_settings)
        self.iface.addToolBarIcon(self.toggle_action)
        self.iface.addPluginToMenu(MENU, self.toggle_action)
        self.iface.addPluginToMenu(MENU, self.engine_action)
        QgsApplication.instance().aboutToQuit.connect(self.release_run)
        if run_is_live(settings.last_run()):
            self.toggle_action.setChecked(True)  # a run outlived the last session: show it

    def _ensure_dock(self) -> Wadi2DDock:
        if self.dock is None:
            self.dock = Wadi2DDock(self.iface, self.iface.mainWindow())
            self.iface.addDockWidget(Qt.RightDockWidgetArea, self.dock)
            self.dock.visibilityChanged.connect(self._sync_action)
        return self.dock

    def show_dock(self, shown: bool) -> None:
        if shown or self.dock is not None:
            self._ensure_dock().setVisible(shown)

    def _sync_action(self, visible: bool) -> None:
        self.toggle_action.setChecked(visible)

    def open_settings(self) -> None:
        self._ensure_dock().open_settings()

    def release_run(self) -> None:
        if self.dock is not None:
            self.dock.release()

    def unload(self) -> None:
        QgsApplication.instance().aboutToQuit.disconnect(self.release_run)
        self.release_run()
        self.iface.removePluginMenu(MENU, self.toggle_action)
        self.iface.removePluginMenu(MENU, self.engine_action)
        self.iface.removeToolBarIcon(self.toggle_action)
        if self.dock is not None:
            self.iface.removeDockWidget(self.dock)
            self.dock.deleteLater()
            self.dock = None
