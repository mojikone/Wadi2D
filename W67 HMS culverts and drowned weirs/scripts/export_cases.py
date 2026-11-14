"""HMS's series of W67's cases to ``tests/data/hms_structures`` with W59's exporter; the basin file kept is the one HMS
itself re-saved, so every key in it is one HMS reads. HMS cuts a long re-saved name to ``..._sav.basin``.

Usage: ``python export_cases.py <folder under _work> [<case> ...]``; with no case, every W67 case.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "W59 HMS reservoir structures" / "scripts"))
sys.path.insert(0, str(HERE))
import export_hms  # noqa: E402
import hms_project as w59  # noqa: E402
import w67_cases  # noqa: E402


def main() -> None:
    folder = w67_cases.HERE / "_work" / sys.argv[1]
    cases = sys.argv[2:] or list(w67_cases.NEW_CASES)
    for case in cases:
        export_hms.export(case, folder)
        saved = sorted(folder.glob(f"{w59.file_stem(case)}_sav*.basin"))
        shutil.copy2(saved[0], export_hms.TARGET / f"{case}.basin")


if __name__ == "__main__":
    main()
