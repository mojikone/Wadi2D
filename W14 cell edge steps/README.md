# W14 cell edge steps

**Status (2026-11-01): done, on `fix/cell-edge-steps`.** Why: at close zoom the depth maps showed cell-sized blocks in narrow wadis, the look he rejected as "pixel pixel". The smooth polygons fixed the wet edge and left the inside of the water. It reached the delivered depth drawing, whose blur is under a pixel, and it was as strong on a uniform 20 m grid as on a mesh.

Cause, measured on Bidah's peak map at 20 m: of the faces wet on both sides, 17,588 are linked and 91 are not, so the blocks are not links failing. A cell is filled to its own water by moving its whole surface by one number, and that number differs from the neighbour's. The mean step at a linked edge was 0.118 m, the 95th percentile 0.41 m, the largest 3.19 m.

Fix: the offset eases to the mean of the two cells in a band beside each joined edge, and the cell is refilled; three passes. Water stays exact, because the last fill sets it. Cells not joined keep their own surface, so nothing crosses a bank. `outputs.pixels.edge_passes` 0 gives the old surface.

Tried on the same map (`s01_edge_steps.py`):

| Method, after three passes | Own share of a cell's mean | Mean step, m | 95 %, m | Largest, m |
|---|---|---|---|---|
| None | | 0.118 | 0.412 | 3.19 |
| Offset at the corners (four passes) | | 0.085 | 0.308 | 1.49 |
| Quadratic spline | 0.44 | 0.061 | 0.232 | 1.61 |
| Band 0.5 | 0.56 | 0.043 | 0.176 | 1.21 |
| Band 0.35 | 0.68 | 0.026 | 0.108 | 0.99 |
| Band 0.25 | 0.77 | 0.017 | 0.065 | 0.62 |

Corners cannot hold a checkerboard of offsets at all, and a wide kernel hardly moves one: that is why the narrow band wins. 0.3 is taken between the last two by eye: 0.25 left thin streaks at a few bends. Cell water holds to 1e-6 m throughout.

Effect on the maps, Bidah to 18 h at 20 m, 0.5 m pixels, km2:

| | H1 | H2 | H3 | H4 | H5 | H6 |
|---|---|---|---|---|---|---|
| Before | 0.838 | 0.470 | 0.031 | 0.392 | 1.336 | 0.200 |
| After | 0.878 | 0.475 | 0.030 | 0.392 | 1.343 | 0.198 |

H3 to H6 move under 1 %, H2 1.1 %. H1 grows 4.7 %, because thin water now ends smoothly and not at a cell edge. The mesh gives the same picture at 10 to 40 m (`before_after.png`); on a mesh a coarse cell has no offset yet from its finer neighbour, so at an interface only the fine side eases.

What this is not: a change to the run. Cells, flows and hydrographs do not move, only how a cell's water is laid out over its pixels. The step costs up to four times the fills per map.
