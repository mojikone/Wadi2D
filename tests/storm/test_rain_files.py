"""The NetCDF and GeoTIFF rain readers, on files written here in both NetCDF formats."""

from __future__ import annotations

import json
import os
from pathlib import Path

import h5py
import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin
from scipy.io import netcdf_file

from wadi2d.engine import cli
from wadi2d.engine.rain_info import rain_info
from wadi2d.io.rain import rain_choices, rain_format, read_rain
from wadi2d.storm.rain_frames import RainSpec

NORTH_WET = np.array([[[0.0, 0.0, 0.0], [0.0, 0.0, 0.0]], [[6.0, 6.0, 6.0], [0.0, 0.0, 0.0]]])
"""Two frames of 2 x 3 pixels, written north first: the second frame rains on the northern row only."""
LAT = np.array([23.0, 24.0])
LON = np.array([56.0, 57.0, 58.0])
HOURS = np.array([1.0, 2.0])


def _text(value: str) -> np.bytes_:
    return np.bytes_(value)


def write_hdf5(path: Path, data: np.ndarray, *, units="mm", lat=LAT, lon=LON, order=("time", "lat", "lon"), hours=HOURS, extra=None) -> None:
    """A NetCDF-4 file as a NetCDF library lays it out; ``data`` is (time, lat, lon) with lat as given."""
    with h5py.File(path, "w") as f:
        axes = {"time": hours, "lat": lat, "lon": lon}
        scales = {}
        for name, values in axes.items():
            scales[name] = f.create_dataset(name, data=values)
            scales[name].make_scale(name)
        f["time"].attrs["units"] = _text("hours since 2021-10-03 00:00:00")
        f["time"].attrs["calendar"] = _text("gregorian")
        f["lat"].attrs["units"] = _text("degrees_north")
        f["lon"].attrs["units"] = _text("degrees_east")
        rain = f.create_dataset("rain", data=np.transpose(data, [("time", "lat", "lon").index(a) for a in order]))
        rain.attrs["units"] = _text(units)
        for n, name in enumerate(order):
            rain.dims[n].attach_scale(scales[name])
        if extra:
            extra(f, rain, scales)


def write_classic(path: Path, data: np.ndarray, units="mm/h") -> None:
    with netcdf_file(path, "w") as f:
        f.createDimension("time", data.shape[0])
        f.createDimension("lat", LAT.size)
        f.createDimension("lon", LON.size)
        t = f.createVariable("time", "d", ("time",))
        t[:] = HOURS
        t.units = b"hours since 2021-10-03 00:00:00"
        la = f.createVariable("lat", "d", ("lat",))
        la[:] = LAT
        la.units = b"degrees_north"
        lo = f.createVariable("lon", "d", ("lon",))
        lo[:] = LON
        lo.units = b"degrees_east"
        rain = f.createVariable("precip", "h", ("time", "lat", "lon"))
        rain[:] = np.round(data / 0.1)
        rain.scale_factor = 0.1
        rain.add_offset = 0.0
        rain._FillValue = -32768
        rain.units = units.encode()


def south_first(data: np.ndarray) -> np.ndarray:
    return data[:, ::-1, :]


def test_format_comes_from_what_the_source_is(tmp_path) -> None:
    assert rain_format(tmp_path) == "geotiff"
    assert rain_format(tmp_path / "a.nc4") == "netcdf"
    assert rain_format(tmp_path / "a.DSS") == "dss"
    with pytest.raises(ValueError, match="comes as"):
        rain_format(tmp_path / "a.csv")


def test_netcdf4_south_first_comes_out_north_first(tmp_path) -> None:
    path = tmp_path / "r.nc"
    write_hdf5(path, south_first(NORTH_WET))
    f = read_rain(path, RainSpec())
    assert f.depths[1, 0].tolist() == [6.0, 6.0, 6.0]
    assert f.depths[1, 1].tolist() == [0.0, 0.0, 0.0]
    assert (f.west, f.north, f.dx, f.dy) == (55.5, 24.5, 1.0, 1.0)
    assert f.crs == "EPSG:4326"


