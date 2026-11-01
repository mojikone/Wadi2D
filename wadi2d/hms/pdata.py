"""The ``.pdata`` file: paired-data table metadata.

Interface: :func:`load`, :class:`PairedDataFile`, :class:`Table`. The file holds no ordinates, only where
they live: ``Table.pathname`` is the DSS pathname, read with :meth:`wadi2d.hms.dss.DssFile.read_paired`.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import Field

from wadi2d.hms import text
from wadi2d.hms.text import Document
from wadi2d.hms.typed import BlockModel, HmsModel, UnknownEntry, hms

HEADER_KIND = "Paired Data Manager"
TABLE_KIND = "Table"


class PairedDataHeader(BlockModel):
    """The manager block."""

    version: str | None = hms("Version")
    filepath_separator: str | None = hms("Filepath Separator")


class Table(BlockModel):
    """The metadata of one paired-data table."""

    table_type: str | None = hms("Table Type")
    description: str | None = hms("Description")
    last_modified_date: str | None = hms("Last Modified Date")
    last_modified_time: str | None = hms("Last Modified Time")
    x_units: str | None = hms("X-Units")
    y_units: str | None = hms("Y-Units")
    use_external_dss_file: str | None = hms("Use External DSS File")
    dss_file: str | None = hms("DSS File")
    pathname: str | None = hms("Pathname")
    interpolation: str | None = hms("Interpolation")


class PairedDataFile(HmsModel):
    """A paired-data manager and its tables, by name."""

    header: PairedDataHeader
    tables: dict[str, Table] = Field(default_factory=dict)

    def of_type(self, table_type: str) -> dict[str, Table]:
        """The tables of one ``Table Type``."""
        return {name: t for name, t in self.tables.items() if t.table_type == table_type}

    def unknown_report(self) -> list[UnknownEntry]:
        """Everything in the file this reader did not recognise."""
        entries = list(self.header.unknown_report())
        for table in self.tables.values():
            entries += table.unknown_report()
        return entries


def from_document(document: Document) -> PairedDataFile:
    """Type a tokenized ``.pdata`` file."""
    block = document.block(HEADER_KIND)
    if block is None:
        raise ValueError(f"no '{HEADER_KIND}:' block: not a paired-data file")
    tables = {b.name: Table.from_block(b) for b in document.blocks(TABLE_KIND)}
    return PairedDataFile(header=PairedDataHeader.from_block(block), tables=tables)


def load(path: str | Path) -> PairedDataFile:
    """Read a ``.pdata`` file."""
    return from_document(text.load(path))
