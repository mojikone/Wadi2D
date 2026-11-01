import sys
sys.path.insert(0, "scripts")
from analyze import show, line_stats
from common import OUT, SITES
from pathlib import Path
study = sys.argv[1]
for d in sorted((OUT / "runs" / study / "runs").iterdir()):
    if (d / "series").exists():
        show(d)
