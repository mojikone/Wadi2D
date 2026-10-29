# Toolchain check, 2026-10-29

Run: `.venv\Scripts\python.exe "W1 research and design note\benchmarks\toolchain_check.py"`; result in `benchmarks\toolchain_check_result.json`.

## What the machine has

| Item | Found | Consequence |
|---|---|---|
| GPU | NVIDIA GeForce RTX 5080, compute capability 12.0, 84 SMs, 16 GB, 64 MB L2, 48 KB shared per block | Blackwell: needs CUDA 12.8 or later for sm_120 |
| Driver | 581.42, CUDA 13.0 capable | Any CUDA 12.x or 13.x runtime works |
| CUDA toolkit (nvcc) | **absent** | No ahead-of-time compilation without an installer |
| MSVC (cl.exe, VS Build Tools) | **absent** | No host compiler for nvcc or pybind11 extensions |
| Python | 3.12.10 (also a 3.14 from uv, and ArcGIS Python 2.7) with numpy 2.4, scipy, numba 0.65, h5py, rasterio 1.5, shapely, pyproj, pydantic 2, pytest, hecdss 0.1.29 | The engine can be Python-orchestrated today; HEC's own DSS package is already installed |
| QGIS | 3.44.8 (LTR, Python 3.12) and 3.36.2, with GRASS and SAGA; the QGIS MCP plugin is installed | The plugin can be tested in QGIS from this session |
| HEC-HMS, HEC-RAS, HEC-DSSVue | installed | HMS runs for mode (a) comparisons; RAS example projects for the HDF reader |
| uv | 0.10.9 | Fast environments |
| Disk | D: 6.3 TB free | The 0.5 m terrain (27.8 GB) streams from its own folder; nothing is copied |

## What was done

A project environment `.venv` (system site packages visible, so his installed packages are reused) with `cupy-cuda12x 14.2.0`
and the NVIDIA pip wheels for the CUDA 12.9 runtime, NVRTC, cuBLAS, cuFFT, cuRAND, cuSOLVER, cuSPARSE and nvJitLink. No system
installer, no admin rights, nothing outside the repo folder. CuPy warns that `CUDA_PATH` is unset and then finds the wheels anyway;
the warning is harmless and can be silenced by setting `CUDA_PATH` to the `nvidia` folder in `site-packages`.

## Result

| Measure | Value |
|---|---|
| NVRTC compile of a two-kernel module for sm_120 | 0.15 s |
| Copy kernel, 2 x 256 MB | 827 GB/s (the card's spec is 960 GB/s; 86%) |
| 5-point float32 stencil, 16.8 M cells | 0.24 ms per call, 70 G cell updates/s (memory-bound ceiling) |
| Kernel launch overhead from Python | 7.4 µs |

Verdict: **PASS**. CUDA C++ kernels compiled at run time by NVRTC through CuPy run on this GPU with no toolkit installed.

## Stack decision that follows (recorded in the design note)

- Kernels in CUDA C++ source files (`.cu`), compiled at run time by NVRTC through CuPy's `RawModule`; the same sources compile
  with nvcc into a DLL later if the Python launch path ever limits speed. At 7 µs per launch and a few ms per step for a
  million-cell domain, Python orchestration costs under 1% [Certain, arithmetic from the numbers above].
- A CPU twin of every kernel in NumPy/Numba for machines without an NVIDIA GPU and for tests on CI.
- Float32 state with depth stored, not level (decision 3); FP64 never in the main loop.
- The engine is a Python process (`wadi2d` package in `.venv`); the QGIS plugin drives it as a subprocess through files and a pipe.
