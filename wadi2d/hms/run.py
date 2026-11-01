"""The ``.run`` file: simulation runs. Interface: :func:`load`, :class:`RunFile`, :class:`Run`."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field

from wadi2d.hms import text
from wadi2d.hms.text import Document
from wadi2d.hms.typed import BlockModel, HmsModel, RawBlock, UnknownEntry, hms

RUN_KIND = "Run"


class Run(BlockModel):
    """One simulation run: the basin, met and control it joins, and its output files."""

    description: str | None = hms("Description")
    default_description: str | None = hms("Default Description")
    log_file: str | None = hms("Log File")
    dss_file: str | None = hms("DSS File")
    is_save_spatial_results: str | None = hms("Is Save Spatial Results")
    last_modified_date: str | None = hms("Last Modified Date")
    last_modified_time: str | None = hms("Last Modified Time")
    last_execution_date: str | None = hms("Last Execution Date")
    last_execution_time: str | None = hms("Last Execution Time")
    basin: str | None = hms("Basin")
    precip: str | None = hms("Precip")
    control: str | None = hms("Control")
    time_series_output: str | None = hms("Time-Series Output")
    results_manager_start: str | None = hms("Time Series Results Manager Start")
    results_manager_end: str | None = hms("Time Series Results Manager End")


class RunFile(HmsModel):
    """The runs of a project, in file order."""

    runs: list[Run] = Field(default_factory=list)
    other_blocks: list[RawBlock] = Field(default_factory=list)

    def run(self, name: str) -> Run:
        """The run called ``name``."""
        for candidate in self.runs:
            if candidate.name == name:
                return candidate
        raise KeyError(name)

    def unknown_report(self) -> list[UnknownEntry]:
        """Everything in the file this reader did not recognise."""
        entries: list[UnknownEntry] = []
        for run in self.runs:
            entries += run.unknown_report()
        for block in self.other_blocks:
            entries.append(UnknownEntry(f"{block.kind} {block.name}".strip(), "block", block.kind))
        return entries


def from_document(document: Document) -> RunFile:
    """Type a tokenized ``.run`` file."""
    runs = [Run.from_block(b) for b in document.blocks(RUN_KIND)]
    other = [RawBlock.from_block(b) for b in document.blocks() if b.kind != RUN_KIND]
    return RunFile(runs=runs, other_blocks=other)


def load(path: str | Path) -> RunFile:
    """Read a ``.run`` file."""
    return from_document(text.load(path))
