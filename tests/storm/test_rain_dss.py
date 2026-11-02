"""The DSS grid reader. Which way up a grid is stored comes only from the two files below, written by HEC's own tools."""

from __future__ import annotations

import base64
import lzma
from datetime import datetime
from pathlib import Path

import numpy as np
import pyproj
import pytest
from hecdss import HecDss, RegularTimeSeries
from hecdss.gridded_data import GriddedData

from wadi2d.io.rain import DSS, rain_choices, rain_format, read_rain
from wadi2d.io.rain.dss_grid import HRAP_WKT, SHG_WKT, dss_choices, read_dss_grid
from wadi2d.storm.rain_frames import RainSpec

PERIOD = "/SHG/TEST/PRECIPITATION/01JAN2000:0000/01JAN2000:0100/SYN/"
UTM = pyproj.CRS.from_epsg(32640).to_wkt("WKT1_GDAL")
NORTH_UP = np.array([[50.0, 51, 52, 53, 54], [30, 31, 32, 33, 34], [5, 6, 7, 8, 9], [0, 0, 0, 0, 0]])

VORTEX_FILE = """
/Td6WFoAAATm1rRGAgAhARwAAAAQz1jM4fHfA3FdAC0RBsCNPj8NopuXgXdOZ49wNhvRngW0h/ShQsdBqj4ESMpmy6GMj4r1roYb
5M7HBbAhWW+gHu6JW1WyMWyIupOPljWFrgNj2mnbNa+s1GIkl1Xf6ZVz+aaOGGOhWhfDNbSVT9dSR/fTiwieYTiWQUsY0oifdPIl
vaFcj6uvsopxawneJxL8JrNEh0S2wtuP9EzGPs3V1zlarzgFBsjC1Q5Zt03vzK5KREXCMECEngyEAYmLKC6otiXTg068F6x1H3Wk
ITgxTQmTInvuSlO++3LET3ZPy/w+V7yYSpFX06vXdDdlibmEiBpKTTdR2EI33iGHZBjQdjadPZQd6rMQy/rWoP9NLLMYp3Bviqb+
5/Q9UG2KlzYsoDaXMTzGIqXe2B6oR6jTwjcIDDEb8NCQA1SMYbv9zHHNJkxRGOu76ezsikbJANpUUo7lcYfqMjYofodHhQrCVOXH
Jj9mNSMpLpmB/vzej+PnaiZWur+TmVbM1i099OckXrkcJwhdybtUSBKiqW7VTNIg4ZX15u38EK5iZLFfcCGqtIjItJ7GjJgrfUnK
nexvlSodjA03JFiDQq3JOK1p6SBtTCy8PvDu0FNALL1CQns4Mb6WYp37bSZ7RZE4w/1E/1ar9HpAt5mo6mXCYjnTAXnrza73oylb
6YE+icogzTAi1CPyZFr0DCWYeonT715SMBhNhqW+uWLxAXTfW44AqyjOscThCFHc+kd2kOuUlIdsGQ+7IwaTgb+hF0IljklDMtj4
dyoNEXx1EptQaF65VrkatKXGZzwRKviK9iDC7+apHqYoNrTKZ6dOHJiwYfHc2bPcb7NQEQ/Ff2wurO7vrc83bPb1RDK20Ln+84k4
efY1Y2z9DJr/gcT4DIuDrHA1P+fXLm/1hhXYcKF/pv35btMAaIz7047QLInaA/wHmimM8J6Wi8Gz6joZUg/1m/Ynp7an2MNiO6BE
fobG58Py/vHEqprX5paRw3ZRnT6pzOsg5lfTHVVpIPa/txJAARrFupfKQ9z9t0uJN8S5Uw7oXEAxCwR2fY/LXAI141OpuvS68bKJ
NbqQKfScg821AvNtJW21Bd9fLoEosYuNetMTHMlxU9DqSdagUx3Wg10gfrquwKoCI8hjoivrokIOh6Wbtm76T7IIG5kyf+khr/G7
jiJqAOemvax8Q8S4AAAAAPrq3QJ7Cek3AAGNB+DjBwDNtsHhscRn+wIAAAAABFla
"""
"""HEC Vortex 0.11.29, BatchImporter, from a GeoTIFF in EPSG:32640 holding NORTH_UP, origin (440000, 2729000), 1 km; rasterio
sampled 50 at y = 2,728,500 and 0 at y = 2,725,500. Named as a PRISM file, which is what gives Vortex a date."""

