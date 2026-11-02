# W10 mesher

Status: finished 2026-11-01. Block-uniform quadtree, tile-level local time stepping, a mesher from DEM and streams, and a Mesh
section in the dock. All off by default; the uniform path gives the same numbers as `main` to the last digit.

**Decision, 2026-11-01: the mesher goes to `main`, off by default, and local stepping stays an option. The mesh's gain is accepted in place
of Stage A's speed gate; that gate's failure stays on record as a failure.** Stages B, C and D pass. Stage A passes on accuracy and fails on
speed: on a uniform grid, local time stepping saves no time. The gain is on the mesh, and only at scale: Block 2 at 10 m ran 2.9 x faster at
buffer 0.5. On a job of Bidah's size the mesh is slower than the uniform grid, because launches cost more than the kernels. The work stands on
`stage/d-plugin`, finished and not merged: the merge and the clean timing of the four mesh cases are the coordinator's.

## The gates

| Stage | Gate | Result | |
|---|---|---|---|
| A Local stepping, uniform grid | Tests with it off, numbers identical | `main` and this branch: same steps, same peaks to the last digit, Bidah and Block 2 | pass |
| | Stoker, Ritter, thin crest, still water | Within the uniform limits, both backends. `lts_levels = 0` is bit-identical to the uniform step | pass |
| | Bidah peak within 1 % | -0.03 % axis, -0.02 % s13 | pass |
| | Mass under 1e-6 | 2e-8 | pass |
| | Real speed gain, idle GPU | **None on a uniform grid.** Table below | **fail** |
| B Quadtree, synthetic ground | Still water | 7e-6 m/s on a rough bed at 1,500 m | pass |
| | Dam break, planar flow within 3 % | Dam break 1.4 to 1.6 % at most off the front, rms 0.1 %; a shock begun in coarse cells rms 2 %; planar 1.8 % at most | pass |
| | Mass under 1e-6 | 2e-10 | pass |
| C Mesher | Bidah within 5 %, 3 x fewer cells | 68,564 cells against 220,006, **3.21 x**; peaks -3.54 and -3.46 %, 1 min late | pass |
| D Plugin | End to end through the real dock | 42 of 42 in QGIS 3.44.8, throwaway profile; then a finished mesh run, its pixel maps and Make map, 37 of 37 | pass |
| Fast path | Not over 3 % slower | Block 2, idle GPU: 162.94 s against 161.98 s, +0.6 % | pass |

1,098 tests pass on the merged code. Ruff is clean on everything added here; `tests/conftest.py` keeps its three old notes.

## Speed, the numbers to read

Uniform grid, Block 2 at 20 m, 2,025,556 cells, first 14 h through the peak. **Clean**: only our own memory on the card.

| Run | Loop, s | Worst peak of 16 lines | Tile-steps |
|---|---|---|---|
| `main` | 161.98 | | |
| This branch, uniform | 162.94 | identical | |
| Local stepping, buffer 1.0 (default) | 190.73 | 0.42 % | |
| Local stepping, buffer 0.5 | 160.25 | 0.26 % | about half |

Tile-steps halve and the wall clock does not move: each substep runs about twice the kernels of a uniform step, and all that is saved
goes to launches, lists and copies. Bidah (262 tiles): 35.4 s uniform, 55.8 s local stepping, other jobs on the card part of the time.

Mesh, Block 2, 14 h, `grid.dx` 10 m, coarse 40 m. Peaks against uniform 10 m at the five dams.

| Run | Cells | Steps | Tile-steps, M | Loop, s | Peaks | GPU |
|---|---|---|---|---|---|---|
| Uniform 10 m | 8,104,054 | 149,582 | | 1,538 | | others on it at the start |
| Mesh, one step | 4,718,245 | 174,449 | 841 | 1,165 | -0.2 to -2.7 % | shared with the tests and QGIS: **not clean** |
| Mesh, local stepping, buffer 1.0 | 4,718,245 | 198,121 | 498 | 946 | -0.2 to -2.5 % | others on it: **not clean** |
| Mesh, local stepping, buffer 0.5 | 4,718,245 | 171,161 | 343 | **523** | -0.2 to -2.4 % | idle at the start, 30 % mean use |

Tile-steps are the same whatever else the card is doing: on the mesh, local stepping cuts them to 59 % at buffer 1.0 and 41 % at 0.5. Only the
523 s is near clean, so 2.9 x stands against 1,538 s, which ran with others on the card, and may flatter a little. The three mesh runs ran before
the merge of `main`, on the frozen code of `ab7f98c`. A clean run of all four, on one idle card, is still wanted.

