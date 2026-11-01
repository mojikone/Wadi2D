"""progress.jsonl: one JSON object per event, flushed at once, because the plugin tails the file."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, TextIO


class Progress:
    """Writes ``{"ev": name, ...}`` lines; ``echo`` copies them to stdout for a caller reading the pipe."""

    def __init__(self, path: str | Path, echo: bool = False, append: bool = False) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._file: TextIO = self.path.open("a" if append else "w", encoding="utf-8")
        self.echo = echo

    def emit(self, ev: str, **fields: Any) -> None:
        line = json.dumps({"ev": ev, **fields}, ensure_ascii=False)
        self._file.write(line + "\n")
        self._file.flush()
        if self.echo:
            print(line, file=sys.stdout, flush=True)

    def close(self) -> None:
        self._file.close()

    def __enter__(self) -> Progress:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()
