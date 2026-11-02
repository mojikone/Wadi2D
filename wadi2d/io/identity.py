"""What identifies an input file for the caches: its content when that is cheap, its size and date otherwise.

A small file rewritten with the same bytes must not look new, and a small file edited within the same second must
not look old. A 27 GB raster cannot be hashed on every start, so it is known by size and date.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

BYTES_PER_MB = 1 << 20
SIDECARS = (".prj",)
"""Files beside a vector that change what it means."""


def file_identity(path: str | Path, limit_mb: float) -> dict[str, object]:
    """A JSON-ready identity of one file, with its sidecars."""
    source = Path(path)
    if source.is_dir():
        return {child.name: file_identity(child, limit_mb) for child in sorted(source.iterdir()) if child.is_file()}
    stat = source.stat()
    if stat.st_size > limit_mb * BYTES_PER_MB:
        identity: dict[str, object] = {"size": stat.st_size, "mtime_ns": stat.st_mtime_ns}
    else:
        identity = {"size": stat.st_size, "sha256": hashlib.sha256(source.read_bytes()).hexdigest()}
    for suffix in SIDECARS:
        extra = source.with_suffix(suffix)
        if extra != source and extra.is_file():
            identity[suffix] = hashlib.sha256(extra.read_bytes()).hexdigest()
    return identity
