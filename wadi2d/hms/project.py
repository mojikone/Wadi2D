"""The ``.hms`` project file: the index of a project.

Interface: :func:`load`, :class:`Project`. ``Project.folder`` is where the file was read from, so component
file names resolve to paths through :meth:`Project.path_of`.
"""

from __future__ import annotations

from pathlib import Path, PureWindowsPath

from pydantic import Field

from wadi2d.hms import text
from wadi2d.hms.text import Document
from wadi2d.hms.typed import BlockModel, HmsModel, RawBlock, UnknownEntry, hms

HEADER_KIND = "Project"
BASIN_KIND = "Basin"
PRECIPITATION_KIND = "Precipitation"
CONTROL_KIND = "Control"


class ProjectHeader(BlockModel):
    """The ``Project:`` block."""

    description: str | None = hms("Description")
    version: str | None = hms("Version")
    filepath_separator: str | None = hms("Filepath Separator")
    dss_file_name: str | None = hms("DSS File Name")
    time_zone_id: str | None = hms("Time Zone ID")


class Component(BlockModel):
    """A basin, met or control entry. HMS spells the key ``Filename`` or ``FileName`` by component."""

    filename: str | None = hms("Filename")
    filename_camel: str | None = hms("FileName")
    description: str | None = hms("Description")
    last_modified_date: str | None = hms("Last Modified Date")
    last_modified_time: str | None = hms("Last Modified Time")

    @property
    def file(self) -> str | None:
        """The component file name, whichever spelling the file used."""
        return self.filename or self.filename_camel


class Project(HmsModel):
    """A project: header, components by name, and anything else raw."""

    header: ProjectHeader
    folder: Path | None = None
    basins: dict[str, Component] = Field(default_factory=dict)
    mets: dict[str, Component] = Field(default_factory=dict)
    controls: dict[str, Component] = Field(default_factory=dict)
    other_blocks: list[RawBlock] = Field(default_factory=list)

    @property
    def name(self) -> str:
        """The project name."""
        return self.header.name

    def path_of(self, component: Component) -> Path:
        """Where a component file lies, relative to the project folder."""
        if component.file is None or self.folder is None:
            raise ValueError(f"cannot resolve the file of {component.label()}")
        return self.folder.joinpath(*PureWindowsPath(component.file).parts)

    def unknown_report(self) -> list[UnknownEntry]:
        """Everything in the file this reader did not recognise."""
        entries = list(self.header.unknown_report())
        for group in (self.basins, self.mets, self.controls):
            for component in group.values():
                entries += component.unknown_report()
        for block in self.other_blocks:
            entries.append(UnknownEntry(f"{block.kind} {block.name}".strip(), "block", block.kind))
        return entries


def from_document(document: Document, folder: Path | None = None) -> Project:
    """Type a tokenized ``.hms`` file."""
    block = document.block(HEADER_KIND)
    if block is None:
        raise ValueError(f"no '{HEADER_KIND}:' block: not a project file")
    groups: dict[str, dict[str, Component]] = {BASIN_KIND: {}, PRECIPITATION_KIND: {}, CONTROL_KIND: {}}
    other: list[RawBlock] = []
    for candidate in document.blocks():
        if candidate.kind in groups:
            groups[candidate.kind][candidate.name] = Component.from_block(candidate)
        elif candidate.kind != HEADER_KIND:
            other.append(RawBlock.from_block(candidate))
    return Project(
        header=ProjectHeader.from_block(block),
        folder=folder,
        basins=groups[BASIN_KIND],
        mets=groups[PRECIPITATION_KIND],
        controls=groups[CONTROL_KIND],
        other_blocks=other,
    )


def load(path: str | Path) -> Project:
    """Read a ``.hms`` file."""
    source = Path(path)
    return from_document(text.load(source), folder=source.parent)
