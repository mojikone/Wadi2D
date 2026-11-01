# SWE kernel micro-benchmark on the NVIDIA GeForce RTX 5080

Measured on 2026-10-29 with CuPy 14.2.0 (CUDA runtime 12090, driver 13000, NVRTC 12.9, compute capability 12.0, 84 SMs). All numbers below are measured [Certain]; the script is `swe_bench.py`, the kernels `swe_kernels.cu`, the raw output `results.json`. Throwaway benchmark: plausibility checks only (no NaN, mass conserved on the closed box, the three organisations agree to round-off), no validation.

## Results

ms/step is one full time step (ghost fill + CFL reduction + all stage kernels; RK2 = two flux evaluations). GCUPS = interior cells / step time (giga cell updates per second). Mass change is relative, over the whole run (20 warm-up + timed steps). 200 timed steps after 20 warm-up steps, CUDA-event timing.

### 2048 x 2048 wet, fast-math, adaptive dt (two-pass custom reduction)

| Integrator | Organisation | Domain | Flags | ms/step | GCUPS | dt end (s) | mass rel. change | wet fraction end | NaN |
|---|---|---|---|---|---|---|---|---|---|
| MH | fused | 2048x2048 wet | - | 0.365 | 11.49 | 0.423 | -2.4e-04 | 1.000 | no |
| MH | split | 2048x2048 wet | - | 1.572 | 2.67 | 0.423 | -1.7e-04 | 1.000 | no |
| MH | tiled | 2048x2048 wet | - | 0.334 | 12.55 | 0.423 | -2.4e-04 | 1.000 | no |
| RK2 | fused | 2048x2048 wet | - | 0.419 | 10.02 | 0.422 | -1.2e-04 | 1.000 | no |
| RK2 | split | 2048x2048 wet | - | 3.167 | 1.32 | 0.423 | -8.6e-05 | 1.000 | no |
| RK2 | tiled | 2048x2048 wet | - | 0.541 | 7.75 | 0.422 | -1.2e-04 | 1.000 | no |

### 2048 x 2048 wet, fast-math off

| Integrator | Organisation | Domain | Flags | ms/step | GCUPS | dt end (s) | mass rel. change | wet fraction end | NaN |
|---|---|---|---|---|---|---|---|---|---|
| MH | fused | 2048x2048 wet | no fast-math | 0.520 | 8.07 | 0.423 | -2.4e-04 | 1.000 | no |
| MH | tiled | 2048x2048 wet | no fast-math | 0.466 | 9.00 | 0.423 | -2.4e-04 | 1.000 | no |
| RK2 | fused | 2048x2048 wet | no fast-math | 0.523 | 8.03 | 0.422 | -1.2e-04 | 1.000 | no |
| RK2 | tiled | 2048x2048 wet | no fast-math | 0.650 | 6.45 | 0.422 | -1.2e-04 | 1.000 | no |

### 2048 x 2048 wet, cost of the CFL reduction (fused kernels)

| Integrator | Organisation | Domain | Flags | ms/step | GCUPS | dt end (s) | mass rel. change | wet fraction end | NaN |
|---|---|---|---|---|---|---|---|---|---|
| MH | fused | 2048x2048 wet | cfl=fixed | 0.333 | 12.60 | 0.381 | -1.5e-10 | 1.000 | no |
| MH | fused | 2048x2048 wet | cfl=cupy | 5.560 | 0.75 | 0.423 | -2.4e-04 | 1.000 | no |
| MH | fused | 2048x2048 wet | cfl=host | 0.418 | 10.04 | 0.423 | -1.7e-04 | 1.000 | no |
| RK2 | fused | 2048x2048 wet | cfl=fixed | 0.372 | 11.27 | 0.380 | +4.9e-10 | 1.000 | no |
| RK2 | fused | 2048x2048 wet | cfl=cupy | 5.888 | 0.71 | 0.422 | -1.2e-04 | 1.000 | no |
| RK2 | fused | 2048x2048 wet | cfl=host | 0.472 | 8.88 | 0.423 | -8.6e-05 | 1.000 | no |

### CUDA graph (one graph = two captured steps, launched 100 times)

| Integrator | Organisation | Domain | Flags | ms/step | GCUPS | dt end (s) | mass rel. change | wet fraction end | NaN |
|---|---|---|---|---|---|---|---|---|---|
| MH | fused | 2048x2048 wet | CUDA graph | 0.354 | 11.84 | 0.423 | +3.4e-10 | 1.000 | no |
| MH | tiled | 2048x2048 wet | CUDA graph | 0.325 | 12.90 | 0.423 | -1.2e-04 | 1.000 | no |
| RK2 | fused | 2048x2048 wet | CUDA graph | 0.401 | 10.45 | 0.422 | -1.2e-04 | 1.000 | no |
| RK2 | tiled | 2048x2048 wet | CUDA graph | 0.526 | 7.98 | 0.422 | -1.1e-04 | 1.000 | no |
| MH | fused | 1024x1024 wet | CUDA graph | 0.084 | 12.47 | 0.436 | -2.4e-04 | 1.000 | no |
| RK2 | fused | 1024x1024 wet | CUDA graph | 0.091 | 11.49 | 0.436 | +9.8e-09 | 1.000 | no |

