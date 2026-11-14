"""A diversion point of a generated basin as W72's diversion element (W75): the same five methods and two limits.

A ``diversion`` point (W73) writes a ``diversion`` block onto its junction in ``basin.json``. At generation the block is
read here: the method named, its numbers parsed, its tables read into the file so ``basin.json`` stands alone, as a
source's hydrograph does. The loader then builds the element from the block alone.

The layer's fields, all text as a GIS field holds them:

| field | what it holds |
|---|---|
| ``method`` | one of :data:`METHODS`, HMS's names; ``inflow function``, ``constant``, ``specified``, ``lateral weir``, ``pump`` also read |
| ``divert_to`` | the element that takes the diverted flow; blank: it leaves the network (HMS's Not Connected) |
| ``table`` | the method's table: a CSV of two columns (a header line is skipped) beside the layer, or inline JSON ``[[x, y], ...]`` |
| ``parameters`` | JSON of the method's numbers, :data:`NEEDS` |
| ``limits`` | JSON, ``max_m3s`` (also ``max_flow_m3s``) and ``max_volume_m3``, in m3, not HMS's 1000 m3 |

The table per method: Inflow-Diversion Table, inflow and diverted flow, m3/s; Specified Flow, minutes from the start of
the run and m3/s (or a CSV or DSS flow record, read as a source's); Lateral Weir and Pump Station, the channel's stage, m,
and flow, m3/s. A weir's ``tailwater`` and a station's ``pump`` (head, m, and flow per unit, m3/s) are tables named in
``parameters``, in the same two forms.

Interface: :data:`METHODS`, :func:`method_name`, :func:`resolve_block`, :func:`diversion_routing`, :func:`check_targets`.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import numpy as np

from wadi2d.hydrology.diversion import (
    CONSTANT_DIVERSION,
    INFLOW_DIVERSION,
    LATERAL_WEIR_DIVERSION,
    PUMP_STATION_DIVERSION,
    SPECIFIED_DIVERSION,
    ChannelRating,
    DiversionLimits,
)
from wadi2d.hydrology.routing import ROUTING_METHODS
from wadi2d.io.series import FLOW, read_record

METHODS = (INFLOW_DIVERSION, CONSTANT_DIVERSION, SPECIFIED_DIVERSION, LATERAL_WEIR_DIVERSION, PUMP_STATION_DIVERSION)
ALIASES = {
    "inflow function": INFLOW_DIVERSION,
    "inflow-diversion": INFLOW_DIVERSION,
    "inflow diversion table": INFLOW_DIVERSION,
    "constant": CONSTANT_DIVERSION,
    "specified": SPECIFIED_DIVERSION,
    "pump": PUMP_STATION_DIVERSION,
}
NEEDS: dict[str, dict[str, tuple[str, ...]]] = {
    INFLOW_DIVERSION: {"table": ("inflow, m3/s", "diverted, m3/s"), "required": (), "optional": ()},
    CONSTANT_DIVERSION: {"table": (), "required": ("rate_m3s",), "optional": ()},
    SPECIFIED_DIVERSION: {"table": ("minutes from the start", "diverted, m3/s"), "required": (), "optional": ()},
    LATERAL_WEIR_DIVERSION: {
        "table": ("channel stage, m", "channel flow, m3/s"),
        "required": ("crest_m", "length_m", "coefficient"),
        "optional": ("tailwater",),
    },
    PUMP_STATION_DIVERSION: {
        "table": ("channel stage, m", "channel flow, m3/s"),
        "required": ("units", "on_m", "off_m", "lift_m", "pump"),
        "optional": (),
    },
}
"""Per method: the ``table`` columns (none: no table), the ``parameters`` it needs and those it may take."""
TABLE_PARAMETERS = ("tailwater", "pump")
"""Parameters that name a table, read as ``table`` is."""
LIMIT_KEYS = {"max_m3s": "max_flow_m3s", "max_flow_m3s": "max_flow_m3s", "max_volume_m3": "max_volume_m3"}
EPOCH = np.datetime64("2000-01-01T00:00:00", "s")
"""A Specified Flow table counts minutes from the run's start; the W72 element counts in dates, so both start here."""
SPLIT = re.compile(r"[,;\t ]+")


def method_name(text: str | None, point: str) -> str:
    """HMS's name of a method as typed; none, or one not known, is refused by name."""
    if text is None or not str(text).strip():
        raise ValueError(f"diversion {point}: the point needs a method, one of {', '.join(METHODS)}")
    typed = " ".join(str(text).split())
    for name in METHODS:
        if typed.lower() == name.lower():
            return name
    if typed.lower() in ALIASES:
        return ALIASES[typed.lower()]
    raise ValueError(f"diversion {point}: method {typed!r} is not one of {', '.join(METHODS)}")


