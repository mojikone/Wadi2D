# Wadi2D's own record: when the face reading came in, where it lives, what was measured

Source: the repository's git history and the W46 and W47 records, read on 2026-11-08 by the coordinating session.
Every number below is a run of the engine itself; none is from outside sources.

## When and where

- [Certain, git] The face section has been read at the upwind cell's level over the face's own invert since the first
  solver commit, `35ad921` of 2026-11-01 ("Solver core: staggered explicit scheme with sub-grid tables ..."):
  `from_left = uf > 0 or (uf == 0 and e_l >= e_r)`, `eup = e_lp if from_left else e_rp`, `face_lookup(eup, ...)`,
  where `e_l = d[left] - fl` is the left cell's level above its lowest pixel less the face invert above that pixel,
  i.e. the left cell's water level over the face invert. It was not added later.
- [Certain, git] The block-uniform quadtree (`655b875`, 2026-11-01) steps its faces, interface faces included, with
  the same `face_step`; the polygon kernel of the aligned strips (`d8a898e`, 2026-11-07) copied the same reading. So
  squares, the quadtree and the aligned strips all carry it.
- [Certain, design record] The scheme was chosen on 2026-11-01 (decision 19 of the project, the source review
  `N01_subgrid_scheme_decision.md`): level per cell, conservative momentum per face, the family of TUFLOW HPC, 3Di,
  SFINCS and HEC-RAS 2D. N01 knew the flat-level problem for thin sheet flow on slopes (3Di/Rana's documentation) and
  added a volume-over-length read of the face section for thin flow, faded out as the downstream depth approaches the
  upwind depth. Deep flow on a slope was not covered by that read and was not tested.
- [Certain, arithmetic] Why the original tests could not see it: W3's channel test (the gate for every scheme change)
  runs at a slope of 0.2 % with a normal depth of 0.778 m; half the bed's drop within a 20 m cell is 0.020 m, 2.6 % of
  the depth, inside the test's 3 % rule. Measured there: 0.986 of the normal depth. The scale grows with slope and
  cell size: at 1 % and 2.1 m deep, 5 % of the depth for 20 m cells, 9 % for 40 m, 14 % for 60 m; at 2 % and 2.5 m,
  8, 16 and 24 %. Measured errors are about half to two thirds of that scale.

## What was measured (W46, W47)

- Straight synthetic valley, 1 % slope, 40 m bed, 300 m3/s steady: 20 m squares and 20 m aligned cells store the same
  water to the digit, 2.5 % less than 5 m squares; 10 m 1.0 % less. The aligned cells on square cells are the lattice
  kernel to the last digit.
- A new test (W3's section at 1 %, 300 m3/s, 20 m): 0.966 of the normal depth on both kernels with the upwind read.
- Faydh 01's main stem, steady 300 m3/s, against 2 m squares converged to 0.2 % at 5 m: the 20 m aligned strip holds
  9.3 % less water (surface 0.20 m low), 10 m 4.2 % less; the 20 m squares +1.0 %, 10 m -1.1 %, 5 m -0.7 %.
- Faydh 01's main stem, a 300 m3/s flash flood with no rain: the strip under-attenuates by about 4 % over 14 km at
  20 and 10 m alike; the 20 m squares over-attenuate by 5 %, 10 m within 1 %.
- The Faydh race (rain-on-grid, dam axis, 16 h), against 5 m squares: 20 m squares -2.8 %, 20 m centre mesh
  (W46) +5.3 %, W45's ring corridors +0.9 % (+2.4 % against the 20 m squares), W45's ring generator with fixed 20 m
  thalweg cells +13 % (+15.8 % against the 20 m squares). The strip's excess sits on its own channel lines (+11 to
  14 % on the main stem's lines against the 20 m squares); tributary strips leave the main's lines untouched; rain on
  the strip only or on the hills only makes no difference.

## The two fixes tried (W47, branch `feature/face-level`, not merged)

- First form: the face section read at the mean of the two cells' levels where both are wet, upwind at a front;
  polygons also take the upwind cell's advection rate. Uniform flow fixed (W3 0.986 to 1.007, the new test 0.966 to
  1.010, straight-valley storage equal across cell sizes to 0.4 %, the strip's flood on Faydh's reach right to 0.6 %
  at 20 m), but 22 tests failed and the Faydh race did not close (all peaks down 1 to 2 %, the centre mesh still
  +9.2 % over the 20 m squares).
- Full form: upwind at crest faces, at faces against boundary cells (a per-cell flag) and at fronts (a fade of the
  carry as the downstream depth falls from 0.5 to 0.25 of the upwind one); the level carried by where the face
  stands between the centres (a half on the lattice, a third on a quad interface, each polygon face's own fraction).
  It mended the earthworks channels, quad planar flow, the mesh pixels and the dykes; 8 analytic cases still fail:

| Case | Upwind read (today) | Full-form carry | Limit |
|---|---|---|---|
| Ritter dam break, depth RMSE, m | 0.0085 | 0.0117 | 0.01 |
| MacDonald subcritical, m | 0.0100 | 0.0206 | 0.015 |
| MacDonald supercritical, m (discharge over the inlet's) | 0.0105 (1.000) | 0.0341 (0.986) | 0.012 |
| MacDonald jump, m (discharge) | 0.0324 (1.000) | 0.0581 (0.959) | 0.05 |
| 45-degree channel of squares, 3 cells, vertical walls, depth error % | 0.13 | 3.86 | 3 |
| W3's channel, 0 / 45 degrees, depth over normal, tiles | 0.986 / 1.025 | 1.007 / 1.069 | 3 % |

  The carry used is a central interpolation (the mean of the two levels weighted by the face's position), not an
  upwind-biased limited reconstruction and not an upwind-depth carry.

## Kernel or mesh generator

- [Certain] The depression of the stored water is the kernel's face reading: it appears on squares and aligned cells
  alike, identically, where neither has a staircase (the straight valley).
- [Certain] The part of the Faydh rain-fed excess that differs between generators (W45 corridors +2.4 %, W46 centres
  +8.3 %, W45 fixed 20 m thalweg cells +15.8 % against the 20 m squares, the same kernel) is not explained by the face
  reading: the first-form fix moved every peak by 1 to 2 % and left the spread.
