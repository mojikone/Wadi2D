"""The ``.nals`` file: depth-area analyses and their analysis points.

Interface: :func:`load`, :class:`NalsFile`, :class:`Analysis`. Each analysis carries its own window and GMT
offset, held verbatim; in Block 2 the offset follows the project time zone (-8 h), not the control file (+4
h).
"""

from __future__ import annotations

from pathlib import Path

from pydantic import Field

from wadi2d.hms import text
from wadi2d.hms.text import Document
from wadi2d.hms.typed import BlockModel, HmsModel, TimeWindowModel, UnknownEntry, hms, hms_list

HEADER_KIND = "Depth-Area Analysis Manager"
ANALYSIS_KIND = "Analysis"


class NalsHeader(BlockModel):
    """The manager block."""

    version: str | None = hms("Version")
    filepath_separator: str | None = hms("Filepath Separator")


class Analysis(TimeWindowModel):
    """One depth-area analysis; ``points`` keeps the file order of the repeated ``Analysis Point`` key."""

    description: str | None = hms("Description")
    dss_file: str | None = hms("DSS File")
    last_modified_date: str | None = hms("Last Modified Date")
    last_modified_time: str | None = hms("Last Modified Time")
    last_execution_date: str | None = hms("Last Execution Date")
    last_execution_time: str | None = hms("Last Execution Time")
    basin_model_name: str | None = hms("Basin Model Name")
    met_model_name: str | None = hms("Met Model Name")
    points: list[str] = hms_list("Analysis Point")
    time_series_output: str | None = hms("Time-Series Output")
    results_manager_start: str | None = hms("Time Series Results Manager Start")
    results_manager_end: str | None = hms("Time Series Results Manager End")


class NalsFile(HmsModel):
    """A depth-area analysis manager and its analyses, in file order."""

    header: NalsHeader
    analyses: list[Analysis] = Field(default_factory=list)

    def analysis(self, name: str) -> Analysis:
        """The analysis called ``name``."""
        for candidate in self.analyses:
            if candidate.name == name:
                return candidate
        raise KeyError(name)

    def unknown_report(self) -> list[UnknownEntry]:
        """Everything in the file this reader did not recognise."""
        entries = list(self.header.unknown_report())
        for analysis in self.analyses:
            entries += analysis.unknown_report()
        return entries


def from_document(document: Document) -> NalsFile:
    """Type a tokenized ``.nals`` file."""
    block = document.block(HEADER_KIND)
    if block is None:
        raise ValueError(f"no '{HEADER_KIND}:' block: not a depth-area analysis file")
    analyses = [Analysis.from_block(b) for b in document.blocks(ANALYSIS_KIND)]
    return NalsFile(header=NalsHeader.from_block(block), analyses=analyses)


def load(path: str | Path) -> NalsFile:
    """Read a ``.nals`` file."""
    return from_document(text.load(path))
