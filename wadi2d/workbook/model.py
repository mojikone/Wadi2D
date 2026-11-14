"""What the dam workbook is built from: one hydrograph per dam and return period, on one time step.

Interface: :class:`Hydrograph`, :class:`Dam`, :class:`WorkbookInput`, :func:`rp_label`, :func:`rp_sort_key`,
:func:`target_sheet_name`. The sources (:mod:`wadi2d.workbook.sources`) fill these; the layout
(:mod:`wadi2d.workbook.layout`) only reads them. Flow in m3/s, pool level in m, storage in Mm3, time in hours from
the start of the run.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import numpy as np

PMP = "PMP"
YEARS = re.compile(r"^(\d+)\s*-?\s*(?:yr|year|y)$", re.IGNORECASE)
QUANTITIES = ("inflow", "outflow", "pool", "storage")
"""The columns a dam can carry per return period, in sheet order; each structure's flow follows them (W74)."""
STRUCTURE = "structure:"
"""A quantity naming one structure's flow, e.g. ``structure:orifice_1`` from W59's ``orifice_1_m3s``."""


def structure_quantity(name: str) -> str:
    return f"{STRUCTURE}{name}"


def structure_name(quantity: str) -> str | None:
    """``structure:orifice_1`` -> ``orifice_1``; None for inflow, outflow, pool and storage."""
    return quantity[len(STRUCTURE) :] if quantity.startswith(STRUCTURE) else None
READ_ME = "Read me"
PEAK_INFLOW, INFLOW_VOLUME, TIME_TO_PEAK = "Peak inflow", "Inflow volume", "Time to peak"
PEAK_OUTFLOW, ATTENUATION, HIGHEST_POOL = "Peak outflow", "Attenuation", "Highest pool level"
FIXED_SHEETS = (READ_ME, PEAK_INFLOW, INFLOW_VOLUME, TIME_TO_PEAK, PEAK_OUTFLOW, ATTENUATION, HIGHEST_POOL)
"""The workbook's own sheets; a dam's sheet may not take one of these names, nor the target period's."""
SHEET_MOST = 31
SHEET_FORBIDDEN = frozenset("[]:*?/\\")
"""Excel refuses a sheet name longer than 31 characters or holding one of these."""
STEP_TOLERANCE_S = 0.5
"""Times rounded to 4 decimals of an hour (0.36 s) still read as one regular step."""


def rp_years(rp: str) -> int | None:
    """The return period in years of a key such as ``200yr``; None for the PMP or any other name."""
    found = YEARS.match(rp.strip())
    return int(found.group(1)) if found else None


def rp_label(rp: str) -> str:
    """``200yr`` -> ``200-yr``, as W1 writes it; the PMP and other names as given."""
    years = rp_years(rp)
    return f"{years}-yr" if years is not None else rp


def rp_sort_key(rp: str) -> tuple[int, int, str]:
    """Years ascending, then the PMP, then any other name."""
    years = rp_years(rp)
    if years is not None:
        return (0, years, rp)
    return (1 if rp.upper() == PMP else 2, 0, rp)


def target_sheet_name(rp: str) -> str:
    """``200yr`` -> ``200-year``, W1's sheet name."""
    years = rp_years(rp)
    return f"{years}-year" if years is not None else rp


@dataclass(frozen=True)
class Hydrograph:
    """One return period at one dam. ``outflow``, ``pool`` and ``storage`` exist only where a reservoir routes."""

    t_h: np.ndarray
    inflow: np.ndarray
    outflow: np.ndarray | None = None
    pool: np.ndarray | None = None
    storage: np.ndarray | None = None
    structures: dict[str, np.ndarray] = field(default_factory=dict)
    """Each outflow structure's flow, m3/s, by W59's column stem (``orifice_1``, ``evaporation``), in the run's order."""

    def column(self, quantity: str) -> np.ndarray | None:
        name = structure_name(quantity)
        return self.structures.get(name) if name is not None else getattr(self, quantity)


@dataclass
class Dam:
    """A dam site or picked element: ``name`` is the model's, ``label`` the sheet's."""

    name: str
    label: str
    element_kind: str
    """What the name is in the source, e.g. ``HMS junction``; written beside it on the dam sheet."""
    catchment_km2: float | None
    series: dict[str, Hydrograph] = field(default_factory=dict)

    def quantities(self, structures: bool = True) -> tuple[str, ...]:
        """The columns this dam carries in every return period: inflow, then what any period has of the rest, then
        each structure's flow (left out with ``structures=False``)."""
        have = [q for q in QUANTITIES[1:] if any(h.column(q) is not None for h in self.series.values())]
        if structures:
            names: list[str] = []
            for h in self.series.values():
                names += [n for n in h.structures if n not in names]
            have += [structure_quantity(n) for n in names]
        return ("inflow", *have)

    @property
    def routed(self) -> bool:
        return "outflow" in self.quantities()


@dataclass
class WorkbookInput:
    """Everything the layout needs; ``dt_s`` goes into every volume formula as its number."""

    dams: list[Dam]
    return_periods: list[str]
    target: str
    dt_s: int
    source: str
    """One sentence for the Read me: where the series came from."""
    source_short: str = "model"
    """The word for the series in the dam sheets' note, e.g. ``HMS``."""
    method: str = ""
    """Shown in chart titles in brackets, e.g. ``depth-area analyses``; empty for none."""
    project: str = ""
    notes: list[str] = field(default_factory=list)

    def check(self) -> None:
        """Refuse an input the workbook cannot lay out, in words."""
        if not self.dams:
            raise ValueError("no dams or elements to write")
        if self.target not in self.return_periods:
            raise ValueError(f"target return period {self.target!r} is not among {self.return_periods}")
        labels = [d.label for d in self.dams]
        if len({label.casefold() for label in labels}) != len(labels):
            raise ValueError(f"two dams share a sheet name: {labels}")
        taken = {name.casefold() for name in (*FIXED_SHEETS, target_sheet_name(self.target))}
        for label in labels:
            if not label.strip() or len(label) > SHEET_MOST or SHEET_FORBIDDEN & set(label):
                raise ValueError(
                    f"sheet name {label!r}: Excel takes 1 to {SHEET_MOST} characters and none of {''.join(sorted(SHEET_FORBIDDEN))}"
                )
            if label.casefold() in taken:
                raise ValueError(f"sheet name {label!r} is one of the workbook's own sheets")
        for dam in self.dams:
            missing = [rp for rp in self.return_periods if rp not in dam.series]
            if missing:
                raise ValueError(f"{dam.name}: no series for {missing}")
            for rp, h in dam.series.items():
                step = np.diff(h.t_h) * 3600.0
                if len(step) and np.max(np.abs(step - self.dt_s)) > STEP_TOLERANCE_S:
                    raise ValueError(f"{dam.name} {rp}: the step is not {self.dt_s} s throughout")
