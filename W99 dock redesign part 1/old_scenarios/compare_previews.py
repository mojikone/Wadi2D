"""The terrain preview jobs of the profile editor scenario: each run names its scratch folder at random, so they are
compared as a set, the folder's name and the editor's draft file names taken out."""

import json
import re
import sys
from pathlib import Path


def previews(root: Path) -> list:
    found = sorted((root / "dock_profile_editor" / "runs").glob("wadi2d_preview_*/job.json"), key=lambda p: p.stat().st_mtime)
    out = []
    for path in found:
        text = path.read_text(encoding="utf-8")
        for form in (str(root), str(root).replace("\\", "/")):
            text = text.replace(json.dumps(form)[1:-1], "<root>")
        out.append(json.loads(re.sub(r"wadi2d_preview_[a-z0-9_]+", "wadi2d_preview_N", text)))
    return out


def differences(a, b, path=""):
    if isinstance(a, dict) and isinstance(b, dict):
        out = []
        for key in sorted(set(a) | set(b)):
            out += differences(a.get(key), b.get(key), f"{path}{key}.")
        return out
    if isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
        return [d for n, (x, y) in enumerate(zip(a, b)) for d in differences(x, y, f"{path}{n}.")]
    return [] if a == b else [f"{path.rstrip('.')}: {str(a)[:90]} != {str(b)[:90]}"]


first, second = previews(Path(sys.argv[1])), previews(Path(sys.argv[2]))
left = list(second)
matched = 0
for job in first:
    if job in left:
        left.remove(job)
        matched += 1
print(f"{len(first)} and {len(second)} preview jobs, {matched} with an identical partner")
for a, b in zip(first, second):
    diff = differences(a, b)
    if diff:
        print(diff[:4])
