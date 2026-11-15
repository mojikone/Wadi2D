"""Two files of array hashes from time_tables.py --hash, compared. Args: a.json b.json. Exit 1 on any difference."""

import json
import sys
from pathlib import Path

a, b = (json.loads(Path(name).read_text(encoding="utf-8")) for name in sys.argv[1:3])
different = sorted(k for k in set(a) | set(b) if a.get(k) != b.get(k))
size = sum(int(__import__("numpy").prod(v[1])) * __import__("numpy").dtype(v[0]).itemsize for v in a.values())
print(
    f"{len(a)} and {len(b)} arrays, {size / 2**30:.2f} GB: "
    + ("identical" if not different else f"DIFFERENT {different}")
)
sys.exit(1 if different else 0)
