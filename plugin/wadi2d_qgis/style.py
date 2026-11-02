# Wadi2D QGIS plugin. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""How depth and hazard look. Colours and class limits are display choices, so they live here, not in the job."""

from __future__ import annotations

from qgis.core import QgsColorRampShader, QgsRasterShader, QgsSingleBandPseudoColorRenderer
from qgis.PyQt.QtGui import QColor

DEPTH_STOPS = (  # depth m, then red, green, blue, alpha; the shallow end fades out over the map
    (0.0, (190, 225, 255, 0)),
    (0.05, (165, 210, 250, 110)),
    (0.5, (70, 140, 225, 190)),
    (2.0, (20, 75, 175, 225)),
    (5.0, (8, 30, 100, 245)),
)
HAZARD_CLASSES = (  # upper limit of depth times velocity m2/s, the Australian Rainfall and Runoff H1-H6 bands
    (0.3, (255, 255, 190, 200), "H1  below 0.3"),
    (0.6, (255, 220, 110, 210), "H2  0.3 to 0.6"),
    (1.0, (250, 170, 60, 220), "H3-H4  0.6 to 1.0"),
    (4.0, (225, 90, 40, 230), "H5  1.0 to 4.0"),
    (float("inf"), (150, 20, 30, 240), "H6  above 4.0"),
)
MAP_ORDER = ("max_depth", "hazard", "max_speed", "max_level", "arrival", "max_mean_depth")
"""Layer order inside a run's group, top first; only the first is switched on."""


def _pseudocolor(layer, ramp_type, items) -> None:
    ramp = QgsColorRampShader(items[0].value, items[-1].value)
    ramp.setColorRampType(ramp_type)
    ramp.setColorRampItemList(items)
    shader = QgsRasterShader()
    shader.setRasterShaderFunction(ramp)
    layer.setRenderer(QgsSingleBandPseudoColorRenderer(layer.dataProvider(), 1, shader))


def style_depth(layer) -> None:
    """A transparent blue ramp: dry ground stays visible, deep water goes dark."""
    items = [
        QgsColorRampShader.ColorRampItem(depth, QColor(*rgba), f"{depth:g} m") for depth, rgba in DEPTH_STOPS
    ]
    _pseudocolor(layer, QgsColorRampShader.Interpolated, items)


def style_hazard(layer) -> None:
    items = [
        QgsColorRampShader.ColorRampItem(limit, QColor(*rgba), label) for limit, rgba, label in HAZARD_CLASSES
    ]
    _pseudocolor(layer, QgsColorRampShader.Discrete, items)


STYLES = {"max_depth": style_depth, "hazard": style_hazard}


MESH_OPACITY = 0.7
MESH_COLOURS = ("#d7301f", "#fc8d59", "#fdcc8a", "#b3cde3", "#6497b1")
"""Finest cell first."""


def style_mesh(layer, sizes: list[float]) -> None:
    """One colour per cell size, the finest the strongest."""
    from qgis.core import QgsPalettedRasterRenderer
    from qgis.PyQt.QtGui import QColor

    classes = [
        QgsPalettedRasterRenderer.Class(size, QColor(MESH_COLOURS[n % len(MESH_COLOURS)]), f"{size:g} m")
        for n, size in enumerate(sorted(sizes))
    ]
    layer.setRenderer(QgsPalettedRasterRenderer(layer.dataProvider(), 1, classes))
    layer.setOpacity(MESH_OPACITY)
    layer.triggerRepaint()