ASC2DSS_FILE = """
/Td6WFoAAATm1rRGAgAhARwAAAAQz1jM4fFXAzpdAC0RBsCNPj8NopuXgXdOZ49wNhuaYGJVJLR4M0cBQb8FP9G6J/tLyISYp3f9
QDW0j2aILjeJYpDfSu+5zQwlpvcl4UCzjQl0OuUdR0UvN2+HRE3Crm7Y2p5dxM4rIuvsk9Gme29Gxcg3ZGZb7/f7dvxUIP8wquiF
72uJiQ2LMOpthBkh2mCshJMhCWBKulV2L6WKdQ28afjOnIEGN5ftkLQs50Z6xvX68mZU6jkCsOhpmqza65N+NFfjgn4edwzucXlA
0ILh+9tIoliE7bdXTIYcONIRycM8agya7t0z/7BfCO+BMyy4x6XJp7wC2sfPRgWd7DskFoel0vkDrexIgxjH1DgdWCIZbBG6Hd1r
3GNICd9onzEnCyQrOP5pknWRh3yD6szfmoc3luc5M8hCeZneebaMdATQ2uJTO+7uVr70/OTYDrV8aQVLsw5JX3mTh4haN/8JhCiN
9JPyxkvDDQQy4+O1j6z7hWBrFZ1vGp5teXhuh/zp2iK2kTreLzhlAjEMaQ+ktfEFG3SYCtAIwUulJaSjvQxankXCFGThJM81cmW0
XinL60bxe7+BgeFGgAinmlCImYsqSlbDwNHEl2f7kt1w1kvIdtw6SUUyRhDHxh/TsTLrLRQsXqjTNpawhrNG8lVQIl6qu4PakdGV
TOd3glYwqZA4ap83dXc0mm7qwo7YD+OkRH85Lm4W3CHq0rRA1LiVF2u6mWTZhSvuHGcLqaWFHB8+2k7w8sjM5+7DMdNxNO/FR36U
9DSi3pU6h2f8qjPxCwr9QhbZ90J1n42WyuD2yOHz0q+AqL7z98yLQPVEDUFCUsbh4WvVwXjaPgY0tHd5+P+8aM+90ZilL41FEojJ
oDFD3VxKWGo5AvdhikBcvz7LOmRfmX+yrOIasjziMNPkgYKxuBAf6HPYNpXj0JElYr/YaUsh9n/ngkT2/eL4r1dF4tM8l6sz36xe
l7fncvFdTRu5rEv6Y1dAUKa0XHFwrroBkNg1sRxiW/wAOJ798pEgoLOQ092gKI1DoELWxPDZpRhbJoaV6ndTVQcNcTk+GAeGRO3Z
JO8lrspwu383QfSkCZCqMWYTO9dX+rqhRb6XQUVQSLsAAACx8uwEagt6HgAB1gbY4gcAMN21jrHEZ/sCAAAAAARZWg==
"""
"""HEC Asc2DssGrid, monolith 3.3.28, GRIDTYPE=SHG, from an ESRI ASCII grid, whose first line is north by the format's own
definition: NORTH_UP with -9999 in row 1, column 3, xllcorner 440000, yllcorner 2726000, 2 km; the period ends at 2400."""


def _hec_file(tmp_path: Path, packed: str) -> Path:
    file = tmp_path / "hec.dss"
    file.write_bytes(lzma.decompress(base64.b64decode(packed)))
    return file


