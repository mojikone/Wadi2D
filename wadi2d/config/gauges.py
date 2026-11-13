"""Rain gauges and observed series in a job: the parts of the schema that name station records (W54).

Interface: :class:`Gauge`, :class:`GaugeRain` (``storm.gauges``), :class:`Observed` (``outputs.observed``). A station
record is a CSV table or a DSS time series; :mod:`wadi2d.io.series` says which layouts are read. Times in a file are a
clock with no time zone: every gauge, every observed record and ``storm.rain_start`` must be on the same one.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

TimeUnit = Literal["s", "min", "h", "d"]
THIESSEN, INVERSE_DISTANCE = "thiessen", "inverse_distance"
GAPS_ERROR, GAPS_ZERO, GAPS_NEIGHBOURS = "error", "zero", "neighbours"
COMPARE_LINE, COMPARE_POINT, COMPARE_ELEMENT = "line", "point", "element"
FLOW, LEVEL, DEPTH = "flow", "level", "depth"
TIME_FORMAT_NOTE = (
    "How a CSV writes its dates, as a strptime pattern such as %d/%m/%Y %H:%M; None reads dates written year first "
    "(2021-10-04 00:05) or as HEC writes them (04Oct2021 00:05)"
)


class _Part(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Gauge(_Part):
    """A rain gauge: where it stands and the record it wrote."""

    name: str
    x: float | None = Field(None, description="Easting in the DEM's coordinate system, m; None takes the HMS gage's")
    y: float | None = Field(None, description="Northing in the DEM's coordinate system, m; None takes the HMS gage's")
    file: str | None = Field(None, description="CSV table or DSS file of the record")
    record: str | None = Field(
        None,
        description="In a CSV, the heading of the value column, None being the second column; in a DSS file, the "
        "pathname of the record or its B/C or B/C/F parts, None being the only precipitation series",
    )
    hms_gage: str | None = Field(
        None, description="A precipitation gage of the HMS project, by name: its DSS file and pathname replace file and record"
    )
    values: Literal["incremental", "cumulative"] = Field(
        "incremental",
        description="What a CSV holds: the depth fallen in each period, or the depth since the start of the record. A DSS "
        "record says so itself (PER-CUM or INST-CUM)",
    )
    units: Literal["mm", "cm", "m", "in"] = Field("mm", description="Depth units of a CSV; a DSS record brings its own")
    time_unit: TimeUnit = Field("min", description="Unit of a CSV's times when they are numbers counted from the run's start")
    time_format: str | None = Field(None, description=TIME_FORMAT_NOTE)
    interval_min: float | None = Field(
        None,
        gt=0.0,
        description="Length of a period of incremental values, minutes. None reads it from the spacing of the times, and "
        "then a missing row cannot be told from a long period; with it, a spacing longer than this is a gap",
    )

    @model_validator(mode="after")
    def _source(self) -> Gauge:
        if (self.file is None) == (self.hms_gage is None):
            raise ValueError(f"rain gauge {self.name} needs either file or hms_gage")
        if self.hms_gage is None and (self.x is None or self.y is None):
            raise ValueError(f"rain gauge {self.name} needs its position, x and y")
        return self


class GaugeRain(_Part):
    """Rain from gauges, spread over the cells and the lumped subbasins by one spatial method (W54)."""

    gauges: list[Gauge] = Field(
        [], description="The gauges; empty takes every precipitation gage of the HMS project that has a position"
    )
    method: Literal["thiessen", "inverse_distance"] = Field(
        THIESSEN,
        description="'thiessen': a place takes its nearest gauge. 'inverse_distance': gauges weighted by 1 / distance^power, "
        "as HEC-HMS's Inverse Distance method",
    )
    power: float = Field(2.0, gt=0.0, le=10.0, description="Exponent of the inverse distance; HEC-HMS uses 2")
    search_radius_m: float | None = Field(
        None,
        gt=0.0,
        description="Inverse distance looks no farther than this for gauges, m; None looks at all of them. A place with no "
        "gauge inside it takes its nearest gauge, and the run says how many cells did",
    )
    quadrants: bool = Field(
        True,
        description="Inverse distance uses the nearest gauge in each of the four quadrants north-east, north-west, "
        "south-west and south-east of a place, as HEC-HMS does, so a cluster of gauges counts once; false uses every "
        "gauge within the search radius",
    )
    weights: dict[str, dict[str, float]] | None = Field(
        None,
        description="Gauge weights of lumped subbasins, by subbasin then gauge, as HEC-HMS's Gage Weights (depth weights): "
        "they replace the spatial method for that subbasin and are scaled to sum to 1. Cells of the 2D area always use "
        "the spatial method",
    )
    gaps: Literal["error", "zero", "neighbours"] = Field(
        GAPS_ERROR,
        description="A gauge with no value in a period that another gauge covers. 'error' stops the run and names the "
        "gauge and the time; 'zero' counts no rain there; 'neighbours' gives the gauge, for that period, what the "
        "spatial method reads at its position from the gauges that have data. A missing row of a cumulative record is "
        "always bridged by its neighbours' difference, spread evenly, once gaps is not 'error'",
    )
    samples: int = Field(
        2000, ge=100, le=200000,
        description="Points over a subbasin's polygon on which inverse distance is averaged for a lumped subbasin; "
        "Thiessen shares are exact areas and need none",
    )

    @model_validator(mode="after")
    def _names(self) -> GaugeRain:
        names = [g.name for g in self.gauges]
        if len(set(names)) != len(names):
            raise ValueError("rain gauge names must differ")
        for subbasin, weights in (self.weights or {}).items():
            unknown = sorted(set(weights) - set(names)) if names else []
            if unknown:
                raise ValueError(f"gauge weights of subbasin {subbasin} name unknown gauges: {unknown}")
            if not weights or min(weights.values()) < 0.0 or sum(weights.values()) <= 0.0:
                raise ValueError(f"gauge weights of subbasin {subbasin} must not be negative and must sum above zero")
        return self


class Observed(_Part):
    """An observed record and the result it is compared with after the run (W54)."""

    name: str
    file: str = Field(description="CSV table or DSS file of the record")
    record: str | None = Field(
        None,
        description="In a CSV, the heading of the value column, None being the second column; in a DSS file, the "
        "pathname of the record or its B/C or B/C/F parts, None being the only series of the quantity",
    )
    quantity: Literal["flow", "level", "depth"] = Field(
        FLOW,
        description="'flow', m3/s, against a result line or a lumped element; 'level', m on the DEM's datum, or 'depth', "
        "m above the cell's lowest point, against a result point",
    )
    compare: Literal["line", "point", "element"] = Field(
        COMPARE_LINE, description="What it is compared with: a result line, a result point, or a lumped element's series"
    )
    target: str = Field(description="Name of that line, point or element")
    series: Literal["outflow", "inflow"] = Field("outflow", description="Which series of a lumped element")
    time_unit: TimeUnit = Field("min", description="Unit of a CSV's times when they are numbers counted from the run's start")
    time_format: str | None = Field(None, description=TIME_FORMAT_NOTE)
    start: str | None = Field(
        None,
        description="Date and time of the run's start on this record's clock, for a record with dates; None takes the "
        "storm's (storm.rain_start, else the start of its rain)",
    )
    offset: float = Field(
        0.0, description="Added to every observed value: the shift of a level onto the DEM's datum, m"
    )

    @model_validator(mode="after")
    def _pairing(self) -> Observed:
        on_point = self.compare == COMPARE_POINT
        if on_point == (self.quantity == FLOW):
            raise ValueError(
                f"observed {self.name}: a flow is compared with a line or an element, a level or a depth with a point"
            )
        return self
