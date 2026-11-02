"""The variables of a NetCDF file, classic or NetCDF-4, read with no NetCDF library. Interface: :func:`open_netcdf`.

NetCDF-4 is HDF5 with dimension scales, so ``h5py`` reads it, and a second HDF5 library in the process is not safe on
Windows. The classic format goes through SciPy. Either way a variable comes out as its dimension names, its attributes
and its values with packing undone and no-data as NaN.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import h5py
import numpy as np
from scipy.io import netcdf_file

HDF5_MAGIC = b"\x89HDF"
CLASSIC_MAGIC = b"CDF"
MAGIC_BYTES = 8


@dataclass(frozen=True)
class Variable:
    """One variable; ``load`` reads its values when they are wanted."""

    name: str
    dims: tuple[str, ...]
    attrs: dict[str, Any]
    native: Any

    def load(self) -> np.ndarray:
        """The values as float64, unpacked, with fill values as NaN."""
        raw = np.asarray(self.native[()], dtype=np.float64)
        fills = [self.attrs[key] for key in ("_FillValue", "missing_value") if key in self.attrs]
        dead = np.zeros(raw.shape, bool)
        for fill in fills:
            dead |= raw == np.float64(np.asarray(fill).ravel()[0])
        unpacked = raw * float(self.attrs.get("scale_factor", 1.0)) + float(self.attrs.get("add_offset", 0.0))
        return np.where(dead, np.nan, unpacked)


def _text(value: Any) -> Any:
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace").rstrip("\x00")
    if isinstance(value, np.ndarray) and value.dtype.kind == "S":
        return _text(value.tobytes())
    if isinstance(value, np.bytes_):
        return _text(bytes(value))
    return value


def _hdf5_dims(dataset: h5py.Dataset) -> tuple[str, ...]:
    if h5py.h5ds.is_scale(dataset.id):
        return (dataset.name.rsplit("/", 1)[-1],)  # a coordinate variable is its own dimension
    names = []
    for n, dim in enumerate(dataset.dims):
        scale = dim[0].name.rsplit("/", 1)[-1] if len(dim) else f"dim{n}"
        names.append(scale)
    return tuple(names)


def _hdf5_variables(f: h5py.File) -> dict[str, Variable]:
    found: dict[str, Variable] = {}

    def visit(name: str, item: Any) -> None:
        if isinstance(item, h5py.Dataset) and item.dtype.kind in "fiu":
            short = name.rsplit("/", 1)[-1]
            attrs = {key: _text(item.attrs[key]) for key in item.attrs}
            found[short] = Variable(short, _hdf5_dims(item), attrs, item)

    f.visititems(visit)
    return found


def _classic_variables(f: netcdf_file) -> dict[str, Variable]:
    found = {}
    for name, item in f.variables.items():
        key = name.decode() if isinstance(name, bytes) else name
        attrs = {k: _text(v) for k, v in item._attributes.items()}
        dims = tuple(d.decode() if isinstance(d, bytes) else d for d in item.dimensions)
        found[key] = Variable(key, dims, attrs, item.data)
    return found


@contextmanager
def open_netcdf(path: Path) -> Iterator[dict[str, Variable]]:
    """The file's variables by short name, open while the block runs."""
    with path.open("rb") as stream:
        magic = stream.read(MAGIC_BYTES)
    if magic.startswith(HDF5_MAGIC):
        with h5py.File(path, "r") as f:
            yield _hdf5_variables(f)
    elif magic.startswith(CLASSIC_MAGIC):
        with netcdf_file(path, "r", mmap=False) as f:
            yield _classic_variables(f)
    else:
        raise ValueError(f"{path.name} is not a NetCDF file")