def _grid(pathname: str, stored: object, **header: object) -> GriddedData:
    """A record; ``stored`` is written as it stands, so its first row is the southern one, as the HEC files show."""
    data = np.asarray(stored, dtype=float)
    fields: dict = {"type": 430, "dataType": 1, "dataUnits": "MM", "cellSize": 100.0, "srsDefinition": UTM}
    return GriddedData.create(
        path=pathname,
        data=data,
        numberOfCellsX=data.shape[1],
        numberOfCellsY=data.shape[0],
        **(fields | header),
    )


def _write(tmp_path: Path, *records: object) -> Path:
    file = tmp_path / "rain.dss"
    dss = HecDss(str(file))
    for record in records:
        assert dss.put(record) == 0
    dss.close()
    return file


def _at(start: str, end: str, series: str = "TEST/PRECIPITATION/SYN") -> str:
    b, c, f = series.split("/")
    return f"/SHG/{b}/{c}/{start}/{end}/{f}/"


def test_a_raster_imported_by_vortex_comes_back_north_up_at_its_coordinates(tmp_path: Path) -> None:
    frames = read_dss_grid(_hec_file(tmp_path, VORTEX_FILE), RainSpec())
    assert np.array_equal(frames.depths[0], NORTH_UP)
    assert (frames.west, frames.north, frames.dx, frames.dy) == (440000.0, 2729000.0, 1000.0, 1000.0)
    assert pyproj.CRS.from_user_input(frames.crs).to_epsg() == 32640
    assert frames.origin == np.datetime64("1999-12-31T12:00:00")
    assert frames.ends_min.tolist() == [1440.0]
    north, south = frames.pixel_of(np.array([440500.0, 440500.0]), np.array([2728500.0, 2725500.0]))
    assert frames.depths[0].ravel()[[north, south]].tolist() == [50.0, 0.0]


def test_an_ascii_grid_loaded_by_hec_comes_back_north_up_with_its_hole(tmp_path: Path) -> None:
    file = _hec_file(tmp_path, ASC2DSS_FILE)
    frames = read_dss_grid(file, RainSpec())
    wanted = NORTH_UP.copy()
    wanted[1, 3] = np.nan
    np.testing.assert_array_equal(frames.depths[0], wanted)
    assert (frames.west, frames.north, frames.dx) == (440000.0, 2734000.0, 2000.0)
    assert pyproj.CRS.from_user_input(frames.crs).name == pyproj.CRS.from_user_input(SHG_WKT).name
    assert frames.origin == np.datetime64("2000-01-01T23:00:00")
    assert frames.ends_min.tolist() == [60.0]
    assert dss_choices(file) == ["ASCTEST/PRECIP/HECASC"]


def test_frames_go_by_time_and_not_by_the_catalogue(tmp_path: Path) -> None:
    file = _write(
        tmp_path,
        _grid(_at("01FEB2000:0100", "01FEB2000:0200"), [[3.0]]),
        _grid(_at("31JAN2000:2300", "01FEB2000:0000"), [[1.0]]),
        _grid(_at("01FEB2000:0000", "01FEB2000:0100"), [[2.0]]),
    )
    frames = read_dss_grid(file, RainSpec())
    assert frames.depths[:, 0, 0].tolist() == [1.0, 2.0, 3.0]
    assert frames.origin == np.datetime64("2000-01-31T23:00:00")
    assert frames.starts_min.tolist() == [0.0, 60.0, 120.0]
    assert frames.ends_min.tolist() == [60.0, 120.0, 180.0]


def test_a_missing_hour_stays_a_gap(tmp_path: Path) -> None:
    file = _write(
        tmp_path,
        _grid(_at("01JAN2000:0000", "01JAN2000:0100"), [[1.0]]),
        _grid(_at("01JAN2000:0300", "01JAN2000:0400"), [[2.0]]),
    )
    frames = read_dss_grid(file, RainSpec())
    assert frames.starts_min.tolist() == [0.0, 180.0]
    assert frames.ends_min.tolist() == [60.0, 240.0]


