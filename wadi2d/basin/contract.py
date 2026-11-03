"""``basin.json``: the basin model as data, the contract the plugin and the run read.

The file holds one ``elements`` list. Every element has ``kind``, ``name``, ``downstream``, ``outlet`` (map x, y), ``geometry``
(``layer`` and ``name`` in ``basin.gpkg``), ``parameters`` and ``missing``. A parameter is ``{"value": ..., "source": ...}``;
its source is one of the ``SOURCE_*`` names. ``missing`` names exactly what an element still lacks to run lumped.

A user edits the file by hand. :func:`refresh` runs on every read: it fills a lag or a celerity that has become computable, marks
a filled-in parameter as the user's, and rebuilds ``missing``, so that list is never out of step with the values. It never
overwrites a number that is there: to recompute a lag after changing a curve number, set the lag to null.

Interface: :func:`parameter`, :func:`value_of`, :func:`missing_of`, :func:`refresh`, :func:`read_model`, :func:`write_model`,
:func:`check_model`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from wadi2d.basin.parameters import index_celerity, kirpich_lag_minutes, nrcs_lag_minutes
from wadi2d.config.schema import LAG_HMS_KIRPICH, LAG_KIRPICH, LAG_NRCS

FORMAT = "wadi2d-basin"
FORMAT_VERSION = "1.0"
SOURCE_TERRAIN = "terrain"
SOURCE_RASTER = "raster"
SOURCE_JOB = "job"
SOURCE_DERIVED = "derived"
SOURCE_USER = "user"
SOURCE_MISSING = "missing"
SUBBASIN, REACH, JUNCTION, RESERVOIR = "subbasin", "reach", "junction", "reservoir"
KINDS = (SUBBASIN, REACH, JUNCTION, RESERVOIR)
REQUIRED = {
    SUBBASIN: ("area_km2", "curve_number", "lag_minutes"),
    REACH: ("length_m", "slope", "manning_n", "bottom_width_m", "side_slope", "index_celerity"),
    JUNCTION: (),
    RESERVOIR: ("elevation_m", "area_m2", "spillways", "initial_elevation_m"),
}
"""What an element needs to run lumped; the owner's rule reads ``missing``, built from this."""

Element = dict[str, Any]
Model = dict[str, Any]


def parameter(value: Any, source: str) -> dict[str, Any]:
    """A parameter; no value means missing, whatever the source."""
    return {"value": value, "source": SOURCE_MISSING if value is None else source}


def value_of(element: Element, key: str) -> Any:
    """A parameter's value; None when absent."""
    entry = element["parameters"].get(key)
    return None if entry is None else entry["value"]


def missing_of(element: Element) -> list[str]:
    """The parameters an element still lacks, by name."""
    return [key for key in REQUIRED[element["kind"]] if value_of(element, key) is None]


def _fill(element: Element, key: str, value: float) -> None:
    element["parameters"][key] = parameter(value, SOURCE_DERIVED)


def _lag(element: Element, method: str) -> float | None:
    """The lag by the model's method, or None while a parameter it needs is absent."""
    length = value_of(element, "flow_length_m")
    if method in (LAG_KIRPICH, LAG_HMS_KIRPICH):
        slope = value_of(element, "slope_10_85")
        return kirpich_lag_minutes(length, slope) if length and slope else None
    if method != LAG_NRCS:
        raise ValueError(f"unknown lag method {method!r}")
    curve, slope = value_of(element, "curve_number"), value_of(element, "slope")
    return nrcs_lag_minutes(length, curve, slope) if length and curve and slope else None


def _derive(element: Element, section_depth_m: float, lag_method: str) -> None:
    """Fill what follows from the rest."""
    if element["kind"] == SUBBASIN and value_of(element, "lag_minutes") is None:
        lag = _lag(element, lag_method)
        if lag is not None:
            _fill(element, "lag_minutes", round(lag, 2))
    if element["kind"] == REACH and value_of(element, "index_celerity") is None:
        names = ("manning_n", "slope", "bottom_width_m", "side_slope")
        manning, slope, width, side = (value_of(element, key) for key in names)
        if manning and slope and width is not None and side is not None:
            _fill(
                element,
                "index_celerity",
                round(index_celerity(manning, slope, width, side, section_depth_m), 3),
            )


def refresh(model: Model) -> Model:
    """Bring ``missing`` and what can be derived up to date with the values, in place."""
    depth = model["settings"]["section_depth_m"]
    method = model["settings"].get("lag_method", LAG_NRCS)  # a file written before the setting existed is NRCS
    for element in model["elements"]:
        for entry in element["parameters"].values():
            if entry["value"] is not None and entry["source"] == SOURCE_MISSING:
                entry["source"] = SOURCE_USER
        _derive(element, depth, method)
        element["missing"] = missing_of(element)
    return model


def check_model(model: Model) -> Model:
    """Refuse a file that is not a basin model, or whose links do not hold."""
    if model.get("format") != FORMAT:
        raise ValueError(f"not a basin model: format {model.get('format')!r}")
    if model.get("format_version") != FORMAT_VERSION:
        raise ValueError(
            f"basin model version {model.get('format_version')!r}; this engine reads {FORMAT_VERSION}"
        )
    names = [element["name"] for element in model["elements"]]
    doubled = sorted({name for name in names if names.count(name) > 1})
    if doubled:
        raise ValueError(f"names used twice: {doubled}")
    known = set(names)
    for element in model["elements"]:
        if element["kind"] not in KINDS:
            raise ValueError(f"{element['name']}: unknown kind {element['kind']!r}")
        target = element["downstream"]
        if target is not None and target not in known:
            raise ValueError(f"{element['name']} drains to unknown element {target}")
    return model


def read_model(path: str | Path) -> Model:
    """A checked, refreshed model from its file."""
    return refresh(check_model(json.loads(Path(path).read_text(encoding="utf-8"))))


def write_model(model: Model, path: Path) -> Path:
    """Write through a temporary name; a basin model already there stays beside it as ``.previous``."""
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(model, indent=1), encoding="utf-8")
    if path.exists():
        path.replace(path.with_suffix(".previous.json"))
    tmp.replace(path)
    return path
