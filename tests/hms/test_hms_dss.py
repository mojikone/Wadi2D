"""The DSS wrapper, on a small file built by ``hecdss`` itself in a temporary folder."""

from __future__ import annotations

import tempfile
from datetime import datetime
from pathlib import Path

import numpy as np
import pytest
from hecdss import HecDss, PairedData, RegularTimeSeries

from wadi2d.hms import daa_fpart, dss, met_fpart, open_dss, run_fpart

FLOW_F = "DAA:DA 100>J1"
PRECIP_F = "MET:Storm 100>S1"
FLOW = [0.0, 10.5, 42.25, 20.0, 1.5, 0.5]
RAIN = [1.0, 2.0, 3.0, 1.5]
STAMP = datetime(2000, 1, 1, 0, 5)


@pytest.fixture(scope="module")
def dss_path(tmp_path_factory: pytest.TempPathFactory) -> Path:
    path = tmp_path_factory.mktemp("dss") / "sample.dss"
    HecDss.set_global_debug_level(dss.NATIVE_DEBUG_LEVEL)
    native = HecDss(str(path))
    native.put(
        RegularTimeSeries.create(
            values=FLOW,
            units="M3/S",
            data_type="INST-VAL",
            interval="5Minute",
            start_date=datetime(2000, 1, 1),
            path=f"//J1/FLOW/01Jan2000/5Minute/{FLOW_F}/",
        )
    )
    native.put(
        RegularTimeSeries.create(
            values=RAIN,
            units="MM",
            data_type="PER-CUM",
            interval="5Minute",
            start_date=STAMP,
            path=f"//S1/PRECIP-INC/01Jan2000/5Minute/{PRECIP_F}/",
        )
    )
    native.put(
        PairedData.create(
            x_values=[1.0, 10.0, 100.0],
            y_values=np.array([[0.999], [0.987], [0.913]]),
            x_units="KM2",
            x_type="Linear",
            y_units="",
            y_type="Linear",
            path="//ARF A/AREA-REDUCTION FACTOR///TABLE/",
        )
    )
    native.close()
    return path


def _scratch_folders() -> set[str]:
    return {p.name for p in Path(tempfile.gettempdir()).glob(f"{dss.SCRATCH_PREFIX}*")}


def test_fparts() -> None:
    assert run_fpart("FM 100yr") == "RUN:FM 100yr"
    assert daa_fpart("DA 100yr B1", "Z4C") == "DAA:DA 100yr B1>Z4C"
    assert met_fpart("FM 100yr", "S3") == "MET:FM 100yr>S3"


def test_missing_path_is_refused_and_not_created(tmp_path: Path) -> None:
    missing = tmp_path / "missing.dss"
    for readonly in (True, False):
        with pytest.raises(FileNotFoundError):
            open_dss(missing, readonly=readonly)
    assert not missing.exists()


def test_catalog(dss_path: Path) -> None:
    with open_dss(dss_path) as file:
        catalog = file.catalog()
        assert {(p.b, p.c) for p in catalog} == {
            ("J1", "FLOW"),
            ("S1", "PRECIP-INC"),
            ("ARF A", "AREA-REDUCTION FACTOR"),
        }
        assert file.record_count >= 3
        flow = next(p for p in catalog if p.b == "J1")
        assert str(flow).startswith("//J1/FLOW/")


def test_read_timeseries_by_parts(dss_path: Path) -> None:
    with open_dss(dss_path) as file:
        series = file.read_timeseries("J1", "FLOW", FLOW_F)
    np.testing.assert_allclose(series.values, FLOW)
    assert series.values.dtype == np.float64
    assert series.times.dtype == np.dtype("datetime64[s]")
    assert series.times[0] == np.datetime64("2000-01-01T00:00:00")
    assert series.times[2] == np.datetime64("2000-01-01T00:10:00")
    assert (series.units, series.data_type, series.interval_seconds) == ("M3/S", "INST-VAL", 300)
    np.testing.assert_array_equal(series.period_start_times(), series.times)


def test_lookup_ignores_case(dss_path: Path) -> None:
    with open_dss(dss_path) as file:
        assert file.find("j1", "flow", FLOW_F.lower()).b == "J1"


def test_period_series_moves_to_period_start(dss_path: Path) -> None:
    with open_dss(dss_path) as file:
        series = file.read_timeseries("S1", "PRECIP-INC", PRECIP_F)
    assert series.data_type == "PER-CUM"
    assert series.times[0] == np.datetime64("2000-01-01T00:05:00")
    assert series.period_start_times()[0] == np.datetime64("2000-01-01T00:00:00")


def test_lookup_failures(dss_path: Path) -> None:
    with open_dss(dss_path) as file, pytest.raises(dss.DssLookupError):
        file.read_timeseries("J1", "FLOW", "no such F part")


def test_read_paired(dss_path: Path) -> None:
    with open_dss(dss_path) as file:
        table = file.read_paired("//ARF A/AREA-REDUCTION FACTOR///TABLE/")
        same = file.read_paired("ARF A", "AREA-REDUCTION FACTOR")
    np.testing.assert_allclose(table.x, [1.0, 10.0, 100.0])
    np.testing.assert_allclose(table.y, [0.999, 0.987, 0.913])
    assert table.y.ndim == 1
    assert table.x_units == "KM2"
    np.testing.assert_array_equal(table.y, same.y)


def test_readonly_works_on_a_copy_deleted_on_close(dss_path: Path) -> None:
    before_bytes = dss_path.read_bytes()
    before_time = dss_path.stat().st_mtime_ns
    before_folders = _scratch_folders()
    with open_dss(dss_path) as file:
        file.catalog()
        assert len(_scratch_folders() - before_folders) == 1
    assert _scratch_folders() == before_folders
    assert dss_path.read_bytes() == before_bytes
    assert dss_path.stat().st_mtime_ns == before_time


def test_close_twice_is_harmless(dss_path: Path) -> None:
    file = open_dss(dss_path)
    file.close()
    file.close()


def test_writable_open_uses_the_file_itself(dss_path: Path) -> None:
    before_folders = _scratch_folders()
    with open_dss(dss_path, readonly=False) as file:
        assert file.read_timeseries("J1", "FLOW", FLOW_F).values.size == len(FLOW)
        assert _scratch_folders() == before_folders