def test_2400_closes_its_own_day(tmp_path: Path) -> None:
    file = _write(
        tmp_path,
        _grid(_at("01JAN2000:2300", "01JAN2000:2400"), [[1.0]]),
        _grid(_at("02JAN2000:0000", "02JAN2000:0100"), [[2.0]]),
    )
    frames = read_dss_grid(file, RainSpec())
    assert frames.origin == np.datetime64("2000-01-01T23:00:00")
    assert frames.ends_min.tolist() == [60.0, 120.0]


def test_units_are_read_frame_by_frame(tmp_path: Path) -> None:
    file = _write(
        tmp_path,
        _grid(_at("01JAN2000:0000", "01JAN2000:0100"), [[2.0]], dataUnits="IN"),
        _grid(_at("01JAN2000:0100", "01JAN2000:0130"), [[10.0]], dataUnits="MM/HR"),
        _grid(_at("01JAN2000:0130", "01JAN2000:0200"), [[7.0]], dataUnits="mm"),
    )
    assert read_dss_grid(file, RainSpec()).depths[:, 0, 0].tolist() == [50.8, 5.0, 7.0]


def test_the_job_can_overrule_the_units_and_unknown_units_are_refused(tmp_path: Path) -> None:
    file = _write(tmp_path, _grid(PERIOD, [[2.0]], dataUnits="CFS"))
    assert read_dss_grid(file, RainSpec(units="in")).depths[0, 0, 0] == 50.8
    with pytest.raises(ValueError, match="units 'CFS'"):
        read_dss_grid(file, RainSpec())


def test_a_null_cell_has_no_data_and_a_dry_cell_stays_dry_when_the_null_value_is_unset(
    tmp_path: Path,
) -> None:
    file = _write(tmp_path, _grid(PERIOD, [[np.nan, 0.0], [1.0, 2.0]], nullValue=0.0))
    depths = read_dss_grid(file, RainSpec()).depths[0]
    assert depths[0].tolist() == [1.0, 2.0]
    assert np.isnan(depths[1, 0])
    assert depths[1, 1] == 0.0


def test_a_flag_set_as_the_null_value_is_honoured(tmp_path: Path) -> None:
    file = _write(tmp_path, _grid(PERIOD, [[9999.0, 1.0]], nullValue=9999.0))
    depths = read_dss_grid(file, RainSpec()).depths[0, 0]
    assert np.isnan(depths[0])
    assert depths[1] == 1.0


def test_the_only_rain_is_taken_and_many_frames_are_one_series(tmp_path: Path) -> None:
    file = _write(
        tmp_path,
        _grid(_at("01JAN2000:0000", "01JAN2000:0100"), [[1.0]]),
        _grid(_at("01JAN2000:0100", "01JAN2000:0200"), [[2.0]]),
        _grid("/SHG/TEST/TERRAIN/01JAN2000:0000/01JAN2000:0100/SYN/", [[900.0]]),
        _grid("/SHG/TEST/TEMPERATURE/01JAN2000:0000/01JAN2000:0100/SYN/", [[20.0]]),
    )
    assert dss_choices(file) == ["TEST/PRECIPITATION/SYN"]
    assert read_dss_grid(file, RainSpec()).count == 2


def test_a_precipitation_time_series_is_not_a_grid(tmp_path: Path) -> None:
    series = RegularTimeSeries.create(
        [1.0, 2.0], path="/SHG/TEST/PRECIP-INC/01JAN2000/1Hour/SYN/", units="MM", data_type="PER-CUM",
        interval=3600, start_date=datetime(2000, 1, 1, 1),
    )  # fmt: skip
    file = _write(tmp_path, _grid(PERIOD, [[1.0]]), series)
    assert dss_choices(file) == ["TEST/PRECIPITATION/SYN"]


