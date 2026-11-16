"""Roughness and infiltration overrides in a job: the parts of the schema that map ground to n and CN (W96).

Interface: :class:`Roughness` (``terrain.roughness``), :class:`CurveOverride` (``hydrology.cn_override``),
:data:`MODEL_TYPES` (``run.model_type``). The tables they describe are built by :mod:`wadi2d.land`; nothing here reads a
file. A job that sets neither part runs and hashes as it did before them.
"""

from __future__ import annotations

import itertools
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

ROUGH_UNIFORM, ROUGH_SPLIT, ROUGH_GRID, ROUGH_LAND_USE = "uniform", "split", "grid", "land_use"
RoughnessForm = Literal["uniform", "split", "grid", "land_use"]
CN_LAND_USE, CN_RANGE, CN_SUBBASIN = "land_use", "range", "subbasin"
MODEL_2D, MODEL_LUMPED, MODEL_HYBRID_LUMPED, MODEL_HYBRID_2D = "2d", "lumped", "hybrid_lumped", "hybrid_2d"
MODEL_TYPES = (MODEL_2D, MODEL_LUMPED, MODEL_HYBRID_LUMPED, MODEL_HYBRID_2D)
ModelType = Literal["2d", "lumped", "hybrid_lumped", "hybrid_2d"]
N_MIN, N_MAX = 0.008, 0.5
"""The bounds of a Manning n anywhere in a job, s/m^(1/3): those of ``terrain.manning``."""


class _Part(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ManningClass(_Part):
    """One row of a land-use table of roughness."""

    code: int = Field(description="The class's value in the land-use raster")
    n: float = Field(ge=N_MIN, le=N_MAX, description="Manning n of the class, s/m^(1/3)")
    name: str = Field("", description="What the class is, for the dock and the run's notes")


def _unique_codes(codes: list[int], what: str) -> None:
    twice = sorted({c for c in codes if codes.count(c) > 1})
    if twice:
        raise ValueError(f"{what} lists the land-use classes {twice} twice")


class Roughness(_Part):
    """Manning n in one of four forms. Absent, ``terrain.manning`` and ``terrain.manning_raster`` hold as before."""

    form: RoughnessForm = Field(
        description="'uniform': one n for every cell. 'split': one n for the square cells and one for the aligned "
        "cells of the strips. 'grid': a raster of n. 'land_use': a raster of land-use classes and a table of n per class"
    )
    n: float | None = Field(
        None,
        ge=N_MIN,
        le=N_MAX,
        description="'uniform': every cell; 'split': the square cells; 'grid' and 'land_use': cells the raster gives "
        "nothing (off it, or nodata), where None takes terrain.manning. s/m^(1/3)",
    )
    n_aligned: float | None = Field(
        None, ge=N_MIN, le=N_MAX, description="'split': the aligned cells of the strips (strips.enabled), s/m^(1/3)"
    )
    raster: str | None = Field(None, description="'grid': the Manning raster, n per pixel, read at the cell centres")
    land_use: str | None = Field(
        None, description="'land_use': the raster of class codes, read at the cell centres (nearest pixel)"
    )
    classes: list[ManningClass] = Field([], description="'land_use': n per class; a class found and not listed stops the run")

    @model_validator(mode="after")
    def _form(self) -> Roughness:
        needs = {
            ROUGH_UNIFORM: ("n",),
            ROUGH_SPLIT: ("n", "n_aligned"),
            ROUGH_GRID: ("raster",),
            ROUGH_LAND_USE: ("land_use", "classes"),
        }[self.form]
        allowed = set(needs) | ({"n"} if self.form in (ROUGH_GRID, ROUGH_LAND_USE) else set())
        for name in needs:
            if getattr(self, name) in (None, []):
                raise ValueError(f"terrain.roughness form {self.form!r} needs {name}")
        for name in ("n", "n_aligned", "raster", "land_use", "classes"):
            if name not in allowed and getattr(self, name) not in (None, []):
                raise ValueError(f"terrain.roughness form {self.form!r} takes no {name}: it would be ignored")
        _unique_codes([c.code for c in self.classes], "terrain.roughness")
        return self


class CurveClass(_Part):
    """One row of a land-use table of curve numbers."""

    code: int = Field(description="The class's value in the land-use raster")
    curve_number: float = Field(gt=0.0, le=100.0, description="CN of the class")
    name: str = Field("", description="What the class is, for the dock and the run's notes")


class CurveRange(_Part):
    """CN values from ``low`` to ``high``, both included, become ``curve_number``."""

    low: float = Field(gt=0.0, le=100.0)
    high: float = Field(gt=0.0, le=100.0)
    curve_number: float = Field(gt=0.0, le=100.0, description="The CN every value in the range becomes")

    @model_validator(mode="after")
    def _order(self) -> CurveRange:
        if self.high < self.low:
            raise ValueError(f"a CN range runs from low to high: {self.low:g} to {self.high:g}")
        return self


class SubbasinCurve(_Part):
    """One subbasin's CN."""

    name: str = Field(description="A subbasin of the run's lumped network, or one with a polygon")
    curve_number: float = Field(gt=0.0, le=100.0)


class CurveOverride(_Part):
    """CN in place of what the CN grid, the job and the basin file give, on rain-on-grid cells and lumped subbasins
    alike. 'land_use': each class's CN from a land-use raster; a cell takes its class's, a lumped subbasin the mean
    of its polygon's pixels. 'range': every CN in a range becomes one value, a cell's and a lumped subbasin's own.
    'subbasin': a CN by subbasin name, the cells of its polygon and its lumped loss."""

    by: Literal["land_use", "range", "subbasin"]
    land_use: str | None = Field(None, description="'land_use': the raster of class codes")
    classes: list[CurveClass] = Field([], description="'land_use': CN per class; a class found and not listed stops the run")
    ranges: list[CurveRange] = Field([], description="'range': the ranges, none overlapping another")
    subbasins: list[SubbasinCurve] = Field([], description="'subbasin': CN by name")

    @model_validator(mode="after")
    def _by(self) -> CurveOverride:
        needs = {
            CN_LAND_USE: ("land_use", "classes"),
            CN_RANGE: ("ranges",),
            CN_SUBBASIN: ("subbasins",),
        }[self.by]
        for name in needs:
            if getattr(self, name) in (None, []):
                raise ValueError(f"hydrology.cn_override by {self.by!r} needs {name}")
        for name in ("land_use", "classes", "ranges", "subbasins"):
            if name not in needs and getattr(self, name) not in (None, []):
                raise ValueError(f"hydrology.cn_override by {self.by!r} takes no {name}: it would be ignored")
        _unique_codes([c.code for c in self.classes], "hydrology.cn_override")
        spans = sorted((r.low, r.high) for r in self.ranges)
        for (_lo, hi), (lo, _hi) in itertools.pairwise(spans):
            if lo <= hi:
                raise ValueError(f"hydrology.cn_override: the CN ranges overlap at {lo:g} to {hi:g}")
        names = [s.name for s in self.subbasins]
        if len(set(names)) != len(names):
            raise ValueError("hydrology.cn_override names a subbasin twice")
        return self
