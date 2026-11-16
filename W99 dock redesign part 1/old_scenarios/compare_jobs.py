"""Every job.json two batches of dock scenarios wrote, compared after taking each batch's own folder out of the paths."""

import json
import sys
from pathlib import Path


def jobs(root: Path) -> dict:
    found = {}
    for path in sorted(root.rglob("job.json")):
        text = path.read_text(encoding="utf-8")
        for form in (str(root), str(root).replace("\\", "/")):
            text = text.replace(json.dumps(form)[1:-1], "<root>")
        found[str(path.relative_to(root))] = json.loads(text)
    return found


def differences(a, b, path=""):
    if isinstance(a, dict) and isinstance(b, dict):
        out = []
        for key in sorted(set(a) | set(b)):
            if key not in a or key not in b:
                out.append(f"{path}{key} only in {'second' if key not in a else 'first'}")
            else:
                out += differences(a[key], b[key], f"{path}{key}.")
        return out
    if isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
        return [d for n, (x, y) in enumerate(zip(a, b)) for d in differences(x, y, f"{path}{n}.")]
    return [] if a == b else [f"{path.rstrip('.')}: {str(a)[:70]} != {str(b)[:70]}"]


first, second = jobs(Path(sys.argv[1])), jobs(Path(sys.argv[2]))
names = sorted(set(first) | set(second))
same = 0
for name in names:
    if name not in first or name not in second:
        print(f"ONLY IN {'second' if name not in first else 'first'}: {name}")
        continue
    diff = differences(first[name], second[name])
    if diff:
        print(f"DIFFERENT {name}: {diff[:5]}")
    else:
        same += 1
print(f"{same} of {len(names)} job.json files identical")