### 2048 x 2048 all dry except a 300 x 300 wet patch (dry-cell cost and the active-cell early exit)

| Integrator | Organisation | Domain | Flags | ms/step | GCUPS | dt end (s) | mass rel. change | wet fraction end | NaN |
|---|---|---|---|---|---|---|---|---|---|
| MH | fused | 2048x2048 dry | - | 0.247 | 17.00 | 0.540 | -4.4e-10 | 0.031 | no |
| MH | split | 2048x2048 dry | - | 1.474 | 2.85 | 0.540 | +1.9e-09 | 0.031 | no |
| MH | tiled | 2048x2048 dry | - | 0.234 | 17.89 | 0.540 | -7.2e-10 | 0.031 | no |
| RK2 | fused | 2048x2048 dry | - | 0.362 | 11.60 | 0.540 | +1.3e-08 | 0.031 | no |
| RK2 | split | 2048x2048 dry | - | 2.998 | 1.40 | 0.540 | +2.3e-08 | 0.031 | no |
| RK2 | tiled | 2048x2048 dry | - | 0.446 | 9.41 | 0.540 | +1.1e-08 | 0.031 | no |
| MH | fused | 2048x2048 dry | early exit | 0.158 | 26.62 | 0.540 | -4.4e-10 | 0.031 | no |
| MH | tiled | 2048x2048 dry | early exit | 0.167 | 25.18 | 0.540 | -7.2e-10 | 0.031 | no |
| RK2 | fused | 2048x2048 dry | early exit | 0.318 | 13.19 | 0.540 | +1.3e-08 | 0.031 | no |
| RK2 | tiled | 2048x2048 dry | early exit | 0.379 | 11.06 | 0.540 | +1.1e-08 | 0.031 | no |

### Scaling of the fused and tiled kernels with domain size (wet, fast-math, adaptive dt)

| Integrator | Organisation | Domain | Flags | ms/step | GCUPS | dt end (s) | mass rel. change | wet fraction end | NaN |
|---|---|---|---|---|---|---|---|---|---|
| MH | fused | 2048x2048 wet | - | 0.365 | 11.49 | 0.423 | -2.4e-04 | 1.000 | no |
| MH | tiled | 2048x2048 wet | - | 0.334 | 12.55 | 0.423 | -2.4e-04 | 1.000 | no |
| RK2 | fused | 2048x2048 wet | - | 0.419 | 10.02 | 0.422 | -1.2e-04 | 1.000 | no |
| RK2 | tiled | 2048x2048 wet | - | 0.541 | 7.75 | 0.422 | -1.2e-04 | 1.000 | no |
| MH | fused | 1024x1024 wet | - | 0.094 | 11.11 | 0.436 | +2.9e-10 | 1.000 | no |
| MH | tiled | 1024x1024 wet | - | 0.091 | 11.58 | 0.436 | +2.8e-11 | 1.000 | no |
| RK2 | fused | 1024x1024 wet | - | 0.107 | 9.82 | 0.436 | +1.0e-08 | 1.000 | no |
| RK2 | tiled | 1024x1024 wet | - | 0.131 | 7.99 | 0.436 | +9.2e-09 | 1.000 | no |
| MH | fused | 4096x4096 wet | - | 1.606 | 10.44 | 0.420 | -1.2e-04 | 1.000 | no |
| MH | tiled | 4096x4096 wet | - | 1.370 | 12.25 | 0.420 | -1.2e-04 | 1.000 | no |
| RK2 | fused | 4096x4096 wet | - | 1.692 | 9.91 | 0.420 | -5.9e-05 | 1.000 | no |
| RK2 | tiled | 4096x4096 wet | - | 2.138 | 7.85 | 0.420 | -5.9e-05 | 1.000 | no |

### Pieces around the step kernels (2048 x 2048 wet, per step)

| Piece | ms |
|---|---|
| ghost_fill_ms | 0.0167 |
| cfl_custom_two_pass_ms | 0.0247 |
| cfl_cupy_reduction_ms | 2.8938 |
| cfl_custom_plus_host_readback_ms | 0.0716 |
| Python launch overhead of one tiny kernel (us) | 8.3 |

### Cross-check of the organisations (512 x 512 wet, 100 steps)

| Quantity | Value |
|---|---|
| mh: max|dh| split-fused | 2.623e-06 |
| mh: max|dh| tiled-fused | 2.861e-06 |
| rk2: max|dh| split-fused | 1.907e-06 |
| rk2: max|dh| tiled-fused | 1.907e-06 |
| max|dh| mh-rk2 (scheme difference, for scale) | 9.382e-03 |
| max depth (scale) | 3.509e+00 |

