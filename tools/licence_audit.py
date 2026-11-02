"""List the licence every runtime dependency declares, from the installed package metadata.

Run from the project venv: python tools/licence_audit.py. Output is what the packages say about themselves.
"""

from __future__ import annotations

from importlib import metadata

RUNTIME = (
    "numpy", "scipy", "h5py", "rasterio", "shapely", "pyproj", "pydantic", "pydantic-core", "numba", "llvmlite",
    "hecdss", "affine", "contourpy", "cupy-cuda12x", "fastrlock", "nvidia-cuda-runtime-cu12", "nvidia-cuda-nvrtc-cu12",
    "nvidia-cublas-cu12", "nvidia-cufft-cu12", "nvidia-curand-cu12", "nvidia-cusolver-cu12", "nvidia-cusparse-cu12",
    "nvidia-nvjitlink-cu12",
)  # fmt: skip


def declared(dist: metadata.Distribution) -> str:
    """The licence the package declares: the SPDX expression, the Licence field, or its classifiers."""
    meta = dist.metadata
    expression = meta.get("License-Expression")
    if expression:
        return expression
    field = (meta.get("License") or "").strip().splitlines()
    if field and len(field[0]) < 80:
        return field[0]
    classifiers = [c.split("::")[-1].strip() for c in meta.get_all("Classifier") or [] if c.startswith("License")]
    return "; ".join(classifiers) or "not stated"


def main() -> None:
    for name in RUNTIME:
        try:
            dist = metadata.distribution(name)
        except metadata.PackageNotFoundError:
            print(f"{name:30s} not installed")
            continue
        print(f"{name:30s} {dist.version:14s} {declared(dist)}")


if __name__ == "__main__":
    main()
