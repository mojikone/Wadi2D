# Wadi2D QGIS plugin. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Suggest breaklines: the engine reads the ground, the dock loads what it wrote as an editable layer.

Reached from the Mesh section's button. The job is the dock's own, as the terrain preview writes it; the engine's
``breaklines`` command writes a GeoPackage beside the run folder; the layer comes in editing, styled by kind, with
the thalwegs beneath it as a read-only reference. The user deletes what is wrong and saves. The bank lines are
refinement lines for the Mesh section: the layer's near_dx, rows and far_dx fields fill its table. They are never
barriers (his rule of 2026-11-07): a face on high ground already reads that ground from the sub-grid tables, and a bank
loaded as a crest line costs the dam peak 10 to 36 % (W26). The road, dam and dyke crests are crest lines for the
Structures section, where every vertex carries its ground elevation, so no field is needed, and a crest face passes at
most critical flow.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from .job_builder import LayerError, preview_job, write_job
from .protocol import engine_error_text, exit_message

TIMEOUT_S = 3600
"""The streams of a large window take minutes; the full extent at 5 m could take most of an hour."""
FOLDER_SUFFIX = "_breaklines"
FILE = "suggested_breaklines.gpkg"
"""What the engine names the file; the plugin reads the path from the engine's event and uses this only to number folders."""
TEMP_PREFIX = "wadi2d_breaklines_"
LAYER_TITLE = "Suggested breaklines"
THALWEG_TITLE = "Thalwegs, reference only, never breaklines"
KINDS = (  # kind in the layer, colour, legend
    ("stream bank", "#0a63c9", "Stream bank, at ground level"),
    ("dam", "#d40000", "Dam, or a road with a culvert"),
    ("road", "#303030", "Road"),
    ("other crest", "#e07b00", "Other crest"),
)
WORKING = "Reading the ground, its streams and its crests..."


def breaklines_args(job: Path | str, out_dir: Path | str) -> list[str]:
    """The arguments of ``wadi2d breaklines``."""
    return ["breaklines", str(job), "--out", str(out_dir)]


def parse_breaklines(out: str) -> dict | None:
    """The event the command prints last, or None."""
    for line in reversed(out.strip().splitlines()):
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if isinstance(event, dict) and event.get("ev") == "breaklines":
            return event
    return None


def output_folder(run_folder: str) -> Path:
    """Beside the run folder, so the file outlives the session; a temporary folder when none is chosen yet.

    A folder that already holds a suggestion is never written again: the user may have edited it, and QGIS may still
    hold it open. The next one goes to a numbered sibling, as runs do.
    """
    if not run_folder:
        return Path(tempfile.mkdtemp(prefix=TEMP_PREFIX))
    base = Path(run_folder)
    candidate = base.with_name(base.name + FOLDER_SUFFIX)
    number = 1
    while (candidate / FILE).exists():
        number += 1
        candidate = base.with_name(f"{base.name}{FOLDER_SUFFIX}_{number}")
    return candidate


def layer_title(event: dict) -> str:
    return f"{LAYER_TITLE}: {event['banks']} banks, {event['crests']} crests"


def summary_text(event: dict) -> str:
    kinds = ", ".join(f"{n} {kind}" for kind, n in event.get("crest_kinds", {}).items())
    crests = f"{event['crests']} crests ({kinds})" if kinds else "no crests"
    return (
        f"Suggested {event['banks']} bank lines along {event['thalwegs']} thalwegs and {crests}, "
        f"from the ground at {event['pixel_m']:g} m. The layer is in editing: delete what is wrong and save it. Use the "
        "bank lines as Refinement lines in the Mesh section, where their near_dx, rows and far_dx fill the table; they "
        "are not barriers, so never load them as Crest lines. Load only the road, dam and dyke crests as Crest lines "
        "under Structures, where their vertices carry the ground elevation and a crest face passes at most critical flow. "
        f"File: {event['path']}"
    )


