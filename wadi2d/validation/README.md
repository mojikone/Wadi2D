# Analytic validation cases

Exact solutions a solver test runs against: rung one of the validation ladder (decision 12 in the project
`CLAUDE.md`). This package holds no solver. `tests/validation/` checks only that the solutions are right:
differenced fields, jump conditions, closed forms.

## Using a case

```python
from wadi2d.validation import UniformGrid, compare
from wadi2d.validation.cases.thacker import build_planar

case = build_planar(UniformGrid.square(4.0, 200))   # origin, dx, nx, ny; arrays are (ny, nx)
z, start = case.bed(), case.initial()               # also case.boundaries, case.manning_n, case.t_end
state = my_solver(z, start, case.boundaries, case.t_end)
report = compare(state, case, case.t_end)           # report.passed, report.failures, report.depth_rmse ...
```

Closed forms beyond the fields stay on `case.solution` (`period`, `shoreline_radius(t)`, `shock(t)`,
`normal_depth`, `q`). Beds are defined at every point, so `lake_at_rest.sample_bed(case.solution.bed, grid, k)`
gives `k x k` points per cell for table building, on any case.

## The cases

The limits are RMSE over wet cells unless stated, for the resolution given. **They are engineering judgement
for a good second-order scheme, not measurements: no solver has run them yet.** Tighten them from the first
convergence study. `G` is 9.80665 here, so numbers differ in the fourth figure from sources using 9.81.

| Case | Builder | Parameters (default) | Source | Limit for a good second-order solver |
|---|---|---|---|---|
| Lake, smooth bump | `lake_at_rest.build_bump` | eta 1, bump 0.5, width 10% of domain | Audusse et al. 2004; SWASHES lake at rest | Round-off: `h` and `q` L-inf 1e-5, F 0.999, volume 1e-6 |
| Lake, rough bed | `lake_at_rest.build_rough` | RMS 0.5, correlation length 5 dx, seed 0, eta 0 | As above; bed by random Fourier features | As above |
| Lake, steep slope | `lake_at_rest.build_slope` | slope 0.1, shoreline at centre | As above | As above |
| Thacker planar | `thacker.build_planar` | a 1, h0 0.1, eta 0.5, 3 periods; 4 m domain, 200 cells | Thacker 1981; SWASHES | `h` 2% of h0, `q` 5% of h0 sqrt(g h0), F 0.95, volume 1e-4 |
| Thacker curved | `thacker.build_curved` | a 1, h0 0.1, r0 0.8, 3 periods; 4 m domain, 200 cells | Thacker 1981; SWASHES | As above |
| Dam break, wet bed | `dam_break.build_stoker` | hl 2, hr 0.5, dam mid-domain, axis x or y; 200+ cells | Stoker 1957; SWASHES | `h` 1% of hl, `q` 3% of hl sqrt(g hl), F 0.95, volume 1e-4 |
| Dam break, dry bed | `dam_break.build_ritter` | hl 2, dam mid-domain, axis x or y; 200+ cells | Ritter 1892; SWASHES | `h` 2% of hl, otherwise as above |
| MacDonald subcritical | `macdonald.build_macdonald(grid, Variant.SUBCRITICAL)` | 1000 m, q 2, n 0.033; dx 5 m | MacDonald et al. 1997; SWASHES long channel | `h` 0.2% of hc, `q` 0.5% |
| MacDonald supercritical | `Variant.SUPERCRITICAL` | As above | As above | As above |
| MacDonald with jump | `Variant.JUMP` | As above; h ahead of jump 0.7 hc at 0.4 L, 0.52 to 1.02 m | Same method; profile built here | `h` 2% of hc, `q` 0.5% |
| Rotated channel | `channel_steady.build_channel`, `build_all_angles` | theta 0, 15, 30, 45; Q 30, S 0.002, n 0.03; rectangular b 20, trapezoidal b 10 m 2, bank 3; 400 m domain | Manning, Chow 1959 | `h` and surface 2% of yn, `q` 5% of mean q; the same Q at every angle |
| Weir, free | `weir.build_weir` | H 1, P 2, crest one cell | Henderson 1966; Chow 1959 | `h` 5% of H, `q` 5% |
| Weir, drowned | `weir.build_weir(grid, tailwater=...)` | As above, tailwater 2.67 to 3 m | See below | `h` 10% of H, `q` 10%, against the chosen reference |

## Two references that are not unique

**Rotated channel.** Manning with `R = A / P` and the strip law, friction on each strip of bed, give different
normal depths: 1.044 against 1.004 m (rectangular, 3.9%) and 1.441 against 1.361 m (trapezoidal, 5.6%). That
gap exceeds the 2% limit. A depth-averaged solver on a grid that resolves the section converges to the strip
law, so pass `conveyance=Conveyance.STRIP` for such a run. A sub-grid run with a conveyance table built on
`A / P` belongs with the default.

The field is sampled at cell centres, so on a coarse sub-grid run a centre may sit on dry bank. Give the
modelled water surface to `compare(..., surface=eta)`, which compares it with `solution.water_surface`.

**Drowned weir.** At H = 1, P = 2:

| Tailwater, m | Textbook energy, `q` | Borda energy-momentum, `q` | Villemonte, `q` |
|---|---|---|---|
| 2.85 | 1.46 | 1.66 | 0.95 |
| 2.90 | 1.26 | 1.52 | 0.81 |
| 2.95 | 0.94 | 1.20 | 0.63 |

The free law gives 1.70. The Borda form is the closure of the shallow-water equations on a step and stays
modular to a crest depth of 0.79 H, against the textbook 2/3. Villemonte is empirical, from sharp-crested
weirs. The 10% limit means nothing until the design note says which of these the crest-aware face must meet.

## Notes

- `case.initial()` is the exact state at t = 0, so steady cases start on their answer and test that a solver
  stays there. A cold start from another state is the test's choice.
- Channel plains fall along the axis at the channel slope: flat across, not level, because uniform flow needs
  the slope.
- The volume check in `compare` is against the initial volume when all sides are closed, and against the exact
  volume otherwise. A sampled exact field misses the volume limit at a moving shoreline, because point samples
  are not discretely conservative; a conservative solver's state does not have that problem.
- The jump profile is steep ahead and mild behind, with depth falling towards the jump, so the jump is stable
  against a shift either way (`tests/validation/test_macdonald.py`).
- The SWASHES supercritical profile reaches Fr = 1.00004 at the inlet. That is the published case; expect it
  to stress a supercritical inflow boundary.