def _json(text: Any, what: str, point: str) -> Any:
    if text is None or isinstance(text, dict | list):
        return text
    if not str(text).strip():
        return None
    try:
        return json.loads(str(text))
    except json.JSONDecodeError as error:
        raise ValueError(f"diversion {point}: {what} {text!r} is not JSON") from error


def _pairs(rows: list, what: str, point: str) -> dict[str, list[float]]:
    try:
        x, y = zip(*[(float(a), float(b)) for a, b in rows], strict=True)
    except (TypeError, ValueError) as error:
        raise ValueError(f"diversion {point}: the {what} table needs two numbers per row") from error
    if len(x) < 2:
        raise ValueError(f"diversion {point}: the {what} table needs two rows or more")
    return {"x": list(x), "y": list(y)}


def _csv(path: Path, what: str, point: str) -> dict[str, list[float]]:
    rows = []
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        parts = [p for p in SPLIT.split(line.strip()) if p]
        if len(parts) < 2:
            continue
        try:
            rows.append((float(parts[0]), float(parts[1])))
        except ValueError:
            if rows:
                raise ValueError(f"diversion {point}: {path.name} has a line that is not two numbers: {line!r}") from None
    return _pairs(rows, what, point)


def _series(path: Path, point: str) -> dict[str, list[float]]:
    """A Specified Flow record from a CSV or DSS flow file, minutes from its first time, CFS taken to m3/s."""
    from wadi2d.basin.points import CFS_TO_M3S, CFS_UNITS

    record = read_record(path, want=FLOW)
    flows = np.asarray(record.values, dtype=np.float64)
    if record.units.strip().upper() in CFS_UNITS:
        flows = flows * CFS_TO_M3S
    minutes = (record.dates - record.dates[0]) / np.timedelta64(1, "s") / 60.0 if record.dated else record.minutes
    if not np.all(np.isfinite(flows)):
        raise ValueError(f"diversion {point}: {path.name} has missing flows")
    return {"x": [float(v) for v in minutes], "y": [float(v) for v in flows]}


def read_table(given: Any, what: str, point: str, folder: Path | None, series: bool = False) -> dict[str, list[float]]:
    """A table as ``{"x": [...], "y": [...]}``: inline JSON pairs or columns, or a file (beside the layer if relative)."""
    if given is None or (isinstance(given, str) and not given.strip()):
        raise ValueError(f"diversion {point}: the {what} is empty; it needs a table, a CSV file or inline [[x, y], ...]")
    if isinstance(given, dict) and set(given) == {"x", "y"}:
        return _pairs(list(zip(given["x"], given["y"], strict=True)), what, point)
    if isinstance(given, list):
        return _pairs(given, what, point)
    text = str(given).strip()
    if text.startswith(("[", "{")):
        return read_table(_json(text, f"{what} table", point), what, point, folder, series)
    path = Path(text) if Path(text).is_absolute() or folder is None else folder / text
    if not path.is_file():
        raise ValueError(f"diversion {point}: the {what} table {text!r} is not a file ({path})")
    if series:
        return _series(path, point)
    return _csv(path, what, point)


def _limits(raw: Any, point: str) -> dict[str, float]:
    given = _json(raw, "limits", point) or {}
    if not isinstance(given, dict):
        raise ValueError(f'diversion {point}: limits must be a JSON object, e.g. {{"max_m3s": 50}}')
    unknown = sorted(set(given) - set(LIMIT_KEYS))
    if unknown:
        raise ValueError(f"diversion {point}: limits {unknown} not known; {', '.join(LIMIT_KEYS)}")
    return {LIMIT_KEYS[key]: float(value) for key, value in given.items() if value is not None}


