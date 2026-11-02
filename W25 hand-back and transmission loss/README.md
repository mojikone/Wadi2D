# W25 hand-back and transmission loss

**Status: in progress on branch `feature/hand-back`, cut from `main` at `0c540e4` (D5 merged). Nothing below is a result yet.**

## [PRESERVE-CHECK]

**KEEP, untouched in behaviour, numbers to the last digit for any job with no hand-back and the loss off:**

- The solver kernels on both backends, CUDA and Numba, the stepper, the level stepper, the mesh. No kernel is edited.
- `hydrographs()`, `preflight()`, `Injection`, `boundary_set()`, `Balance.error`, `Balance.relative`, the `done` event and `results.h5` attributes of an old job.
- A lumped network run once before the 2D run when there is no hand-back; `_check_routes` for those jobs.
- Old checkpoints: format `2`, and their job hash, stay resumable.
- The dock. `plugin/` gains no code; the job fields pass through, `tests/plugin/schema_sample.json` is regenerated.

**CHANGE:**

- `hydrology.handbacks` (new job part): name, line, element. Inside the grid the line is an open sink line with its own tally per step. Volume crossing per lumped step, over the step, is the inflow of the element. The network below it reruns on the series so far during the run, and its outflow goes to the `Injection` where it re-enters, or leaves at the end of the network.
- `LumpedEngine.run` gains `external` and `cut`. Absent, the arithmetic is the old one.
- `Balance` gains fields with default zero. The `done` event and `results.h5` gain them only when the job uses them.
- A checkpoint gains a `handback` group when the job has one.
- `transmission` (new job part, off by default): a rate over the wetted plan of channel cells, limited by the water present and optionally by a total depth per cell, applied through the source refresh, on its own line in the balance.
- `boundary_notes` takes optional labels; `boundary_set` keeps its results and shares one helper with the per-line faces.
- The mesh refines along hand-back lines as along boundaries.

**FILES:**

- New: `wadi2d/hydrology/live_network.py`, `wadi2d/engine/handback.py`, `wadi2d/engine/transmission.py`, tests, this folder.
- Edited: `wadi2d/config/schema.py`, `wadi2d/run.py`, `wadi2d/forcing.py` (small), `wadi2d/engine/monitor.py`, `wadi2d/io/checkpoint.py`, `wadi2d/hydrology/network.py`, `wadi2d/mesh/build.py` (one line), `tests/plugin/schema_sample.json`.

The blast radius is several modules but no existing behaviour is removed, and the owner has said not to stop; the proof is `old_jobs_check.py` below.