def test_several_series_need_a_choice_and_the_error_names_them(tmp_path: Path) -> None:
    file = _write(
        tmp_path,
        _grid(_at("01JAN2000:0000", "01JAN2000:0100", "A/PRECIP/RADAR"), [[1.0]]),
        _grid(_at("01JAN2000:0000", "01JAN2000:0100", "B/RAINFALL/WRF"), [[2.0]]),
    )
    assert dss_choices(file) == ["A/PRECIP/RADAR", "B/RAINFALL/WRF"]
    with pytest.raises(ValueError, match=r"A/PRECIP/RADAR.*B/RAINFALL/WRF"):
        read_dss_grid(file, RainSpec())
    assert read_dss_grid(file, RainSpec(variable="b/rainfall/wrf")).depths[0, 0, 0] == 2.0


def test_an_unknown_series_and_a_file_without_rain_say_what_there_is(tmp_path: Path) -> None:
    file = _write(tmp_path, _grid("/SHG/TEST/TERRAIN/01JAN2000:0000/01JAN2000:0100/SYN/", [[900.0]]))
    with pytest.raises(ValueError, match=r"no gridded series 'NO/SUCH/ONE'.*TEST/TERRAIN/SYN"):
        read_dss_grid(file, RainSpec(variable="NO/SUCH/ONE"))
    with pytest.raises(ValueError, match=r"no gridded precipitation.*TEST/TERRAIN/SYN"):
        read_dss_grid(file, RainSpec())


def test_one_series_under_two_a_parts_is_refused(tmp_path: Path) -> None:
    file = _write(
        tmp_path,
        _grid("/SHG/TEST/PRECIP/01JAN2000:0000/01JAN2000:0100/SYN/", [[1.0]]),
        _grid("/HRAP/TEST/PRECIP/01JAN2000:0100/01JAN2000:0200/SYN/", [[2.0]]),
    )
    with pytest.raises(ValueError, match="more than one A part"):
        read_dss_grid(file, RainSpec())


def test_frames_cut_to_their_rain_sit_in_the_union_and_are_dry_outside(tmp_path: Path) -> None:
    file = _write(
        tmp_path,
        _grid(
            _at("01JAN2000:0000", "01JAN2000:0100"),
            [[1.0, 2.0], [3.0, 4.0]],
            lowerLeftCellX=-1,
            lowerLeftCellY=5,
        ),
        _grid(_at("01JAN2000:0100", "01JAN2000:0200"), [[5.0, 6.0, 7.0]], lowerLeftCellX=1, lowerLeftCellY=7),
    )
    frames = read_dss_grid(file, RainSpec())
    assert (frames.west, frames.north, frames.dx) == (-100.0, 800.0, 100.0)
    np.testing.assert_array_equal(frames.depths[0], [[0, 0, 0, 0, 0], [3, 4, 0, 0, 0], [1, 2, 0, 0, 0]])
    np.testing.assert_array_equal(frames.depths[1], [[0, 0, 5, 6, 7], [0, 0, 0, 0, 0], [0, 0, 0, 0, 0]])
    assert frames.missing_share() == 0.0


def test_a_small_frame_with_a_dry_rim_was_not_cut_to_its_rain_so_its_outside_is_unknown(
    tmp_path: Path,
) -> None:
    rimmed = [[0.0, 0.0, 0.0], [0.0, 5.0, 0.0], [0.0, 0.0, 0.0]]
    whole = np.ones((5, 5))
    file = _write(
        tmp_path,
        _grid(_at("01JAN2000:0000", "01JAN2000:0100"), whole),
        _grid(_at("01JAN2000:0100", "01JAN2000:0200"), rimmed, lowerLeftCellX=1, lowerLeftCellY=1),
    )
    depths = read_dss_grid(file, RainSpec()).depths[1]
    assert depths[2, 2] == 5.0
    assert depths[1, 1] == 0.0
    assert np.isnan(depths[0]).all()
    assert np.isnan(depths[:, 4]).all()


def test_a_small_dry_frame_says_nothing_fell_outside_it(tmp_path: Path) -> None:
    file = _write(
        tmp_path,
        _grid(_at("01JAN2000:0000", "01JAN2000:0100"), np.ones((3, 3))),
        _grid(_at("01JAN2000:0100", "01JAN2000:0200"), [[0.0]], lowerLeftCellX=1, lowerLeftCellY=1),
    )
    assert read_dss_grid(file, RainSpec()).depths[1].tolist() == [[0.0] * 3] * 3


