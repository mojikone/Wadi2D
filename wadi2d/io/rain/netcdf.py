"""Rain in a CF NetCDF file. Interface: :func:`read_netcdf`, :func:`netcdf_choices`.

Axes come from their CF attributes, then their names, so (time, lon, lat) and (time, lat, lon) read alike, and a
south-up grid comes out north-up. Periods come from the time variable's bounds where it has them; a bare time closes its
period or opens it as the job says, because no attribute can tell, and that choice moves the rain by one period. Only
a regular grid is read: a curvilinear or Gaussian grid is refused, not interpolated. Rain accumulated from the start of
a forecast is not unpicked; :meth:`RainFrames.looks_cumulative` warns about it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from wadi2d.io.rain import NETCDF, RAIN_CHOICES, RAIN_READERS
from wadi2d.io.rain.netcdf_file import Variable, open_netcdf
from wadi2d.storm.rain_frames import SECONDS_PER_MINUTE, RainFrames, RainSpec, depth_in_mm

RAIN_STANDARD_NAMES = (
    "precipitation_amount", "rainfall_amount", "lwe_thickness_of_precipitation_amount", "precipitation_flux",
    "rainfall_rate", "lwe_precipitation_rate", "rainfall_flux", "thickness_of_rainfall_amount",
)  # fmt: skip
RAIN_NAMES = ("precipitation", "precipitationcal", "precip", "rain", "rainfall", "tp", "pr", "apcp", "prcp")
X_NAMES = ("lon", "longitude", "x", "easting", "xc")
Y_NAMES = ("lat", "latitude", "y", "northing", "yc")
X_STANDARD = ("longitude", "projection_x_coordinate")
Y_STANDARD = ("latitude", "projection_y_coordinate")
TIME_NAMES = ("time", "t")
CALENDARS = ("", "standard", "gregorian", "proleptic_gregorian")
TIME_UNITS = {"second": 1.0, "sec": 1.0, "minute": 60.0, "min": 60.0, "hour": 3600.0, "hr": 3600.0, "day": 86400.0}
SINCE = re.compile(
    r"^\s*(\w+?)s?\s+since\s+(\d{1,4})-(\d{1,2})-(\d{1,2})(?:[ T](\d{1,2})(?::(\d{1,2}))?(?::(\d{1,2}))?)?",
    re.IGNORECASE,
)
REGULAR = 1e-2
"""Largest spread of the pixel size along an axis, as a share of it."""
LONLAT = "EPSG:4326"
FRAME_AXES = 3


@dataclass(frozen=True)
class _Axis:
    """A regular axis, its pixel size and whether it runs backwards."""

    edge: float
    step: float
    flip: bool


def _low(variable: Variable, key: str) -> str:
    return str(variable.attrs.get(key, "")).lower()


def _is_time(v: Variable) -> bool:
    return _low(v, "axis") == "t" or _low(v, "standard_name") == "time" or " since " in _low(v, "units")


def _time_dim(variables: dict[str, Variable]) -> str | None:
    for name, v in variables.items():
        if len(v.dims) == 1 and v.dims[0] == name and (_is_time(v) or name.lower() in TIME_NAMES):
            return name
    return None


def _is_x(v: Variable) -> bool:
    return _low(v, "axis") == "x" or _low(v, "standard_name") in X_STANDARD or _low(v, "units") == "degrees_east"


def _is_y(v: Variable) -> bool:
    return _low(v, "axis") == "y" or _low(v, "standard_name") in Y_STANDARD or _low(v, "units") == "degrees_north"


def _space_dim(variables: dict[str, Variable], dims: tuple[str, ...], test, names: tuple[str, ...]) -> str | None:
    for dim in dims:
        v = variables.get(dim)
        if v is not None and test(v):
            return dim
    return next((dim for dim in dims if dim.lower() in names), None)


def rain_variables(variables: dict[str, Variable]) -> list[Variable]:
    """Variables on time and two space axes."""
    time = _time_dim(variables)
    found = []
    for v in variables.values():
        if time is None or time not in v.dims or len(v.dims) < FRAME_AXES:
            continue
        if _space_dim(variables, v.dims, _is_x, X_NAMES) and _space_dim(variables, v.dims, _is_y, Y_NAMES):
            found.append(v)
    return found


def _pick(variables: dict[str, Variable], wanted: str | None, name: str) -> Variable:
    found = rain_variables(variables)
    if wanted is not None:
        for v in found:
            if v.name == wanted:
                return v
        raise ValueError(f"{name}: no rain variable {wanted!r}; it has {[v.name for v in found]}")
    if not found:
        raise ValueError(f"{name}: no variable on time and two space axes; only a regular grid can be read")
    named = [v for v in found if _low(v, "standard_name") in RAIN_STANDARD_NAMES or v.name.lower() in RAIN_NAMES]
    if len(found) == 1 or len(named) == 1:
        return found[0] if len(found) == 1 else named[0]
    raise ValueError(f"{name}: say which variable is the rain: {[v.name for v in found]}")


def _axis(variables: dict[str, Variable], dim: str, name: str) -> _Axis:
    if dim not in variables:
        raise ValueError(f"{name}: the axis {dim!r} has no coordinates")
    values = variables[dim].load()
    if values.ndim != 1 or values.size < 2:
        raise ValueError(f"{name}: the axis {dim!r} needs at least two coordinates")
    gaps = np.diff(values)
    step = float(gaps.mean())
    if np.ptp(gaps) > REGULAR * abs(step):
        raise ValueError(f"{name}: the axis {dim!r} is not regular, and only a regular grid can be read")
    low = float(values.min())
    return _Axis(low - abs(step) / 2.0, abs(step), step < 0.0)


def _times_s(v: Variable, name: str) -> tuple[np.ndarray, np.datetime64 | None]:
    """Seconds from the first stamp's reference, and that reference."""
    values = v.load()
    if _low(v, "calendar") not in CALENDARS:
        raise ValueError(f"{name}: the calendar {_low(v, 'calendar')!r} is not one this reads")
    match = SINCE.match(str(v.attrs.get("units", "")))
    if match is None:
        return values, None
    unit = TIME_UNITS.get(match[1].lower())
    if unit is None:
        raise ValueError(f"{name}: the time unit {match[1]!r} is not one this reads")
    year, month, day = int(match[2]), int(match[3]), int(match[4])
    hour, minute, second = (int(match[k] or 0) for k in (5, 6, 7))
    text = f"{year:04d}-{month:02d}-{day:02d}T{hour:02d}:{minute:02d}:{second:02d}"
    return np.round(values * unit), np.datetime64(text, "s")