def test_a_descending_latitude_needs_no_flip(tmp_path) -> None:
    path = tmp_path / "r.nc"
    write_hdf5(path, NORTH_WET, lat=LAT[::-1])
    assert read_rain(path, RainSpec()).depths[1, 0].tolist() == [6.0, 6.0, 6.0]


def test_lon_first_as_imerg_writes_it_reads_the_same(tmp_path) -> None:
    path = tmp_path / "r.nc"
    data = south_first(NORTH_WET).copy()
    data[1, 1, 0] = 9.0  # north-west pixel of the second frame
    write_hdf5(path, data, order=("time", "lon", "lat"))
    f = read_rain(path, RainSpec())
    assert f.depths.shape == (2, 2, 3)
    assert f.depths[1, 0, 0] == 9.0
    assert f.depths[1, 0, 1] == 6.0


def test_a_descending_longitude_is_flipped(tmp_path) -> None:
    path = tmp_path / "r.nc"
    data = NORTH_WET.copy()
    data[1, 0, 0] = 9.0
    write_hdf5(path, south_first(data), lon=LON[::-1])
    assert read_rain(path, RainSpec()).depths[1, 0, 2] == 9.0


def test_classic_netcdf_with_packing_and_rate_units(tmp_path) -> None:
    path = tmp_path / "r.nc"
    write_classic(path, south_first(NORTH_WET))
    f = read_rain(path, RainSpec(stamp="start"))
    assert f.depths[1, 0, 0] == pytest.approx(6.0)
    assert f.origin == np.datetime64("2021-10-03T01:00:00", "s")


def test_a_bare_time_closes_its_period_by_default(tmp_path) -> None:
    path = tmp_path / "r.nc"
    write_hdf5(path, NORTH_WET, lat=LAT[::-1])
    closed = read_rain(path, RainSpec())
    opened = read_rain(path, RainSpec(stamp="start"))
    assert closed.origin == np.datetime64("2021-10-03T00:00:00", "s")
    assert opened.origin == np.datetime64("2021-10-03T01:00:00", "s")
    assert closed.ends_min.tolist() == [60.0, 120.0]


def test_time_bounds_settle_the_periods_whatever_the_stamp(tmp_path) -> None:
    path = tmp_path / "r.nc"

    def bounds(f, _rain, scales):
        f["time"].attrs["bounds"] = _text("time_bnds")
        f.create_dataset("time_bnds", data=np.array([[0.5, 1.0], [1.5, 2.0]]))

    write_hdf5(path, NORTH_WET, lat=LAT[::-1], extra=bounds)
    f = read_rain(path, RainSpec(stamp="start"))
    assert f.origin == np.datetime64("2021-10-03T00:30:00", "s")
    assert f.starts_min.tolist() == [0.0, 60.0]
    assert f.ends_min.tolist() == [30.0, 90.0]


def test_fill_value_is_no_data_and_a_start_date_is_applied(tmp_path) -> None:
    path = tmp_path / "r.nc"

    def fill(_f, rain, _scales):
        rain.attrs["_FillValue"] = np.float64(-1.0)

    data = NORTH_WET.copy()
    data[0, 0, 0] = -1.0
    write_hdf5(path, data, lat=LAT[::-1], extra=fill)
    f = read_rain(path, RainSpec(), "2021-10-03T01:00:00")
    assert f.count == 1
    plain = read_rain(path, RainSpec())
    assert np.isnan(plain.depths[0, 0, 0])


def test_an_irregular_axis_is_refused(tmp_path) -> None:
    path = tmp_path / "r.nc"
    write_hdf5(path, NORTH_WET, lon=np.array([56.0, 57.0, 59.0]))
    with pytest.raises(ValueError, match="not regular"):
        read_rain(path, RainSpec())


def test_two_rain_variables_need_a_choice(tmp_path) -> None:
    path = tmp_path / "r.nc"

    def second(f, rain, scales):
        other = f.create_dataset("snow", data=rain[()])
        other.attrs["units"] = _text("mm")
        for n, name in enumerate(("time", "lat", "lon")):
            other.dims[n].attach_scale(scales[name])

    write_hdf5(path, NORTH_WET, lat=LAT[::-1], extra=second)
    assert set(rain_choices(path)) == {"rain", "snow"}
    assert read_rain(path, RainSpec()).depths[1, 0, 0] == 6.0  # the name settles it
    assert read_rain(path, RainSpec(variable="snow")).depths[1, 0, 0] == 6.0
    with pytest.raises(ValueError, match="no rain variable"):
        read_rain(path, RainSpec(variable="hail"))


