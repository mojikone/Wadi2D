# Wadi2D QGIS plugin. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Embankments and channels from feature to job: pure Python, no QGIS. The numbers come from the engine's schema."""

from __future__ import annotations

import re
from pathlib import Path

SHAPED_KINDS = ("embankment", "channel", "channel_dyke")
SHAPE_KEYS = (
    "width", "left_slope", "right_slope", "left_crest_width", "right_crest_width", "left_outer_slope",
    "right_outer_slope",
)  # fmt: skip
LEVEL_KEYS = ("left_top_z", "right_top_z", "bed_start_z", "bed_slope", "water_depth", "freeboard")
END_KEYS = ("start_end", "end_end", "taper_length")
SECTION_PATH = "terrain.objects.section."
OBJECT_PATH = "terrain.objects."
LINING = "lining_n"
TOP = "top_z"
TABLE = "table"
OPENINGS = "openings"
LABELS = {"embankment": "embankment", "channel": "channel", "channel_dyke": "channel with dykes"}
_OPENING = re.compile(
    r"^\s*(\d+(?:\.\d*)?)\s*(?:-|to)\s*(\d+(?:\.\d*)?)\s*(left|right|both|l|r|b)?\s*$", re.I
)
_SIDES = {"l": "left", "r": "right", "b": "both"}


def parse_openings(text: str | None) -> list[dict]:
    """``"120-180 left; 600-650"`` as the job's openings: a range of stations, then a bank or both."""
    if text is None or not str(text).strip():
        return []
    found = []
    for part in re.split(r"[;\n]", str(text)):
        if not part.strip():
            continue
        match = _OPENING.match(part)
        if match is None:
            raise ValueError(f'Openings: "{part.strip()}" is not a range such as 120-180 or 120-180 left.')
        start, end, side = float(match[1]), float(match[2]), (match[3] or "both").lower()
        if end <= start:
            raise ValueError(f'Openings: "{part.strip()}" ends before it starts.')
        found.append({"start": start, "end": end, "side": _SIDES.get(side, side)})
    return found


def shaped_object(kind: str, feature, table: Path | str | None = None) -> dict:
    """The job's entry for one feature; ``table`` is the section table as copied into the run folder."""
    props = feature.properties
    entry: dict = {"kind": kind, "coordinates": feature.xy()}
    if props.get("name"):
        entry["name"] = str(props["name"])
    if props.get("crest_z") is not None:
        entry["z_constant"] = props["crest_z"]
    elif feature.vertex_z() is not None:
        entry["z"] = feature.vertex_z()
    section = {key: props[key] for key in (*SHAPE_KEYS, *LEVEL_KEYS) if props.get(key) is not None}
    if props.get(TOP) is not None:
        section["crest_z"] = props[TOP]
    if table is not None:
        section[TABLE] = str(table)
    entry["section"] = section
    if kind != "channel":
        entry[OPENINGS] = parse_openings(props.get(OPENINGS))
    if kind != "embankment" and props.get(LINING):
        entry[LINING] = props[LINING]
    for key in END_KEYS:
        if props.get(key) is not None:
            entry[key] = props[key]
    return entry


def _feature_problem(kind: str, feature) -> str | None:
    props = feature.properties
    label = LABELS[kind]
    table = props.get(TABLE)
    if table:
        if not Path(table).is_file():
            return f"The section table of a {label} is not there: {table}"
        return None
    level = props.get("crest_z") is not None or feature.vertex_z() is not None
    if kind == "embankment":
        if level or props.get(TOP) is not None:
            return None
        return "Every embankment needs a crest: choose a field, a section table, or a layer with Z values."
    designed = props.get("bed_start_z") is not None and props.get("bed_slope") is not None
    if not (level or designed):
        return (
            f"Every {label} needs a bed: a field, a section table, Z values, or a start level with a slope."
        )
    if kind == "channel":
        return None
    banks = props.get("left_top_z") is not None and props.get("right_top_z") is not None
    freeboard = props.get("freeboard") is not None and props.get("water_depth") is not None
    if props.get(TOP) is not None or banks or freeboard:
        return None
    return f"Every {label} needs a top: a field for both banks, one for each bank, or freeboard with a water depth."


def shaped_problems(structures: dict) -> list[str]:
    """What stops a job, in plain words, each said once."""
    found = []
    for kind in SHAPED_KINDS:
        for feature in structures.get(kind, []):
            problem = _feature_problem(kind, feature)
            if problem is None:
                try:
                    parse_openings(feature.properties.get(OPENINGS))
                except ValueError as error:
                    problem = str(error)
            if problem is not None and problem not in found:
                found.append(problem)
    return found


def volumes_text(volumes: list[dict]) -> str:
    """Cut and fill in one sentence; objects that moved no ground are left out."""
    parts = []
    for row in volumes:
        cut, fill = row.get("cut_m3", 0.0), row.get("fill_m3", 0.0)
        moved = [f"{word} {value:,.0f} m3" for word, value in (("cut", cut), ("fill", fill)) if value >= 0.5]
        if moved:
            parts.append(f"{row.get('object', '')}: {', '.join(moved)}")
    return "Earthworks. " + "; ".join(parts) + "." if parts else ""
