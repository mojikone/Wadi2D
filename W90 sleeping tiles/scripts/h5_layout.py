"""Print the layout of an HDF5 file: names, shapes, types, attributes' names (read only)."""

import sys

import h5py


def show(name, obj):
    if isinstance(obj, h5py.Dataset):
        print(f"  {name}  {obj.shape}  {obj.dtype}  chunks={obj.chunks}  {obj.compression}")
    else:
        print(f"  {name}/  attrs={list(obj.attrs)[:12]}")


for path in sys.argv[1:]:
    with h5py.File(path, "r") as f:
        print(path, "attrs", {k: (str(v)[:80]) for k, v in f.attrs.items() if k != "config"})
        f.visititems(show)
