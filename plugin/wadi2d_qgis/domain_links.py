# Wadi2D QGIS plugin. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""The domain from an outline (W101 item 5): Terrain's two buttons run ``wadi2d domain`` and load the result.

The rough outline, the kept edges and the catchments are written as GeoJSON in the DEM's CRS beside a job of the
terrain and the boundary lines, in a folder beside the run folder (a new one each time); the domain the engine writes
is loaded under the model's Inputs > Terrain with what changed, and chosen as Terrain's domain. The engine works out
the domain; this side writes, asks, loads and says.
"""

from __future__ import annotations

import json
from pathlib import Path

from qgis.core import (
    QgsCategorizedSymbolRenderer,
    QgsFillSymbol,
    QgsRendererCategory,
    QgsSingleSymbolRenderer,
    QgsVectorLayer,
)
from qgis.PyQt.QtCore import QObject

from . import settings
from .domain_rows import (
    ALIGN,
    CATCHMENTS_FILE,
    CHANGES_LAYER,
    COMPLETE,
    DOMAIN_LAYER,
    KEEP_FILE,
    OUTLINE_FILE,
    TIMEOUT_S,
    WORKING,
    domain_args,
    domain_problems,
    domain_words,
    output_folder,
    parse_domain,
)
from .engine_process import EngineQuery
from .job_builder import LayerError, domain_job, layer_features, raster_path, write_geojson, write_job
from .layer_groups import TERRAIN, add_layer, clear_slot, input_group, model_name
from .protocol import engine_error_text, exit_message

SLOT_DOMAIN = "domain from outline"
"""The layers of the last completion or alignment: the next one replaces them, a layer moved out of the group stays."""
TITLES = {COMPLETE: "Domain completed upstream", ALIGN: "Domain aligned to the catchments"}
CHANGE_COLOURS = {
    "added": ("#2e9d4a", "Added: draining in"),
    "removed": ("#d0342c", "Removed: draining out past the outline"),
    "not added": ("#8a8a8a", "Not added: across a kept edge"),
    "rim removed": ("#d0342c", "Rim removed: outside the catchments"),
    "gap added": ("#2e9d4a", "Gap added: inside the catchments"),
}


def style_domain(layer) -> None:
    symbol = QgsFillSymbol.createSimple({"color": "0,0,0,0", "outline_color": "#1a5f9a", "outline_width": "0.6"})
    layer.setRenderer(QgsSingleSymbolRenderer(symbol))


def style_changes(layer) -> None:
    categories = [
        QgsRendererCategory(kind, QgsFillSymbol.createSimple({"color": colour, "outline_style": "no"}), words)
        for kind, (colour, words) in CHANGE_COLOURS.items()
    ]
    layer.setRenderer(QgsCategorizedSymbolRenderer("kind", categories))
    layer.setOpacity(0.55)


class DomainLinks(QObject):
    """Terrain's Complete upstream and Align to catchments."""

    def __init__(self, dock) -> None:
        super().__init__(dock)
        self.dock = dock
        self.query: EngineQuery | None = None
        self.folder: Path | None = None
        self.layers: list = []
        terrain = dock.terrain
        terrain.complete_button.clicked.connect(lambda: self.start(COMPLETE))
        terrain.align_button.clicked.connect(lambda: self.start(ALIGN))

    def _say(self, text: str) -> None:
        self.dock.terrain.outline_words.setText(text)

    def _buttons(self, on: bool) -> None:
        self.dock.terrain.complete_button.setEnabled(on)
        self.dock.terrain.align_button.setEnabled(on)

    def start(self, mode: str) -> None:
        terrain = self.dock.terrain
        if self.query is not None:
            self._say("A domain is already being made.")
            return
        dem, outline = terrain.dem_layer(), terrain.outline.currentLayer()
        catchments, keep = terrain.outline_catchments.currentLayer(), terrain.outline_keep.currentLayer()
        found = domain_problems(mode, dem is not None and raster_path(dem) is not None, outline is not None, catchments is not None)
        if found:
            self._say(" ".join(found))
            return
        try:
            values: dict = {}
            for section in self.dock.sections:
                values.update(section.values(dem.crs()))
            folder = output_folder(self.dock.panel.folder.filePath())
            crs = values["crs"]
            outline_file = write_geojson(folder / OUTLINE_FILE, layer_features(outline, dem.crs(), {}), crs)
            keep_file = write_geojson(folder / KEEP_FILE, layer_features(keep, dem.crs(), {}), crs) if keep else None
            align = None
            if mode == ALIGN:
                align = write_geojson(folder / CATCHMENTS_FILE, layer_features(catchments, dem.crs(), {}), crs)
            job = write_job(domain_job(values, folder), folder)
        except (LayerError, OSError) as error:
            self._say(str(error))
            return
        self.folder = folder
        self._buttons(False)
        self._say(WORKING[mode])
        self.query = EngineQuery(settings.engine_text(), self)
        self.query.done.connect(lambda code, out, err: self._done(mode, code, out, err))
        self.query.start(domain_args(job, folder, outline_file, keep_file, align), TIMEOUT_S)

    def _done(self, mode: str, code: int, out: str, err: str) -> None:
        self.query = None
        self._buttons(True)
        event = parse_domain(out) if code == 0 else None
        if event is None:
            self._say(f"The domain was not made. {exit_message(code)} {engine_error_text(err)}".strip())
            return
        report = json.loads(Path(event["report"]).read_text(encoding="utf-8"))
        self.layers = self.load(mode, event, report)
        self._say(domain_words(report))

    def load(self, mode: str, event: dict, report: dict) -> list:
        """The domain and what changed, under the model's Inputs > Terrain, the domain chosen in Terrain."""
        model = model_name(self.dock.panel.folder.filePath())
        clear_slot(model, SLOT_DOMAIN)
        group = input_group(model, TERRAIN)
        title = f"{TITLES[mode]}, {report['domain_km2']:,.2f} km2"
        # from the GeoPackage, which names its CRS; the GeoJSON beside it names none and would read as degrees
        domain = QgsVectorLayer(f"{event['layers']}|layername={DOMAIN_LAYER}", title, "ogr")
        changes = QgsVectorLayer(f"{event['layers']}|layername={CHANGES_LAYER}", f"{TITLES[mode]}: what changed", "ogr")
        shown = []
        for layer, style in ((changes, style_changes), (domain, style_domain)):
            if layer.isValid():
                style(layer)
                add_layer(group, layer, SLOT_DOMAIN, index=0)
                shown.append(layer)
        if domain.isValid():
            self.dock.terrain.domain.setLayer(domain)
        return shown


__all__ = ["SLOT_DOMAIN", "DomainLinks"]