def _periods(variables, time: Variable, spec: RainSpec, name: str) -> tuple[np.ndarray, np.ndarray, np.datetime64 | None]:
    """Start and end of each period in minutes from the first start, and that start's date."""
    stamps, reference = _times_s(time, name)
    bounds = variables.get(str(time.attrs.get("bounds", "")))
    if bounds is not None:
        edges, _ = _times_s(Variable(bounds.name, bounds.dims, {**bounds.attrs, "units": time.attrs.get("units", "")}, bounds.native), name)
        starts, ends = edges[:, 0], edges[:, 1]
    else:
        if spec.interval_min is not None:
            lengths = np.full(stamps.size, spec.interval_min * SECONDS_PER_MINUTE)
        elif stamps.size < 2:
            raise ValueError(f"{name}: one frame with no bounds needs the length of its period")
        else:
            gaps = np.diff(stamps)
            lengths = np.concatenate(([gaps[0]], gaps)) if spec.stamp == "end" else np.append(gaps, gaps[-1])
        starts, ends = (stamps - lengths, stamps) if spec.stamp == "end" else (stamps, stamps + lengths)
    zero = float(starts[0])
    origin = None if reference is None else reference + np.timedelta64(int(zero), "s")
    return (starts - zero) / SECONDS_PER_MINUTE, (ends - zero) / SECONDS_PER_MINUTE, origin


def _crs(variables: dict[str, Variable], v: Variable, xdim: str) -> str:
    mapping = variables.get(str(v.attrs.get("grid_mapping", "")))
    if mapping is not None:
        for key in ("crs_wkt", "spatial_ref"):
            if key in mapping.attrs:
                return str(mapping.attrs[key])
    x = variables[xdim]
    return LONLAT if _low(x, "units").startswith("degree") or xdim.lower().startswith("lon") else ""


@RAIN_READERS.register(NETCDF)
def read_netcdf(path: Path, spec: RainSpec) -> RainFrames:
    with open_netcdf(path) as variables:
        v = _pick(variables, spec.variable, path.name)
        tdim = _time_dim(variables)
        xdim = _space_dim(variables, v.dims, _is_x, X_NAMES)
        ydim = _space_dim(variables, v.dims, _is_y, Y_NAMES)
        extra = [d for n, d in enumerate(v.dims) if d not in (tdim, xdim, ydim) and v.native.shape[n] != 1]
        if extra:
            raise ValueError(f"{path.name}: {v.name} has more axes than time and space: {extra}")
        starts, ends, origin = _periods(variables, variables[tdim], spec, path.name)
        x, y = _axis(variables, xdim, path.name), _axis(variables, ydim, path.name)
        values = v.load()
        crs = _crs(variables, v, xdim)
    keep = [d for d in v.dims if d in (tdim, ydim, xdim)]
    values = values.reshape([size for d, size in zip(v.dims, values.shape, strict=True) if d in keep])
    frames = np.transpose(values, [keep.index(tdim), keep.index(ydim), keep.index(xdim)])
    if not y.flip:
        frames = frames[:, ::-1, :]  # a rising axis has its south first
    if x.flip:
        frames = frames[:, :, ::-1]
    north = y.edge + y.step * frames.shape[1]
    depths = depth_in_mm(frames, str(v.attrs.get("units", "")), spec.units, ends - starts)
    return RainFrames(depths, starts, ends, x.edge, north, x.step, y.step, crs, origin)


def netcdf_choices(path: Path) -> list[str]:
    with open_netcdf(path) as variables:
        return [v.name for v in rain_variables(variables)]


RAIN_CHOICES[NETCDF] = netcdf_choices
