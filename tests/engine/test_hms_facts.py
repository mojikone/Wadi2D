"""W74: what the chart's header says of an HMS basin's elements: kind, drainage area, and a subbasin's tc where the
basin's .sqlite holds its flow path; and a design line's rain bar from the junction it pours into."""

from __future__ import annotations

from pathlib import Path

import pytest

from wadi2d.products.hms_facts import NO_PATH, NOT_A_SUBBASIN, hms_element_facts
from wadi2d.products.result_lines import line_rain

DIVERSION = Path(__file__).resolve().parents[1] / "data" / "hms_diversions" / "div_constant.basin"


def test_every_element_gets_its_kind_and_area_and_no_tc_without_a_flow_path():
    facts = hms_element_facts(DIVERSION)
    assert facts, "the diversion test basin reads"
    kinds = {name: f["kind"] for name, f in facts.items()}
    assert "diversion" in kinds.values()
    for f in facts.values():
        assert f["tc_minutes"] is None
        assert f["tc_note"] == (NO_PATH if f["kind"] == "subbasin" else NOT_A_SUBBASIN)
    assert hms_element_facts(DIVERSION.with_name("missing.basin")) == {}


@pytest.mark.data
def test_block2_subbasins_tc_is_his_kirpich_whose_lag_is_the_hms_lag(hms_project_dir: Path):
    """His 18 HMS lags are 0.6 x Kirpich on the longest path and the 10-85 slope (W24); read from the .sqlite here,
    0.6 tc must give each lag back, which also proves the units."""
    facts = hms_element_facts(hms_project_dir / "Basin_1.basin", hms_project_dir / "Basin_1.sqlite")
    subbasins = {n: f for n, f in facts.items() if f["kind"] == "subbasin"}
    assert len(subbasins) == 18
    for name, f in subbasins.items():
        assert f["tc_minutes"] is not None and f["lag_minutes"] is not None, name
        assert 0.6 * f["tc_minutes"] == pytest.approx(f["lag_minutes"], rel=5e-3), name
    from wadi2d.hms import basin as hms_basin
    from wadi2d.workbook.sources import _upstream_area_km2

    basin = hms_basin.load(hms_project_dir / "Basin_1.basin")
    for name, f in facts.items():  # the same reading as the dam workbook's catchments (W60)
        assert (f["drainage_area_km2"] or 0.0) == pytest.approx(_upstream_area_km2(basin, name), abs=1e-3), name


def test_a_design_line_takes_the_rain_of_the_junction_it_pours_into():
    line = {"name": "Dam line"}
    line_rain(line, {"t_s": [0, 60], "rain_mm": [0, 2.0], "excess_mm": [0, 0.5], "outflow_m3s": [0, 1]})
    assert line["rain"] == {"t_s": [0, 60], "rain_mm": [0, 2.0], "excess_mm": [0, 0.5]}
    bare = {"name": "x"}
    line_rain(bare, {"t_s": [0], "outflow_m3s": [0]})
    line_rain(bare, None)
    assert "rain" not in bare