def resolve_block(block: dict[str, Any], folder: Path | None = None) -> dict[str, Any]:
    """The block with the method's name, its parameters and limits parsed and its tables read; checked by building it."""
    point = str(block.get("point") or "?")
    method = method_name(block.get("method"), point)
    needs = NEEDS[method]
    parameters = _json(block.get("parameters"), "parameters", point) or {}
    if not isinstance(parameters, dict):
        raise ValueError(f"diversion {point}: parameters must be a JSON object")
    allowed = set(needs["required"]) | set(needs["optional"])
    unknown = sorted(set(parameters) - allowed)
    if unknown:
        raise ValueError(f"diversion {point}: {method} takes no {unknown}; it takes {sorted(allowed) or 'none'}")
    lacking = [key for key in needs["required"] if parameters.get(key) is None]
    if lacking:
        raise ValueError(f"diversion {point}: {method} needs {lacking} in the parameters field")
    tables = dict(block.get("tables") or {})
    if needs["table"] and "table" not in tables:
        tables["table"] = read_table(block.get("table"), "table field", point, folder, method == SPECIFIED_DIVERSION)
    for key in TABLE_PARAMETERS:
        if key in parameters and key not in tables:
            tables[key] = read_table(parameters[key], f"{key} parameter", point, folder)
    out = {
        **block,
        "method": method,
        "divert_to": (str(block["divert_to"]).strip() or None) if block.get("divert_to") is not None else None,
        "parameters": {k: v for k, v in parameters.items() if k not in TABLE_PARAMETERS} or None,
        "limits": _limits(block.get("limits"), point) or None,
        "tables": tables or None,
    }
    try:
        diversion_routing(out)
    except (TypeError, ValueError) as error:
        raise ValueError(f"diversion {point}: {error}") from error
    return out


def _rating(table: dict[str, list[float]]) -> ChannelRating:
    return ChannelRating(stages_m=np.asarray(table["x"], np.float64), flows_m3s=np.asarray(table["y"], np.float64))


def diversion_routing(block: dict[str, Any]):
    """W72's routing object of a resolved block."""
    method = block["method"]
    p = block.get("parameters") or {}
    tables = block.get("tables") or {}
    limits = DiversionLimits(**(block.get("limits") or {}))
    if method == INFLOW_DIVERSION:
        t = tables["table"]
        kwargs = {"inflows_m3s": np.asarray(t["x"], np.float64), "diverted_m3s": np.asarray(t["y"], np.float64)}
    elif method == CONSTANT_DIVERSION:
        kwargs = {"rate_m3s": float(p["rate_m3s"])}
    elif method == SPECIFIED_DIVERSION:
        t = tables["table"]
        seconds = np.round(np.asarray(t["x"], np.float64) * 60.0).astype("int64")
        kwargs = {
            "start": EPOCH, "times": EPOCH + seconds.astype("timedelta64[s]"),
            "flows_m3s": np.asarray(t["y"], np.float64), "gage": str(block.get("point") or ""),
        }  # fmt: skip
    elif method == LATERAL_WEIR_DIVERSION:
        kwargs = {
            "channel": _rating(tables["table"]), "crest_m": float(p["crest_m"]), "length_m": float(p["length_m"]),
            "coefficient": float(p["coefficient"]),
            "tailwater": _rating(tables["tailwater"]) if "tailwater" in tables else None,
        }  # fmt: skip
    else:
        pump = tables["pump"]
        units = float(p["units"])
        if units != int(units) or units < 1:
            raise ValueError(f"{units} pumps")
        kwargs = {
            "channel": _rating(tables["table"]), "heads_m": np.asarray(pump["x"], np.float64),
            "flows_m3s": np.asarray(pump["y"], np.float64), "units": int(units), "on_m": float(p["on_m"]),
            "off_m": float(p["off_m"]), "lift_m": float(p["lift_m"]),
        }  # fmt: skip
    return ROUTING_METHODS.build(method, limits=limits, **kwargs)


def check_targets(elements: list[dict[str, Any]]) -> None:
    """Every diversion's ``divert_to`` is an element of the model, not itself, not where its main flow goes, and not
    above it (the run would refuse the loop at its start)."""
    by_name = {e["name"]: e for e in elements}
    names = set(by_name)
    for element in elements:
        block = element.get("diversion")
        if not block or block.get("divert_to") is None:
            continue
        target, name = block["divert_to"], element["name"]
        if target not in names:
            near = ", ".join(sorted(n for n in names if n.lower().startswith(target[:1].lower()))[:8])
            raise ValueError(
                f"diversion {name}: divert_to {target!r} is not an element of the model"
                + (f" (names starting so: {near})" if near else "")
            )
        if target in (name, element["downstream"]):
            raise ValueError(f"diversion {name}: divert_to {target!r} is the diversion or its own main channel")
        below, at = set(), target
        while at is not None and at not in below:
            below.add(at)
            at = by_name[at]["downstream"]
        if name in below:
            raise ValueError(
                f"diversion {name}: divert_to {target!r} drains back into {name}, a loop; divert to an element "
                "below it or on another branch"
            )
