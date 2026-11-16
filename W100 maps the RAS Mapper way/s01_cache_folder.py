"""A cache folder of this iteration that reads W79's caches without ever writing into them.

    python s01_cache_folder.py W79_CACHE OUT

Every file of W79's cache folder is hard-linked into OUT (the same volume: no copy), and every DEM chunk store
(a folder) is joined by a directory junction. A cache entry built again here (a key the current code moved) is saved
under a temporary name and renamed into OUT, which replaces the link in OUT and leaves W79's file as it was.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def main() -> None:
    theirs, out = Path(sys.argv[1]), Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    for item in theirs.iterdir():
        target = out / item.name
        if target.exists():
            continue
        if item.is_dir():
            subprocess.run(["cmd", "/c", "mklink", "/J", str(target), str(item)], check=True, capture_output=True)
        else:
            os.link(item, target)
    print(f"{out}: {sum(1 for _ in out.iterdir())} entries")


if __name__ == "__main__":
    main()
