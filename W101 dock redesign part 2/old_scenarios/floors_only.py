"""Every run job of two batches compared with the three map floors of W101's threshold taken out of the second."""
import json
import sys
from pathlib import Path

FLOORS = ("depth_floor", "hazard_depth_floor", "cell_depth_floor")


def jobs(root: Path) -> dict:
    found = {}
    for path in sorted(root.rglob("job.json")):
        text = path.read_text(encoding="utf-8")
        for form in (str(root), str(root).replace("\\", "/")):
            text = text.replace(json.dumps(form)[1:-1], "<root>")
        found[str(path.relative_to(root))] = json.loads(text)
    return found


first, second = jobs(Path(sys.argv[1])), jobs(Path(sys.argv[2]))
same = left = 0
for name in sorted(set(first) & set(second)):
    if "wadi2d_preview_" in name:
        continue
    pixels = second[name].get("outputs", {}).get("pixels")
    if isinstance(pixels, dict):
        assert all(pixels.get(k) == 0.1 for k in FLOORS), name
        for k in FLOORS:
            pixels.pop(k, None)
        if not pixels:
            second[name]["outputs"].pop("pixels")
    if first[name] == second[name]:
        same += 1
    else:
        left += 1
        print("DIFFERENT", name)
print(f"{same} identical, {left} different, after the floors at 0.1")