def write_stack(folder: Path, names, values=(1.0, 2.0, 3.0), crs="EPSG:32640", transform=None) -> None:
    folder.mkdir(exist_ok=True)
    grid = transform or from_origin(1000.0, 5000.0, 500.0, 500.0)
    for name, value in zip(names, values, strict=True):
        data = np.full((2, 3), value, np.float32)
        data[0, 0] = -9999.0
        with rasterio.open(
            folder / name, "w", driver="GTiff", height=2, width=3, count=1, dtype="float32", crs=crs, transform=grid,
            nodata=-9999.0,
        ) as dst:  # fmt: skip
            dst.write(data, 1)


def test_geotiffs_run_in_natural_name_order(tmp_path) -> None:
    folder = tmp_path / "stack"
    write_stack(folder, ["r_10.tif", "r_2.tif", "r_1.tif"], (3.0, 2.0, 1.0))
    f = read_rain(folder, RainSpec(interval_min=30.0))
    assert f.depths[:, 1, 1].tolist() == [1.0, 2.0, 3.0]
    assert f.starts_min.tolist() == [0.0, 30.0, 60.0]
    assert np.isnan(f.depths[0, 0, 0])
    assert (f.west, f.north, f.dx, f.dy) == (1000.0, 5000.0, 500.0, 500.0)


def test_a_geotiff_folder_needs_a_period_and_one_grid(tmp_path) -> None:
    folder = tmp_path / "stack"
    write_stack(folder, ["a.tif"], (1.0,))
    with pytest.raises(ValueError, match="length of each period"):
        read_rain(folder, RainSpec())
    write_stack(folder, ["b.tif"], (1.0,), transform=from_origin(0.0, 5000.0, 500.0, 500.0))
    with pytest.raises(ValueError, match="same grid"):
        read_rain(folder, RainSpec(interval_min=30.0))


def test_rate_units_scale_a_geotiff_by_its_period(tmp_path) -> None:
    folder = tmp_path / "stack"
    write_stack(folder, ["a.tif"], (6.0,))
    assert read_rain(folder, RainSpec(interval_min=30.0, units="mm/h")).depths[0, 1, 1] == pytest.approx(3.0)


def test_rain_info_says_what_a_file_holds(tmp_path) -> None:
    path = tmp_path / "r.nc"
    write_hdf5(path, NORTH_WET, lat=LAT[::-1])
    info = rain_info(str(path))
    assert info["frames"] == 2
    assert info["period_min"] == 60.0
    assert info["start"] == "2021-10-03T00:00:00"
    assert info["max_mm"] == 6.0
    assert info["crs"] == "EPSG:4326"
    assert json.dumps(info)


def test_rain_info_asks_when_there_is_a_choice(tmp_path) -> None:
    path = tmp_path / "r.nc"

    def second(f, rain, scales):
        other = f.create_dataset("snow", data=rain[()])
        other.attrs["units"] = _text("mm")
        for n, name in enumerate(("time", "lat", "lon")):
            other.dims[n].attach_scale(scales[name])

    write_hdf5(path, NORTH_WET, lat=LAT[::-1], extra=second)
    info = rain_info(str(path))
    assert info["frames"] == 0
    assert set(info["choices"]) == {"rain", "snow"}


def test_the_command_line_reports_a_bad_file_plainly(tmp_path, capsys) -> None:
    path = tmp_path / "r.nc"
    path.write_bytes(b"not a file")
    assert cli.main(["rain", str(path)]) == cli.EXIT_RAIN
    assert "not a NetCDF file" in capsys.readouterr().err


def test_a_rain_folder_has_an_identity(tmp_path) -> None:
    from wadi2d.io.identity import file_identity

    folder = tmp_path / "stack"
    write_stack(folder, ["a.tif"], (1.0,))
    first = file_identity(folder, 10.0)
    write_stack(folder, ["b.tif"], (1.0,))
    assert file_identity(folder, 10.0) != first
    assert os.path.isdir(folder)
