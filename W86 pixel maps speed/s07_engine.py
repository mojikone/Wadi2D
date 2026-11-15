"""An engine folder for a remake of somebody else's run: their checkout's package with this branch's product code.

    python s07_engine.py THEIR_CHECKOUT OUT_FOLDER

The grid and strip caches are keyed by a hash of the bytes of the code that builds them. A git worktree checks the
same commit out with other line endings than the checkout a run was made from, so a remake from the worktree misses
every cache and builds Block 2's tables and aligned mesh again, minutes of work for the same tables. Found on the
way, not changed: the key would have to hash the text, and that changes every key once.

Here: THEIR_CHECKOUT's ``wadi2d`` copied byte for byte, then the files this branch changes (none of them hashed)
laid over it. ``s02_remake.py --engine OUT_FOLDER`` then hits the run's own caches.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CHANGED = (
    "products/ground.py", "products/pixels.py", "products/step.py", "products/blocks.py", "products/strip_pixels.py",
    "products/strip_kernels.py", "products/cell_maps.py", "products/runner.py", "render/frame_pixels.py",
    "render/renderer.py", "io/geotiff.py", "run.py",
)  # fmt: skip


def main() -> None:
    theirs, out = Path(sys.argv[1]) / "wadi2d", Path(sys.argv[2])
    if (out / "wadi2d").exists():
        shutil.rmtree(out / "wadi2d")
    shutil.copytree(theirs, out / "wadi2d", ignore=shutil.ignore_patterns("__pycache__"))
    for name in CHANGED:
        shutil.copy2(REPO / "wadi2d" / name, out / "wadi2d" / name)
    sys.path.insert(0, str(REPO))
    from wadi2d.io.cache import STRIP_SOURCES, builder_identity, source_identity

    same = builder_identity(out / "wadi2d") == builder_identity(theirs)
    same_strip = source_identity(STRIP_SOURCES, out / "wadi2d") == source_identity(STRIP_SOURCES, theirs)
    print(f"{out}: grid cache key as theirs: {same}; strip cache key as theirs: {same_strip}")


if __name__ == "__main__":
    main()