def test_frames_on_different_cell_sizes_are_refused(tmp_path: Path) -> None:
    file = _write(
        tmp_path,
        _grid(_at("01JAN2000:0000", "01JAN2000:0100"), [[1.0]]),
        _grid(_at("01JAN2000:0100", "01JAN2000:0200"), [[1.0]], cellSize=200.0),
    )
    with pytest.raises(ValueError, match="not on the same grid"):
        read_dss_grid(file, RainSpec())


@pytest.mark.parametrize("end", ["", "01JAN2000:0100"], ids=["no E part", "E equal to D"])
def test_a_grid_with_no_period_is_refused_plainly(tmp_path: Path, end: str) -> None:
    file = _write(tmp_path, _grid(_at("01JAN2000:0100", end), [[1.0]], dataType=2))
    with pytest.raises(ValueError, match="instantaneous"):
        read_dss_grid(file, RainSpec())


def test_e_equal_to_d_is_seen_through_the_2400_notation(tmp_path: Path) -> None:
    file = _write(tmp_path, _grid(_at("02JAN2000:0000", "01JAN2000:2400"), [[1.0]]))
    with pytest.raises(ValueError, match="instantaneous"):
        read_dss_grid(file, RainSpec())


def test_an_instantaneous_grid_takes_its_period_from_the_job(tmp_path: Path) -> None:
    file = _write(
        tmp_path,
        _grid(_at("01JAN2000:0100", ""), [[1.0]], dataType=2),
        _grid(_at("01JAN2000:0200", ""), [[3.0]], dataType=2, dataUnits="MM/HR"),
    )
    closing = read_dss_grid(file, RainSpec(interval_min=60.0))
    assert closing.origin == np.datetime64("2000-01-01T00:00:00")
    assert closing.ends_min.tolist() == [60.0, 120.0]
    assert closing.depths[:, 0, 0].tolist() == [1.0, 3.0]
    opening = read_dss_grid(file, RainSpec(interval_min=60.0, stamp="start"))
    assert opening.origin == np.datetime64("2000-01-01T01:00:00")


def test_the_pathname_period_beats_the_interval_of_the_job(tmp_path: Path) -> None:
    file = _write(tmp_path, _grid(PERIOD, [[1.0]]))
    assert read_dss_grid(file, RainSpec(interval_min=5.0)).ends_min.tolist() == [60.0]


def test_a_grid_with_no_date_is_refused(tmp_path: Path) -> None:
    file = _write(tmp_path, _grid("/SHG/TEST/PRECIP////", [[1.0]], type=431))
    with pytest.raises(ValueError, match="not a date and time"):
        read_dss_grid(file, RainSpec())


def test_cell_zero_moves_the_grid(tmp_path: Path) -> None:
    file = _write(
        tmp_path,
        _grid(
            PERIOD,
            np.ones((2, 3)),
            lowerLeftCellX=3,
            lowerLeftCellY=4,
            xCoordOfGridCellZero=1000.0,
            yCoordOfGridCellZero=2000.0,
        ),
    )
    frames = read_dss_grid(file, RainSpec())
    assert (frames.west, frames.north) == (1300.0, 2600.0)


def test_negative_cell_indices_are_west_and_south_of_cell_zero(tmp_path: Path) -> None:
    file = _write(tmp_path, _grid(PERIOD, np.ones((2, 3)), lowerLeftCellX=-104, lowerLeftCellY=-58))
    frames = read_dss_grid(file, RainSpec())
    assert (frames.west, frames.north) == (-10400.0, -5600.0)