Bidah on the mesh: 88 to 269 s against 36 s uniform, not clean. A mesh substep runs about 25 kernels over three cell sizes and two
axes, against 9 on the uniform path, at about 8 microseconds each, so at 90 tiles the launches swamp the kernels. **Below about
1 M cells the mesh saves memory, not time.** [Likely; the crossover itself was not measured.]

Buffer 0.5 is an option, not the default: it misses Stage B's 3 % at a front running onto dry coarse cells (3.7 %, against 1.3 %).

## What was built

- **Local stepping** (`solver/levels.py`, `solver/level_stepper.py`, `cpu/levels.py`, `gpu/levels.py`, `kernels/levels.cu`). A level is a
  list of tiles and a dt run through the kernels as they are, which is why the uniform path cannot move. Coarse tiles go first; the
  edge between levels steps at the finer rate; the fine tile reads the coarse level interpolated in time; what the fine steps carried
  beyond the coarse estimate goes into the coarse cell's residual, so volume is exact. Neighbours differ by one level.
- **Quadtree** (`grid/quad.py`, `tables/quad.py`, `kernels/quad.cu`, `cpu/quad.py`). 32 x 32 cells of one size per tile, 2:1, no lists
  inside a tile. A side of a fine tile that faces a coarser one is 32 fine faces with their own ground, through the same `face_step`
  with the true distance between centres. The coarse face is closed and takes their sum, so fine fluxes add up to it exactly.
- **Mesher** (`mesh/`). Streams through WhiteboxTools as in `create_streams.py`: breach, D8, accumulate. A stream counts only where it lies
  below the ground around it, which reads zero on any plane, so a stream on an open plain forces nothing. Wadis over 10 km2 stay at
  the finest cell, over 1 km2 one step coarser. Barriers, shaped crests, boundaries and design lines stay fine. Slope breaks are in
  the code and off by default: on Bidah's hills they would refine nearly everything.
- **Plugin**: section 2, Mesh. Cell sizes, zones, a preview raster of tile sizes (`preview_on_map.png`), local stepping.
- **`wadi2d mesh JOB --out DIR`**: the preview from the command line.

## With the terrain tools

`main` 020ea37 is merged. Tested on the new grids:

- **A negative `cw` reads the energy head.** Both kernels already did, because an interface face runs the same `face_step`. The table
  builder did not: it kept only positive coefficients, so a shaped crest would have become a plain one in silence. Fixed and tested.
- **Embankment and channel_dyke stay watertight across cell sizes**: dry past the crest at 0.3 m below it, both backends; overtopped at
  0.4 m, within 8 % of the uniform grid; dykes hold a channel across cell sizes, with the plain dry on both sides.
- **A crest, wall, boundary or design line that reaches a coarse tile is refused**, exit 2, in plain words. It can only happen with
  `mesh.refine_lines` off or on a tile-edge face; there is no way to run it wrong.
- **Cut and fill equal the uniform grid's.** The survey walked one finest tile per tile; it now walks every square of a coarse one.

## Found on the way, for the owner

1. **The uniform engine depends on its step on thin rain sheets.** Valley job, 900 s: outflow 142.8 m3 at a step of about 1.2 s, 125.7 m3 at
   0.05 s, 14 %. Not caused by this work. It bears on every rain-on-grid peak and was not known. [Certain on that job.]
2. **CuPy hands one loaded module to identical source**, constants included. Two live models with different numerics in one process
   overwrite each other's constants on the GPU. Nothing does that today; the mesh gets round it with a tag per cell size.
3. **Coarse edge cells add 0.48 % to Bidah's rain** (3,593,302 against 3,576,149 m3): a coarse cell counts when half of it is inside.
4. **On a slope a coarse cell reads shallower** without sheet flow: the same -10 % as a uniform 20 m grid, to four figures. With production
   numerics 1.8 %. The interface adds nothing of its own.

5. **Two meshes built at once can trip WhiteboxTools.** It keeps one settings file, and one run in a full suite exited 0 with no output while a
   dock check built its own mesh. The analysis now tries three times, then says so. The cause is [Likely]; the missing file is [Certain].
6. **A resumed run does not end exactly where an unbroken one does**, on the uniform grid too: rain windows restart at the stop, and a peak at the
   end of the storm moved 0.9 % uniform, up to 1.4 % on the mesh. Not caused by this work; the windows could be kept on their old times.

