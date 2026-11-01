"""The tokenizer: byte-exact round trip, block structure, sub-block recognition."""

from __future__ import annotations

from pathlib import Path

import pytest

from wadi2d.hms import text

ROUND_TRIP_CASES = {
    "empty": b"",
    "crlf": b"Control: C\r\n     Time Interval: 5\r\nEnd:\r\n",
    "lf": b"Control: C\n     Time Interval: 5\nEnd:\n",
    "bare cr": b"Control: C\r     Time Interval: 5\rEnd:\r",
    "mixed endings": b"Control: C\r\n     A: 1\n     B: 2\r\nEnd:\n",
    "no final newline": b"Control: C\r\n     A: 1\r\nEnd:",
    "trailing spaces": b"Basin: B   \r\n     Description: \r\n     Key:  two   \r\nEnd: \r\n",
    "no space after colon": b"Map:\r\n     Layer:13\r\nEnd:\r\n",
    "latin-1 byte": b"Terrain Data: T\r\n     Stream Threshold: 20 km\xb2\r\nEnd:\r\n",
    "utf-8 bom": b"\xef\xbb\xbfProject: P\r\nEnd:\r\n",
    "utf-8 name": "Junction: Wādī\r\nEnd:\r\n".encode(),
    "unclosed block": b"Subbasin: S1\r\n     Area: 1\r\n",
    "stray end": b"End:\r\nEnd:\r\n",
    "text between blocks": b"not a block\r\n\r\nControl: C\r\nEnd:\r\n   indented: x\r\n",
    "raw line in block": b"Subbasin: S1\r\n     no colon here\r\n\tTab: 1\r\nEnd:\r\n",
    "form feed in value": b"Subbasin: S1\r\n     Note: a\x0cb\x85c\r\nEnd:\r\n",
    "closer with spaces": b"Computation Point: J\r\nEnd Computation Point: \r\n",
}


@pytest.mark.parametrize("data", ROUND_TRIP_CASES.values(), ids=ROUND_TRIP_CASES.keys())
def test_inline_round_trip(data: bytes) -> None:
    assert text.dumps(text.parse(data)) == data


def test_every_fixture_round_trips(fixtures: Path, tmp_path: Path) -> None:
    files = [p for p in fixtures.iterdir() if p.is_file()]
    assert len(files) >= 11
    for path in files:
        target = tmp_path / path.name
        text.dump(text.load(path), target)
        assert target.read_bytes() == path.read_bytes(), path.name


def test_fixtures_really_carry_crlf(fixtures: Path) -> None:
    assert b"\r\n" in (fixtures / "sample.basin").read_bytes()


def test_line_fields_keep_the_separator() -> None:
    document = text.parse(b"Subbasin: S1\r\n     Latitude Degrees:  24.5\r\n     Depth: \r\nEnd:\r\n")
    latitude, depth = list(document.blocks()[0].fields())
    assert (latitude.indent, latitude.key, latitude.sep, latitude.value) == (
        " " * 5,
        "Latitude Degrees",
        ":  ",
        "24.5",
    )
    assert latitude.eol == "\r\n"
    assert (depth.sep, depth.value) == (": ", "")


def test_value_keeps_later_colons() -> None:
    block = text.parse(b"Reach: R\r\n     Last Modified Time: 09:36:22\r\nEnd:\r\n").blocks()[0]
    assert block.get("Last Modified Time") == "09:36:22"


def test_repeated_keys_stay_in_order() -> None:
    block = text.parse(b"Met: M\r\n     Use: A\r\n     Other: x\r\n     Use: B\r\nEnd:\r\n").blocks()[0]
    assert block.get_all("Use") == ["A", "B"]
    assert block.get("Use") == "A"
    assert block.get("Missing", "fallback") == "fallback"


def test_top_level_blocks(fixtures: Path) -> None:
    document = text.load(fixtures / "sample.basin")
    assert not document.unclosed()
    assert len(document.blocks("Subbasin")) == 4
    assert document.block("Junction", "J2").get("Downstream") == "Sink 1"
    assert document.block("Junction", "Nope") is None
    assert document.block("Basin Spatial Properties").name == ""


def test_computation_point_closes_with_its_own_end(fixtures: Path) -> None:
    document = text.load(fixtures / "sample.basin")
    block = document.block("Computation Point")
    assert block.closer.key == "End Computation Point"
    assert [b.kind for b in block.blocks()] == ["Parameter Set", "Graph Definition"]
    assert document.block("Basin Layer Properties") is not None


def test_end_layer_closes_each_layer_kind(fixtures: Path) -> None:
    block = text.load(fixtures / "sample.basin").block("Basin Layer Properties")
    assert [b.kind for b in block.blocks()] == ["Element Layer", "2D Connection Layer", "Map Layer"]
    assert block.blocks("Map Layer")[0].get("Layer") == "13"


def test_sub_block_at_the_indent_of_its_opener(fixtures: Path) -> None:
    block = text.load(fixtures / "sample.basin").block("Reservoir")
    assert [b.kind for b in block.blocks()] == ["Spillway", "Spillway", "Conduit", "Evaporation Method"]
    spillway = block.blocks("Spillway")[1]
    assert spillway.get("Spillway Outlet") == "Auxiliary"
    assert block.get("Spillway Crest Length") is None


def test_closer_with_a_value_and_end_time_inside(fixtures: Path) -> None:
    block = text.load(fixtures / "sample.gage").block("Gage")
    variant = block.blocks("Variant")[0]
    assert variant.name == "Variant-1"
    assert variant.get("End Time") == "2 January 2000, 00:00"
    assert variant.closer.key == "End Variant"


def test_start_time_and_end_time_are_plain_keys() -> None:
    data = b"Control: C\r\n     Start Time: 24:00\r\n     End Time: 24:00\r\n     End Date: \r\nEnd:\r\n"
    block = text.parse(data).blocks()[0]
    assert block.blocks() == []
    assert block.get("End Time") == "24:00"


def test_unmatched_end_key_stays_a_field() -> None:
    block = text.parse(b"Basin: B\r\n     End Something: 3\r\n     End Other:\r\nEnd:\r\n").blocks()[0]
    assert block.blocks() == []
    assert block.get("End Something") == "3"


def test_opener_looks_like_an_empty_key_until_closed() -> None:
    block = text.parse(
        b"Basin: B\r\n     Canopy: None\r\n     Surface: Simple\r\n     End Surface:\r\nEnd:\r\n"
    )
    item = block.blocks()[0]
    assert item.get("Canopy") == "None"
    assert [b.name for b in item.blocks("Surface")] == ["Simple"]


def test_unclosed_block_is_reported() -> None:
    assert [b.name for b in text.parse(b"Subbasin: S1\r\n     Area: 1\r\n").unclosed()] == ["S1"]


def test_encoding_is_recorded() -> None:
    assert text.parse(b"Project: P\r\nEnd:\r\n").encoding == text.UTF8
    assert text.parse(b"Project: \xb2\r\nEnd:\r\n").encoding == text.LATIN1


def test_load_refuses_a_missing_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        text.load(tmp_path / "missing.basin")
