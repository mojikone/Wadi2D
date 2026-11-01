"""The ``.met`` file: the meteorologic model and its precipitation parameters.

Interface: :func:`load`, :func:`from_document`, :class:`Met`. The Hypothetical Storm (what Block 2 uses,
with a user pattern and a user depth-area table) is typed. Any other ``Precip Method Parameters`` block, the
classic Frequency Storm with its per-duration depths included, is kept raw in ``Met.parameters``.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import Field

from wadi2d.hms import text
from wadi2d.hms.text import Document
from wadi2d.hms.typed import BlockModel, HmsModel, RawBlock, UnknownEntry, hms, hms_list

HEADER_KIND = "Meteorology"
PARAMETERS_KIND = "Precip Method Parameters"
SUBBASIN_KIND = "Subbasin"
HYPOTHETICAL_STORM = "Hypothetical Storm"
FREQUENCY_STORM = "Frequency Storm"


class HypotheticalStorm(BlockModel):
    """``Precip Method Parameters: Hypothetical Storm``; ``storm_depth`` in the file's units."""

    last_modified_date: str | None = hms("Last Modified Date")
    last_modified_time: str | None = hms("Last Modified Time")
    precipitation_method: str | None = hms("Precipitation Method")
    storm_depth: float | None = hms("Storm Depth")
    precip_freq_grid_name: str | None = hms("Precip-Freq Grid Name")
    storm_type: str | None = hms("Storm Type")
    storm_duration: float | None = hms("Storm Duration")
    pattern_name: str | None = hms("Pattern Name")
    storm_area: float | None = hms("Storm Area")
    depth_area_reduction_method: str | None = hms("Depth-Area Reduction Method")
    reduction_table_name: str | None = hms("Reduction Table Name")
    uniform_depth: str | None = hms("Uniform Depth")


class SubbasinPrecip(BlockModel):
    """A per-subbasin block of the met model; ``depth`` is empty in Block 2 (``Uniform Depth: Yes``)."""

    last_modified_date: str | None = hms("Last Modified Date")
    last_modified_time: str | None = hms("Last Modified Time")
    depth: float | None = hms("Depth")


class MetHeader(BlockModel):
    """The ``Meteorology:`` block; ``use_basin_models`` is a repeated key."""

    last_modified_date: str | None = hms("Last Modified Date")
    last_modified_time: str | None = hms("Last Modified Time")
    description: str | None = hms("Description")
    version: str | None = hms("Version")
    unit_system: str | None = hms("Unit System")
    set_missing_data_to_default: str | None = hms("Set Missing Data to Default")
    precipitation_method: str | None = hms("Precipitation Method")
    air_temperature_method: str | None = hms("Air Temperature Method")
    atmospheric_pressure_method: str | None = hms("Atmospheric Pressure Method")
    dew_point_method: str | None = hms("Dew Point Method")
    wind_speed_method: str | None = hms("Wind Speed Method")
    shortwave_radiation_method: str | None = hms("Shortwave Radiation Method")
    longwave_radiation_method: str | None = hms("Longwave Radiation Method")
    snowmelt_method: str | None = hms("Snowmelt Method")
    evapotranspiration_method: str | None = hms("Evapotranspiration Method")
    use_basin_models: list[str] = hms_list("Use Basin Model")


class Met(HmsModel):
    """A meteorologic model: header, typed storm when there is one, every other block raw."""

    header: MetHeader
    storm: HypotheticalStorm | None = None
    subbasins: dict[str, SubbasinPrecip] = Field(default_factory=dict)
    parameters: list[RawBlock] = Field(default_factory=list)
    other_blocks: list[RawBlock] = Field(default_factory=list)

    @property
    def name(self) -> str:
        """The met model name."""
        return self.header.name

    @property
    def frequency_storm(self) -> RawBlock | None:
        """The raw Frequency Storm parameters, when the model uses that method."""
        return next((p for p in self.parameters if p.name == FREQUENCY_STORM), None)

    def unknown_report(self) -> list[UnknownEntry]:
        """Everything in the file this reader did not recognise."""
        entries = list(self.header.unknown_report())
        entries += self.storm.unknown_report() if self.storm else []
        for subbasin in self.subbasins.values():
            entries += subbasin.unknown_report()
        for block in self.other_blocks:
            entries.append(UnknownEntry(f"{block.kind} {block.name}".strip(), "block", block.kind))
        return entries


def from_document(document: Document) -> Met:
    """Type a tokenized ``.met`` file."""
    header: MetHeader | None = None
    storm: HypotheticalStorm | None = None
    subbasins: dict[str, SubbasinPrecip] = {}
    parameters: list[RawBlock] = []
    other: list[RawBlock] = []
    for block in document.blocks():
        if block.kind == HEADER_KIND and header is None:
            header = MetHeader.from_block(block)
        elif block.kind == PARAMETERS_KIND and block.name == HYPOTHETICAL_STORM:
            storm = HypotheticalStorm.from_block(block)
        elif block.kind == PARAMETERS_KIND:
            parameters.append(RawBlock.from_block(block))
        elif block.kind == SUBBASIN_KIND:
            subbasins[block.name] = SubbasinPrecip.from_block(block)
        else:
            other.append(RawBlock.from_block(block))
    if header is None:
        raise ValueError(f"no '{HEADER_KIND}:' block: not a met file")
    return Met(header=header, storm=storm, subbasins=subbasins, parameters=parameters, other_blocks=other)


def load(path: str | Path) -> Met:
    """Read a ``.met`` file."""
    return from_document(text.load(path))