Mutation checks, recorded because a first clean pass proved nothing: 16 faults put into the edge and interface code, one at a time. 14 are
caught, four of them only after new tests were written for them. Two are not: coarse-rate edge faces, and halos frozen in time, read within
noise on the smooth wave. Their job is at fast fronts, and no test shows that yet.

## Pixel maps on a mesh

The step runs once per cell size, each on a lattice of that size, so the uniform code does the work. Around each set of cells sits a ring of
ghost cells for what lies beside it: a finer neighbour gives its mean, a coarser one its sloped surface read at the ghost's centre, which is why
coarse sizes go first. Sills come from the fine faces, and each coarse cell fills to its own volume.

A planar sheet down a 1 % slope through both interfaces, 0.34 m deep: **largest step 0.0064 m, at most 0.012 m from the uniform run**
(`tests/products/test_mesh_pixels.py`). CPU and GPU give the same hazard and within 1 mm of the same depth. The speed saved in frames used to read
raster neighbours, which inside a coarse cell are the same cell; it now reads the cell's own faces.

Bidah at 2 m pixels, 3 h after a 30 mm storm, through the dock: 68,564 cells, three sizes. Wet 1.87 km2 against 1.94 on uniform 10 m; of the wet
pixels 85 % are wet on both, there the median difference is 2 mm and 95 % lie within 0.175 m. Small ponds and side wadis under 1 km2 sit in coarse
cells and read shallower: that is the mesh's resolution, not the step (`pixels_mesh_vs_uniform.png`).

At the DEM's own 0.5 m (`pixels_05m.py`), Bidah through the peak, 10 to 40 m cells, 28 maps: 248 s in all, 79 s of it the loop, mass -2e-8, 10,700 x 16,720
pixels. H1 to H6 0.90, 0.45, 0.05, 0.35, 1.28, 0.20 km2. Two things it showed, neither from the mesh: a straight 0.75 m step in the ground at
about 438,890 / 2,727,425 that reads as a seam in the DEM; and cell-sized blocks in narrow wadis, as strong on uniform 20 m (445 jumps over 0.5 m in one
crop, 366 on the mesh). The blocks reach the depth drawing; the fix is its own change.

## Tested on a mesh, against an answer known without it

All in `tests/engine/test_mesh_paths.py`, cells of both sizes.

| Path | Answer it is held to | Result |
|---|---|---|
| Depth grid, CN raster | Volume from each cell's own depth or CN | within 0.2 %; **fixed:** a coarse cell over a raster's edge read off it, so a raster ending at the DEM was refused |
| Depth grid that stops short | Refused in plain words | refused, exit 2 |
| Manning raster | The same value as a number | 0.1 % |
| Pool set by level | Ground's own volume | 0.1 % |
| Lumped subbasin, table, into fine and coarse cells | Rain masked, hydrograph enters once | rain within 0.2 %, inflow exact |
| Lumped subbasin from an HMS basin | Its volume enters | 3 % |
| 2D subbasin with its own CN | Volume | 0.2 % |
| Depth-area study, composite maps | The uniform grid | design peak within 5 %, median depth 2 cm |
| Stop and resume, CPU and GPU | An unbroken run | peak 1.4 % off; a uniform run moves 0.9 %, because rain windows restart at the stop |
| `--dry-run` | The mesh's own cells, memory, a word on the time | **fixed:** it reported the uniform grid. Its time is rough, and says so |
| Spillway, burn line, normal-depth edge | Rating; uniform | 3 %, 0.1 %, 5 % |
| Gauge in a coarse cell | Uniform water level | 3 cm on a 1 % slope |
| Pixel depth against an embankment | Crest and the far side dry | dry |

The dock offers no ARF study and no resume, so those two reach a mesh from the command line. Nothing had to be refused beyond what already was.

## Not tested

Levels at a real front on a mesh at full scale; an observed event; another PC; the CPU backend through the dock. A mesh rebuilds its tables each
run: no cache. Slope breaks are unit-tested only. A mesh ran no timing in this last pass: the GPU was held by the full-extent rerun, and the clean
timing of the four mesh cases is the coordinator's.

## Files

`bidah.py` one run with changed settings. `speed.py`, `speed_mesh.py` timing with GPU use sampled; results in `speed_*.jsonl`.
`plug_mesh.py`, `plug_maps.py`, `run_plug.ps1` the dock checks; `log_plugin_run.txt`, `log_plugin_maps.txt` their records. `runs/` is not in git.