def suggest_problems(values: dict) -> list[str]:
    """What stops a suggestion: it needs the ground and nothing else."""
    if not values.get("dem"):
        return ["Choose a DEM layer backed by a file."]
    return ["The DEM must be in a projected CRS, in metres."] if values.get("geographic") else []


def dock_of(widget):
    """The dock a section sits in: a section never knows it, so the button looks up."""
    while widget is not None and not (hasattr(widget, "sections") and hasattr(widget, "panel")):
        widget = widget.parent()
    return widget


class Suggester:
    """One suggestion at a time for one dock; the layers it added are replaced by the next."""

    def __init__(self, dock) -> None:
        self.dock = dock
        self.query = None
        self.layer_ids: list[str] = []
        self.folder: Path | None = None

    def start(self) -> None:
        from . import settings
        from .engine_process import EngineQuery

        dock = self.dock
        if self.query is not None:
            dock.panel.say("A suggestion is already running.", "note")
            return
        dem = dock.terrain.dem_layer()
        if dem is None:
            dock.panel.say("Choose a DEM layer first.", "bad")
            return
        try:
            values: dict = {}
            for section in dock.sections:
                values.update(section.values(dem.crs()))
            found = suggest_problems(values)
            if found:
                dock.panel.say(" ".join(found), "bad")
                return
            self.folder = output_folder(dock.panel.folder.filePath())
            job = write_job(preview_job(values, self.folder), self.folder)
        except (LayerError, OSError) as error:
            dock.panel.say(str(error), "bad")
            return
        dock.panel.say(WORKING, "info")
        self.query = EngineQuery(settings.engine_text(), dock)
        self.query.done.connect(self._done)
        self.query.start(breaklines_args(job, self.folder), TIMEOUT_S)

    def _done(self, code: int, out: str, err: str) -> None:
        self.query = None
        event = parse_breaklines(out) if code == 0 else None
        if event is None:
            self.dock.panel.say(f"{exit_message(code)} {engine_error_text(err)}", "bad")
            return
        self._load(event)
        self.dock.panel.say(summary_text(event), "info")

    def _load(self, event: dict) -> None:
        from qgis.core import QgsProject, QgsVectorLayer

        project = QgsProject.instance()
        for old in self.layer_ids:
            if project.mapLayer(old) is not None:
                project.removeMapLayer(old)
        self.layer_ids = []
        root = project.layerTreeRoot()
        reference = QgsVectorLayer.LayerOptions()
        reference.forceReadOnly = True
        thalwegs = QgsVectorLayer(
            f"{event['path']}|layername={event['thalweg_layer']}", THALWEG_TITLE, "ogr", reference
        )
        lines = QgsVectorLayer(f"{event['path']}|layername={event['layer']}", layer_title(event), "ogr")
        for layer, style in ((thalwegs, style_thalwegs), (lines, style_breaklines)):
            if not layer.isValid():
                continue
            style(layer)
            project.addMapLayer(layer, False)
            root.insertLayer(0, layer)
            self.layer_ids.append(layer.id())
        if lines.isValid():
            lines.startEditing()


def style_breaklines(layer) -> None:
    from qgis.core import QgsCategorizedSymbolRenderer, QgsLineSymbol, QgsRendererCategory

    categories = [
        QgsRendererCategory(kind, QgsLineSymbol.createSimple({"color": colour, "width": "1.1"}), legend)
        for kind, colour, legend in KINDS
    ]
    layer.setRenderer(QgsCategorizedSymbolRenderer("kind", categories))


def style_thalwegs(layer) -> None:
    from qgis.core import QgsLineSymbol, QgsSingleSymbolRenderer

    symbol = QgsLineSymbol.createSimple({"color": "#22a7f0", "width": "0.5", "line_style": "dash"})
    layer.setRenderer(QgsSingleSymbolRenderer(symbol))


def suggest_breaklines(section) -> None:
    """What the Mesh section's button does."""
    dock = dock_of(section)
    if dock is None:
        return
    suggester = getattr(section, "suggester", None)
    if suggester is None or suggester.dock is not dock:
        suggester = section.suggester = Suggester(dock)
    suggester.start()
