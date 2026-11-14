"""The ``.gage`` file of an HEC-HMS project: its time-series gages. Interface: :func:`load`, :func:`beside`, :class:`HmsGage`.

A gage is a name, a type (Precipitation, Flow, Stage ...), units, a DSS data type, and the DSS file and pathname of its
record. HEC-HMS 4.12 keeps the file and pathname in a ``Variant`` sub-block and marks one ``Default Variant: Yes``;
older versions keep them in the gage block itself, and both are read. A position is optional in HMS, in degrees with
no datum named: it is read where present, as decimal degrees or as degrees, minutes and seconds. Read from a real
4.12 project with seven gages; no project with gage positions was at hand, so those keys are [Likely], from the HMS
documentation. A file with only its ``Gage Manager`` block has no gages, which is not an error.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PureWindowsPath

from wadi2d.hms import text
from wadi2d.hms.text import Block

GAGE_KIND = "Gage"
VARIANT_KIND = "Variant"
PRECIPITATION = "Precipitation"
FLOW = "Flow"
STAGE = "Stage"
SUFFIX = ".gage"
YES = "yes"
MINUTES_PER_DEGREE, SECONDS_PER_DEGREE = 60.0, 3600.0


@dataclass(frozen=True)
class HmsGage:
    """One gage as the project holds it; ``dss_file`` is absolute."""

    name: str
    kind: str
    units: str
    data_type: str
    dss_file: Path | None
    pathname: str | None
    latitude: float | None = None
    longitude: float | None = None

    @property
    def is_rain(self) -> bool:
        return self.kind.casefold() == PRECIPITATION.casefold()


def _degrees(block: Block, word: str) -> float | None:
    """A latitude or longitude: one decimal value, or degrees with minutes and seconds carrying the sign of the degrees."""
    plain = block.get(word)
    degrees = block.get(f"{word} Degrees")
    try:
        if plain is not None:
            return float(plain)
        if degrees is None:
            return None
        whole = float(degrees)
        rest = float(block.get(f"{word} Minutes") or 0.0) / MINUTES_PER_DEGREE
        rest += float(block.get(f"{word} Seconds") or 0.0) / SECONDS_PER_DEGREE
    except ValueError:
        return None
    return whole - rest if degrees.strip().startswith("-") else whole + rest


def _record(block: Block) -> tuple[str | None, str | None]:
    """(DSS file, pathname) of a gage: the default variant's, else the first variant's, else the block's own."""
    variants = block.blocks(VARIANT_KIND)
    chosen = next(
        (v for v in variants if (v.get("Default Variant") or "").casefold() == YES),
        variants[0] if variants else None,
    )
    if chosen is not None:
        return chosen.get("DSS File Name") or chosen.get("DSS File"), chosen.get(
            "DSS Pathname"
        ) or chosen.get("Pathname")
    return block.get("DSS File Name") or block.get("DSS File"), block.get("DSS Pathname") or block.get(
        "Pathname"
    )


def load(path: str | Path) -> list[HmsGage]:
    """Every gage of a ``.gage`` file, in file order; an empty list for a project that has none."""
    source = Path(path)
    gages = []
    for block in text.load(source).blocks(GAGE_KIND):
        file, pathname = _record(block)
        dss = None
        if file:
            name = Path(*PureWindowsPath(file).parts)
            dss = name if name.is_absolute() else source.parent / name
        gages.append(
            HmsGage(
                name=block.name,
                kind=block.get("Gage Type") or "",
                units=block.get("Units") or "",
                data_type=block.get("Data Type") or "",
                dss_file=dss,
                pathname=pathname or None,
                latitude=_degrees(block, "Latitude"),
                longitude=_degrees(block, "Longitude"),
            )
        )
    return gages


def beside(hms_project: str | Path | None, hms_basin: str | Path | None) -> Path | None:
    """The ``.gage`` file of a project named by its ``.hms`` file, or found beside its basin file; None when there is none."""
    if hms_project is not None:
        found = Path(hms_project).with_suffix(SUFFIX)
        return found if found.is_file() else None
    if hms_basin is None:
        return None
    files = sorted(Path(hms_basin).parent.glob(f"*{SUFFIX}"))
    return files[0] if files else None