### Kernel resources (fast-math build)

| Kernel | Registers | Local (spill) bytes | Static shared bytes |
|---|---|---|---|
| ghost_x | 28 | 0 | 0 |
| ghost_y | 38 | 0 | 0 |
| cfl_partial | 19 | 0 | 1024 |
| cfl_final | 16 | 0 | 4096 |
| rk2_fused | 62 | 0 | 0 |
| mh_fused | 118 | 0 | 0 |
| recon_cells | 40 | 0 | 0 |
| flux_x | 33 | 0 | 0 |
| flux_y | 27 | 0 | 0 |
| update_cells | 40 | 0 | 0 |
| rk2_tiled | 56 | 0 | 41856 |
| mh_tiled | 78 | 0 | 46848 |

## Method

**State and grid.** Uniform grid, dx = dy = 10 m, float32, depth-based state (h, hu, hv) with the bed z as a fourth
array; the water level eta = h + z is formed in registers only (decision 3). Every array carries a 2-cell ghost frame;
the walls are reflective ghosts (normal discharge negated), refilled by a small kernel before every flux evaluation.

**Scheme.** Per face: MUSCL reconstruction with the minmod limiter of eta, h, hu and hv (z at the face = eta - h), first
order where the cell or a neighbour is dry; hydrostatic reconstruction at the face (Audusse et al. 2004); HLLC with the
two-rarefaction wave-speed estimates and the dry-bed cases; the Audusse face source terms plus the centred bed-slope
term (Audusse and Bristeau 2005), which makes still water on the bumpy sloping bed exact; point-implicit Manning
friction (n = 0.03, h^(4/3) via cbrtf) after the flux update; wet/dry threshold 1e-4 m; adaptive global time step
dt = 0.45 dx / max(max(|u|,|v|) + c) from a min-reduction over the wet cells, kept on the device (the kernels read dt
from a device pointer; no host synchronisation).

**Integrators.** MH = MUSCL-Hancock: the four reconstructed faces of a cell are advanced by dt/2 with the cell's own
flux divergence and bed-slope term, then one HLLC per face; one flux evaluation per step. RK2 = SSP-RK2 (Heun):
two flux evaluations per step, friction applied inside each stage.

**Organisations.** (1) *fused*: one kernel per flux evaluation computes the four face fluxes of its cell and updates
the cell; the neighbours' face states are recomputed (RK2: 9-cell cross stencil; MH: 13-cell stencil because the
neighbour's predictor needs its own neighbours), no intermediate arrays. (2) *split*: a reconstruction (+ predictor)
kernel writes the four face states of every cell (16 floats per cell), two flux kernels write the x and y face fluxes
and the face source terms (5 floats per face), an update kernel reads them back: the classic layout, every face
computed once, at the price of about 250 bytes per cell of global traffic instead of 28. (3) *tiled*: 32 x 32 cells per
block loaded with a 2-cell halo into shared memory (36 x 36 x 4 arrays = 20.7 KB); RK2: every face computed once into a
shared flux buffer (x pass, then y pass reusing the buffer, 21 KB); MH: the predictor is computed once per cell per pass
into shared memory (26 KB, faces stored without z, z recomputed) and the four face fluxes per owned cell. Block of
32 x 8 threads, four cells per thread; static shared memory stays under 48 KB.

**Domains.** Closed box of 2048 x 2048 cells (4.19 M) of 10 m, bed sloping 0.5 % in x plus smoothed random bumps of
+-0.5 m. Wet case: 1 m of water everywhere plus a Gaussian mound of 3 m (sigma 0.1 nx) at the centre, water starts at
rest and reaches its friction equilibrium (about 2 m/s) within the run. Dry case: the same bed dry except a 300 x 300
cell patch 2 m deep at the centre, which spreads during the run. 1024 x 1024 and 4096 x 4096 wet boxes for scaling.

**Early exit.** Fused kernels: a cell whose 5-cell cross (itself and the four neighbours) is dry copies its state and
returns (the fluxes on its four faces are exactly zero, also for the MH predictor, so this is consistent). Tiled
kernels: a block whose whole 36 x 36 tile is dry writes through and returns (`__syncthreads_or`). The split kernels have
no early exit.

**Timing.** 20 warm-up steps, then 200 timed steps between CUDA events on a non-blocking stream. The CUDA-graph
variant captures two consecutive steps (so the ping-pong buffers return to their roles) and launches the graph 100
times. The 'fixed' CFL mode uses 0.9 x the adaptive dt of the matching run; 'cupy' uses a `cupy.ReductionKernel`
instead of the two custom kernels; 'host' adds a `float(dt)` read-back every step (a full pipeline drain).


Total wall time of the run: 10.1 s.
