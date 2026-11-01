# Wadi2D QGIS plugin. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""QGIS entry point. Nothing here imports QGIS, so the pure modules can be tested without it."""


def classFactory(iface):  # the name QGIS looks for
    from .plugin import Wadi2DPlugin

    return Wadi2DPlugin(iface)