@pytest.mark.parametrize(
    ("grid_type", "name"),
    [(410, "Stereographic_CONUS_HRAP"), (420, "USA_Contiguous_Albers_Equal_Area_Conic_USGS_version")],
)
def test_hrap_and_albers_grids_keep_their_system_when_the_file_has_none(
    tmp_path: Path, grid_type: int, name: str
) -> None:
    file = _write(tmp_path, _grid(PERIOD, [[1.0]], type=grid_type, srsDefinition=""))
    assert pyproj.CRS.from_user_input(read_dss_grid(file, RainSpec()).crs).name == name


def test_the_hrap_system_puts_a_cell_where_hrap_says(tmp_path: Path) -> None:
    file = _write(
        tmp_path,
        _grid(
            PERIOD,
            [[1.0]],
            type=410,
            srsDefinition="",
            cellSize=4762.5,
            lowerLeftCellX=401,
            lowerLeftCellY=401,
        ),
    )
    frames = read_dss_grid(file, RainSpec())
    lon, lat = pyproj.Transformer.from_crs(frames.crs, 4326, always_xy=True).transform(
        frames.west, frames.north - frames.dy
    )
    assert lon == pytest.approx(-105.0)
    assert lat > 0.0


def test_a_specified_grid_with_no_system_has_none(tmp_path: Path) -> None:
    file = _write(tmp_path, _grid(PERIOD, [[1.0]], srsDefinition=""))
    assert read_dss_grid(file, RainSpec()).crs == ""


def test_a_system_nobody_can_read_is_refused(tmp_path: Path) -> None:
    file = _write(tmp_path, _grid(PERIOD, [[1.0]], srsDefinition="not a coordinate system"))
    with pytest.raises(ValueError, match="coordinate system"):
        read_dss_grid(file, RainSpec())


def test_a_dss_6_file_and_a_file_that_is_not_dss_say_so(tmp_path: Path) -> None:
    old = tmp_path / "old.dss"
    old.write_bytes(b"ZDSS" + bytes(12) + b"6-YO" + bytes(100))
    with pytest.raises(ValueError, match="version 6"):
        read_dss_grid(old, RainSpec())
    with pytest.raises(ValueError, match="version 6"):
        dss_choices(old)
    other = tmp_path / "other.dss"
    other.write_bytes(b"not a dss file at all, this one")
    with pytest.raises(ValueError, match="not a DSS file"):
        read_dss_grid(other, RainSpec())


def test_a_missing_file_says_so(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        read_dss_grid(tmp_path / "none.dss", RainSpec())


def test_the_source_file_is_left_exactly_as_it_was(tmp_path: Path) -> None:
    file = _write(tmp_path, _grid(PERIOD, [[1.0]]))
    before = file.read_bytes()
    read_dss_grid(file, RainSpec())
    dss_choices(file)
    assert file.read_bytes() == before


def test_the_registry_reaches_this_reader(tmp_path: Path) -> None:
    file = _write(
        tmp_path,
        _grid(_at("01JAN2000:0000", "01JAN2000:0100"), [[1.0]]),
        _grid(_at("01JAN2000:0100", "01JAN2000:0200"), [[3.0]]),
    )
    assert rain_format(file) == DSS
    assert rain_choices(file) == ["TEST/PRECIPITATION/SYN"]
    assert read_rain(file, RainSpec()).depths[:, 0, 0].tolist() == [1.0, 3.0]
    late = read_rain(file, RainSpec(), start="2000-01-01T01:00:00")
    assert late.depths[:, 0, 0].tolist() == [3.0]
    assert late.origin == np.datetime64("2000-01-01T01:00:00")


def test_hrap_wkt_is_readable_on_its_own() -> None:
    assert pyproj.CRS.from_user_input(HRAP_WKT).is_projected


def test_a_system_longer_than_hecdss_reads_by_default_comes_back_whole(tmp_path: Path) -> None:
    psd93 = pyproj.CRS.from_epsg(3440).to_wkt("WKT1_GDAL")
    assert len(psd93) > 600
    file = _write(tmp_path, _grid(PERIOD, [[1.0]], srsDefinition=psd93))
    assert pyproj.CRS.from_user_input(read_dss_grid(file, RainSpec()).crs).to_epsg() == 3440
