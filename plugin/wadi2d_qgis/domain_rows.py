# Wadi2D QGIS plugin. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""The domain from an outline (W101 item 5), without Qt: the folder, the command, what stops it and its words.

``wadi2d domain`` (W97) completes a rough outline with every catchment draining into it, or aligns an outline to
catchment polygons; the edges along the job's boundary lines and a keep layer stay as drawn. The engine writes
``domain.geojson``, ``domain.gpkg`` (the domain and what changed) and ``domain_report.json``; these are its words.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

COMPLETE, ALIGN = "complete", "align"
FOLDER_SUFFIX = "_domain"
TEMP_PREFIX = "wadi2d_domain_"
DOMAIN_FILE, LAYERS_FILE, DOMAIN_LAYER, CHANGES_LAYER = "domain.geojson", "domain.gpkg", "domain", "changes"
OUTLINE_FILE, KEEP_FILE, CATCHMENTS_FILE = "outline.geojson", "keep.geojson", "catchments.geojson"
TIMEOUT_S = 1800
"""Block 2's outline completed in 37 s (W97); the margin doubles while a catchment runs to the window's edge."""
WORKING = {COMPLETE: "Completing the outline with the catchments draining into it...", ALIGN: "Aligning the outline to the catchments..."}
MOST_NOTES = 4


def output_folder(run_folder: str) -> Path:
    """Beside the run folder, so the domain outlives the session; a new numbered one each time, never written over
    (the model may already run on the last one). A temporary folder when no output folder is chosen."""
    if not run_folder:
        return Path(tempfile.mkdtemp(prefix=TEMP_PREFIX))
    base = Path(run_folder)
    candidate = base.with_name(base.name + FOLDER_SUFFIX)
    number = 1
    while (candidate / DOMAIN_FILE).exists():
        number += 1
        candidate = base.with_name(f"{base.name}{FOLDER_SUFFIX}_{number}")
    return candidate


OUTFLOW_KIND = "normal"
"""What an added outflow line is: normal depth, its slope the Boundaries table's to check (W106)."""


def leaving_words(leaving: list[dict]) -> str:
    """The streams the new domain sends out through closed edges, the largest first, and what the button does."""
    if not leaving:
        return ""
    streams = "; ".join(
        f"{row['area_km2']:,.2f} km2 at ({row['x']:.0f}, {row['y']:.0f})"
        + (", where the DEM ends" if row.get("no_ground") else "")
        for row in sorted(leaving, key=lambda r: -r["area_km2"])
    )
    many = len(leaving) > 1
    return (
        f" {len(leaving)} stream{'s' if many else ''} leave{'' if many else 's'} this domain through a closed edge, "
        f"where the edge is a wall that would dam {'them' if many else 'it'}: {streams}. Add outflow lines there "
        "puts a normal-depth line along the edge at each, to Boundaries; check its slope there."
    )


def outflow_name(row: dict) -> str:
    return f"Outflow {row['area_km2']:,.1f} km2"


def align_source(domain_name: str | None, outline_name: str | None) -> tuple[str, str] | None:
    """What Align to catchments aligns (W106, gap 4 of W104): Terrain's domain when one is chosen, the completed one
    after Complete upstream, else the rough outline; with the words that say which. None with neither."""
    if domain_name:
        return "domain", f'Aligning Terrain\'s domain "{domain_name}" to the catchments...'
    if outline_name:
        return "outline", f'Aligning the rough outline "{outline_name}" to the catchments (Terrain has no domain yet)...'
    return None


def domain_problems(mode: str, has_dem: bool, has_outline: bool, has_catchments: bool, has_domain: bool = False) -> list[str]:
    """``has_domain``: Terrain holds a domain, which Align aligns in place of the rough outline (W106)."""
    found = [] if has_dem else ["Choose the DEM first: the catchments are read on it."]
    if not has_outline and not (mode == ALIGN and has_domain):
        found.append(
            "Choose the rough outline, a polygon layer."
            if mode != ALIGN
            else "Choose Terrain's domain or the rough outline: Align to catchments aligns the domain, or the outline."
        )
    if mode == ALIGN and not has_catchments:
        found.append("Choose the catchments to align to, a polygon layer: the HMS subbasins or a generated basin's.")
    return found


def domain_args(job: Path | str, out: Path | str, outline: Path | str, keep: Path | str | None, align: Path | str | None) -> list[str]:
    """The arguments of ``wadi2d domain``: the outline completed, or aligned to ``align``."""
    args = ["domain", str(job), "--out", str(out), "--outline", str(outline)]
    if keep:
        args += ["--keep", str(keep)]
    if align:
        args += ["--align", str(align)]
    return args


def parse_domain(out: str) -> dict | None:
    """The event the command prints last, or None."""
    for line in reversed(out.strip().splitlines()):
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if isinstance(event, dict) and event.get("ev") == "domain":
            return event
    return None


def _km2(value: float) -> str:
    return f"{value:,.2f} km2"


def _catchments(found: list[dict], threshold: str) -> str:
    return f"{len(found)} catchment{'' if len(found) == 1 else 's'} with a stream over {threshold}"


def _notes(notes: list[str]) -> str:
    if not notes:
        return ""
    said = " ".join(note.rstrip(".") + "." for note in notes[:MOST_NOTES])
    more = len(notes) - MOST_NOTES
    return " " + said + (f" And {more} more in the report." if more > 0 else "")


def domain_words(report: dict) -> str:
    """The report's areas, in words."""
    if report.get("mode") == ALIGN:
        text = (
            f"Domain {_km2(report['domain_km2'])}, the outline of {_km2(report['outline_km2'])} aligned to "
            f"{report['catchments']} catchment{'' if report['catchments'] == 1 else 's'}: a rim of "
            f"{_km2(report['rim_removed_km2'])} outside them removed, gaps of {_km2(report['gap_added_km2'])} added "
            f"(bands narrower than twice {report['tolerance_m']:g} m)."
        )
        if "cells_outside_catchments" in report:
            text += (
                f" Cells of {report['cell_m']:g} m outside every catchment: {report['cells_outside_catchments']:,}, "
                f"{_km2(report['outside_catchments_km2'])} (were {report['cells_outside_catchments_before']:,})."
            )
        return text + _notes(report.get("notes") or [])
    added, removed, not_added = (report.get(k) or [] for k in ("catchments_added", "catchments_removed", "catchments_not_added"))
    threshold = f"{report['stream_threshold_km2']:g} km2" if report.get("stream_threshold_km2") else "the threshold"
    text = (
        f"Domain {_km2(report['domain_km2'])}, the outline of {_km2(report['outline_km2'])} completed upstream: "
        f"{_km2(report['added_km2'])} added, draining in ({_catchments(added, threshold)}, "
        f"{_km2(report['slivers_added_km2'])} in smaller pieces); {_km2(report['removed_km2'])} removed, draining out "
        f"past the outline ({_catchments(removed, threshold)}, {_km2(report['slivers_removed_km2'])} in smaller pieces)."
    )
    if report.get("not_added_km2"):
        text += (
            f" Not added, draining in across kept edges: {_km2(report['not_added_km2'])} "
            f"({_catchments(not_added, threshold)})."
        )
    text += f" Kept edges: {report.get('kept_lines', 0)} lines; the ground read at {report.get('pixel_m', 0):g} m."
    return text + _notes(report.get("notes") or [])


__all__ = [
    "ALIGN", "COMPLETE", "domain_args", "domain_problems", "domain_words", "output_folder", "parse_domain",
]  # fmt: skip
