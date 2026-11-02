# W12 full extent rerun

**Status (2026-11-01): running.** W2's job on the merged engine, `2195de6`: same domain, terrain, storm, losses, Manning and outlets. W2 stays as it was and remains the record of the first run.

## What changed against W2

| Change | Expected effect |
|---|---|
| Dry-face fix in the momentum advection | Peaks in narrow diagonal channels fall slightly |
| Boundary fix | None: W2's two coast lines keep every cell |
| Map interval 900 s, not 21,600 s, and the pixel step in the run | Pixel depth, hazard, smooth polygons and the depth drawing come from the run itself |
| Fill to mean depth in the pixel step | H1 grows about 12 % against W2's issued maps, H3 to H6 hardly move |

Set before the run: mass error at most 1e-6, and each of the five dam peaks within 5 % of W2. A dam outside that is explained before anything is issued.

## Rerun

From the repository root with the project venv:

`python -m wadi2d.engine.cli run "W12 full extent rerun/jobs/full_30m_200yr.json" --out "W12 full extent rerun/runs/full_30m_200yr"`

`runs/`, `cache/` and `run.log` stay out of git.
