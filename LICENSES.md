# Licence audit

Wadi2D is released under GPL-3.0-or-later (`LICENSE`). This page lists what each runtime dependency declares about itself, read from the
installed package metadata by `tools/licence_audit.py` on 2026-11-01. Rerun it when a dependency changes. It records what the packages state; it
is not legal advice.

| Package | Version | Declared licence | With GPL-3.0 |
|---|---|---|---|
| numpy | 2.4.6 | BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0 | compatible |
| scipy | 1.18.0 | BSD-3-Clause | compatible |
| h5py | 3.16.0 | BSD-3-Clause | compatible |
| rasterio | 1.5.0 | BSD-3-Clause | compatible |
| shapely | 2.1.2 | BSD-3-Clause | compatible |
| pyproj | 3.7.2 | MIT | compatible |
| pydantic, pydantic-core | 2.13.4, 2.46.4 | MIT | compatible |
| numba | 0.65.1 | BSD | compatible |
| llvmlite | 0.47.0 | BSD-2-Clause AND Apache-2.0 WITH LLVM-exception | compatible |
| hecdss | 0.1.29 | MIT | compatible |
| affine | 2.4.0 | BSD | compatible |
| cupy-cuda12x | 14.2.0 | MIT | compatible |
| **nvidia-cuda-runtime, nvrtc, cublas, cufft, curand, cusolver, cusparse, nvjitlink (cu12)** | 12.9 | **NVIDIA proprietary** | **see below** |
| QGIS (plugin host) | 3.34+ | GPL-2.0-or-later | compatible; the plugin is GPL-3.0-or-later |

## The NVIDIA libraries

The GPU path loads NVIDIA's proprietary runtime and compiler libraries. They are never part of this repository and never bundled: a user installs
them from PyPI with the `gpu` extra. The engine also runs without them, on the CPU.

Whether a GPL program may be distributed while it loads a proprietary library depends on that library counting as a system library, and that is
not settled here. The usual remedy is an additional permission under GPL-3.0 section 7, granted by the copyright holder, allowing the program to be
combined with the NVIDIA CUDA libraries. **That is a decision for the owner of the code, and it is not taken yet.** It costs nothing to add while
he is the only contributor; after outside contributions it would need their agreement.

The HEC-RAS and HEC-HMS programs are not dependencies: Wadi2D reads their files. The `hecdss` wheel bundles HEC's DSS library under its stated licence.
