"""The ``.control`` file: the simulation window. Interface: :func:`load`, :class:`Control`."""

from __future__ import annotations

from pathlib import Path

from wadi2d.hms import text
from wadi2d.hms.text import Document
from wadi2d.hms.typed import TimeWindowModel, hms

HEADER_KIND = "Control"


class Control(TimeWindowModel):
    """A control specification; ``time_interval`` in minutes, ``n_steps`` counts both ends of the window."""

    last_modified_date: str | None = hms("Last Modified Date")
    last_modified_time: str | None = hms("Last Modified Time")
    description: str | None = hms("Description")
    version: str | None = hms("Version")


def from_document(document: Document) -> Control:
    """Type a tokenized ``.control`` file."""
    block = document.block(HEADER_KIND)
    if block is None:
        raise ValueError(f"no '{HEADER_KIND}:' block: not a control file")
    return Control.from_block(block)


def load(path: str | Path) -> Control:
    """Read a ``.control`` file."""
    return from_document(text.load(path))
