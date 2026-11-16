# Wadi2D QGIS plugin tests. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""The status of each dock section (W99): the state and the one line of words, from plain facts; and the palettes the
states are drawn in, light and dark, held to a contrast a reader can rely on."""

from __future__ import annotations

import pytest
from wadi2d_qgis import look
from wadi2d_qgis import section_status as s
from wadi2d_qgis.model_types import HYBRID_2D, HYBRID_LUMPED, LUMPED, TWO_D
from wadi2d_qgis.section_status import MISSING, OPTIONAL, READY, Status


def test_terrain_needs_a_dem_in_metres() -> None:
    assert s.terrain(None, False, False, 20.0, None, 0.035, None) == (
        MISSING,
        "Choose a DEM layer backed by a file.",
    )
    assert s.terrain("memory", False, False, 20.0, None, 0.035, None).state == MISSING
    assert s.terrain("dem", True, True, 20.0, None, 0.035, None) == (
        MISSING,
        "The DEM must be in a projected CRS, in metres.",
    )
    ready = s.terrain("dem", True, False, 20.0, "plain", 0.035, None)
    assert ready == (
        READY,
        "DEM dem \N{MIDDLE DOT} cell 20 m \N{MIDDLE DOT} domain plain \N{MIDDLE DOT} Manning 0.035",
    )
    assert "current map extent" in s.terrain("dem", True, False, 20.0, None, 0.035, None).words
    assert "Manning from landuse" in s.terrain("dem", True, False, 20.0, None, 0.035, "landuse").words


def test_mesh_is_optional_until_it_contradicts_itself() -> None:
    assert s.mesh(False, 160.0, 0, False, None).state == OPTIONAL
    assert s.mesh(True, 160.0, 2, False, None) == (
        READY,
        "Refined: coarsest cell 160 m \N{MIDDLE DOT} 2 refinement lines",
    )
    assert s.mesh(False, 160.0, 0, True, None).state == MISSING
    assert s.mesh(False, 160.0, 0, True, "banks").state == READY
    assert "untick" in s.mesh(True, 160.0, 0, True, "banks").words


def hydro(kind, hms=None, complete=False, ticked=False, ready=False, cn=None):
    return s.hydrology(
        kind,
        hms,
        complete,
        ticked,
        ready,
        18 if hms or ticked else 0,
        12 if hms or ticked else 0,
        cn,
        None,
        None,
    )


@pytest.mark.parametrize("kind", [LUMPED, HYBRID_LUMPED, HYBRID_2D])
def test_a_type_with_a_lumped_part_misses_it_in_hydrology(kind: str) -> None:
    assert hydro(kind).state == MISSING and "needs its lumped catchments" in hydro(kind).words
    assert hydro(kind, hms="Block2").state == MISSING  # the three files
    assert hydro(kind, hms="Block2", complete=True) == (
        READY,
        "HMS project Block2 \N{MIDDLE DOT} 18 subbasins, 12 lumped \N{MIDDLE DOT} no losses: all the rain on the grid runs off",
    )
    assert "Generate basin" in hydro(kind, ticked=True).words
    assert hydro(kind, ticked=True, ready=True).state == READY


def test_hydrology_of_a_model_with_no_lumped_part() -> None:
    assert hydro(TWO_D) == (OPTIONAL, "No losses: all the rain on the grid runs off")
    assert hydro(None) == hydro(TWO_D)
    assert hydro(TWO_D, cn=78.0) == (READY, "Curve number 78")
    unused = hydro(TWO_D, hms="Block2", complete=True, cn=78.0)
    assert unused.state == READY and "not used" in unused.words  # set in the dock, left out of the job: said
    assert hydro(None, hms="Block2", complete=True).words.startswith("HMS project Block2")


def test_storm_says_what_falls_or_what_is_missing() -> None:
    assert s.storm("hms", {}, True) == (READY, "As in the HMS project, with its area reduction")
    assert s.storm("single", {"rain_mm_h": 0.0, "rain_hours": 1.0}, False).state == MISSING
    assert s.storm("single", {"rain_mm_h": 40.0, "rain_hours": 0.5}, False) == (
        READY,
        "Constant rain 40 mm/h for 0.5 h",
    )
    assert s.storm("gauges", {}, False, 0).state == MISSING
    assert s.storm("gauges", {}, False, 3) == (READY, "3 rain gauges, as received")
    design = {
        "kind": "hypothetical",
        "depth_mm": 120.0,
        "hours": 6.0,
        "pattern": [],
        "arf_mode": "none",
        "area_km2": 0.0,
        "arf": [],
    }
    assert s.storm("hypothetical", {"storm": design}, False).state == MISSING
    design = {**design, "pattern": [(0.0, 0.0), (100.0, 100.0)], "arf_mode": "given", "arf_factor": 0.7}
    assert s.storm("hypothetical", {"storm": design}, False) == (
        READY,
        "Design storm 120 mm in 6 h \N{MIDDLE DOT} reduction factor 0.7",
    )
    table = {"kind": "hyetograph", "rows": [(15.0, 4.0), (30.0, 11.5)]}
    assert s.storm("single", {"storm": table}, False) == (READY, "Hyetograph of 2 periods, 15.5 mm")


def test_the_optional_sections() -> None:
    assert s.structures({}, [], [], 0, 0).state == OPTIONAL
    assert s.structures({"Crest lines": "dams"}, ["Crest lines"], [], 0, 0).state == MISSING
    assert s.structures({"Crest lines": "dams"}, [], ["Dam A starts at a level: type the level."], 0, 0) == (
        MISSING,
        "Dam A starts at a level: type the level.",
    )
    assert s.structures({"Crest lines": "dams", "Walls": "walls"}, [], [], 1, 2) == (
        READY,
        "Crest lines, Walls \N{MIDDLE DOT} 1 dam start set \N{MIDDLE DOT} 2 breaches",
    )
    assert s.boundaries(None, [], ("flow",)).state == OPTIONAL
    assert s.boundaries("edges", [("normal", None), ("flow", None)], ("flow",)).state == MISSING
    assert s.boundaries("edges", [("normal", None), ("normal", None), ("flow", "q.csv")], ("flow",)) == (
        READY,
        "3 lines \N{MIDDLE DOT} 2 normal, 1 flow",
    )
    assert s.points(None, 0).state == OPTIONAL and s.points("dams", 5) == (
        READY,
        "5 lines and points from dams",
    )
    assert s.gauges([]).state == OPTIONAL
    assert s.gauges([("G1", "", "")]) == (MISSING, "Gauge G1 needs its record file.")
    assert s.gauges([("G1", "q.csv", "")]).state == MISSING
    assert s.gauges([("G1", "q.csv", "dam")]) == (READY, "1 observed record")
    assert s.run("", True) == (MISSING, "Choose an output folder.")
    assert s.run("C:/runs/own", False) == (READY, "Into own \N{MIDDLE DOT} cell maps only")
    assert s.study().state == OPTIONAL


def test_the_footer_counts_only_what_shows() -> None:
    statuses = {"terrain": Status(READY, "x"), "mesh": Status(MISSING, "y"), "run": Status(MISSING, "z")}
    assert s.needing(statuses, ("terrain", "mesh", "run")) == ["mesh", "run"]
    assert s.needing(statuses, ("terrain", "run")) == ["run"]  # Lumped hides the mesh
    assert s.footer_words(0) == "No section is missing anything"
    assert s.footer_words(1) == "1 section needs you before running"
    assert s.footer_words(3) == "3 sections need you before running"


def test_a_state_is_never_told_by_colour_alone() -> None:
    assert set(s.STATE_WORDS) == set(s.STATE_MARKS) == {READY, OPTIONAL, MISSING}
    assert len(set(s.STATE_MARKS.values())) == 3 and all(s.STATE_WORDS.values())
    for palette in (look.LIGHT, look.DARK):
        assert set(palette.status) == {READY, OPTIONAL, MISSING}


# The palettes: text on its fill, by the WCAG contrast ratio. 4.5 is the ratio asked of body text.


def luminance(colour: str) -> float:
    channels = [int(colour[n : n + 2], 16) / 255.0 for n in (1, 3, 5)]
    linear = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast(a: str, b: str) -> float:
    high, low = sorted((luminance(a), luminance(b)), reverse=True)
    return (high + 0.05) / (low + 0.05)


@pytest.mark.parametrize("palette", [look.LIGHT, look.DARK], ids=["light", "dark"])
def test_every_text_reads_on_its_fill(palette) -> None:
    pairs = {
        "text on card": (palette.text, palette.card),
        "text on page": (palette.text, palette.page),
        "muted on card": (palette.muted, palette.card),
        "muted on page": (palette.muted, palette.page),
        "button text on accent": (palette.on_accent, palette.accent),
        "2D tag": palette.tag_2d,
        "lumped tag": palette.tag_lumped,
        **{f"badge {kind or 'none'}": pair for kind, pair in palette.badges.items()},
        **{f"pill {state}": (ink, fill) for state, (ink, fill, _border) in palette.status.items()},
        **{
            f"{state} words on card": (ink, palette.card)
            for state, (ink, _fill, _border) in palette.status.items()
        },
    }
    weak = {name: round(contrast(*pair), 2) for name, pair in pairs.items() if contrast(*pair) < 4.5}
    assert not weak, weak


def test_the_sheet_is_the_palettes_and_nothing_else() -> None:
    light, dark = look.sheet(False), look.sheet(True)
    assert look.LIGHT.card in light and look.DARK.card not in light
    assert look.DARK.card in dark and look.LIGHT.card not in dark
    for name in (
        look.SECTION_CARD,
        look.PILL,
        look.STEP,
        look.FOOTER,
        look.STRIP,
        look.TYPE_CARD,
        look.BADGE,
    ):
        assert f"#{name}" in light and f"#{name}" in dark
