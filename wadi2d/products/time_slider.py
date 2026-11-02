"""The saved frames of a run as one CF-UGRID NetCDF file, which QGIS opens as a mesh layer with a time axis.

The mesh is the real cells, active ones only, so a coarse tile is coarse. A frame holds depth, speed and hazard per cell; a
cell below the depth floor is left out, so dry ground draws as nothing. These are cell values, of a cell's deepest point,
not the pixel maps: they show how the flood moves, and the rasters of ``pixels`` stay the numbers of record.

Written with h5py alone. A NetCDF-4 file is an HDF5 file with dimension scales, and a second HDF5 library in the process
beside h5py is not safe on Windows. Text attributes have to be fixed-length: QGIS's reader skips the mesh otherwise and
opens the file as a raster with no time.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

import h5py
import numpy as np

from wadi2d.config.schema import Pixels, RunConfig
from wadi2d.products.cell_grid import CELL_GRID_FILE, CELL_GRID_LAYER
from wadi2d.products.frames import frame_names, read_frames
from wadi2d.products.hazard import classify
from wadi2d.solver.layout import TILE

FRAMES_FILE = "frames.nc"
EPOCH = "seconds since 2000-01-01 00:00:00"
"""The file needs a date, and a run has none: the first of January 2000 stands for the start of the run."""
FILL = -9999.0
GZIP_LEVEL = 1
CHUNK_CELLS = 65536
TIME_CHUNK = 64
MESH = "Mesh2"
NODE_DIM, FACE_DIM, CORNER_DIM = "nMesh2_node", "nMesh2_face", "nMaxMesh2_face_nodes"
FACE_NODES = "Mesh2_face_nodes"
FIELDS = (("depth", "Depth, m", "m"), ("speed", "Speed, m/s", "m/s"), ("hazard", "Hazard class, 1 to 6 are H1 to H6", "1"))
SCALE_NOTE = "This is a netCDF dimension but not a netCDF variable."


def _text(value: str) -> np.bytes_:
    return np.bytes_(value)


@dataclass
class CellMesh:
    """Active cells: ``rows`` and ``columns`` on the raster of the saved frames, ``nodes`` and ``faces`` for the file."""

    rows: np.ndarray
    columns: np.ndarray
    x: np.ndarray
    y: np.ndarray
    faces: np.ndarray

    @property
    def count(self) -> int:
        return self.rows.size


def _mesh(rows: np.ndarray, columns: np.ndarray, sizes: np.ndarray, shape: tuple[int, int], x0: float, y0: float, dx: float) -> CellMesh:
    """Cells by north-west corner on the finest raster, with their sizes in raster cells; corners are shared by number."""
    across = shape[1] + 1
    south, east = rows + sizes, columns + sizes
    corners = np.stack(
        (south * across + columns, south * across + east, rows * across + east, rows * across + columns), axis=1
    ).astype(np.int64)  # counter-clockwise on the map, from the south-west
    keys, faces = np.unique(corners, return_inverse=True)
    node_rows, node_columns = np.divmod(keys, across)
    faces = faces.reshape(corners.shape).astype(np.int32)
    centre = sizes // 2
    return CellMesh(rows + centre, columns + centre, x0 + node_columns * dx, y0 - node_rows * dx, faces)


def uniform_mesh(mask: np.ndarray, x0: float, y0: float, dx: float) -> CellMesh:
    rows, columns = np.nonzero(mask)
    return _mesh(rows, columns, np.ones(rows.size, np.int64), mask.shape, x0, y0, dx)


def tile_mesh(mask: np.ndarray, tiles: list[tuple[int, int, int]], x0: float, y0: float, dx: float) -> CellMesh:
    """A quadtree from its tiles, (row, column, level) in tiles of the finest cells; ``mask`` says which cells are active."""
    rows, columns, sizes = [], [], []
    for tile_row, tile_column, level in tiles:
        size = 1 << level
        y, x = tile_row * TILE, tile_column * TILE
        own = mask[y : y + TILE * size : size, x : x + TILE * size : size]
        jj, ii = np.nonzero(own)
        rows.append(y + jj * size)
        columns.append(x + ii * size)
        sizes.append(np.full(jj.size, size, np.int64))
    return _mesh(np.concatenate(rows), np.concatenate(columns), np.concatenate(sizes), mask.shape, x0, y0, dx)


def read_tiles(run: Path) -> list[tuple[int, int, int]]:
    with sqlite3.connect(run / CELL_GRID_FILE) as db:
        return db.execute(f"SELECT tile_row, tile_column, level FROM {CELL_GRID_LAYER}").fetchall()


def run_mesh(run: Path, cfg: RunConfig) -> CellMesh:
    with h5py.File(run / "results.h5", "r") as f:
        mask = f["mask"][:]
        x0, y0, dx = (float(f.attrs[name]) for name in ("x0", "y0", "dx"))
    if cfg.mesh.enabled:
        return tile_mesh(mask, read_tiles(run), x0, y0, dx)
    return uniform_mesh(mask, x0, y0, dx)


def _dimension(f: h5py.File, name: str, size: int) -> h5py.Dataset:
    scale = f.create_dataset(name, (size,), dtype="f4")
    scale.make_scale(f"{SCALE_NOTE} {size}")
    return scale


def _topology(f: h5py.File) -> None:
    mesh = f.create_dataset(MESH, (), dtype="i4")
    mesh.attrs["cf_role"] = _text("mesh_topology")
    mesh.attrs["long_name"] = _text("Cells of the run")
    mesh.attrs["topology_dimension"] = np.int32(2)
    mesh.attrs["node_coordinates"] = _text("Mesh2_node_x Mesh2_node_y")
    mesh.attrs["face_node_connectivity"] = _text(FACE_NODES)
    mesh.attrs["face_dimension"] = _text(FACE_DIM)


def _create(path: Path, mesh: CellMesh, times: np.ndarray, crs: str) -> None:
    with h5py.File(path, "w", libver="earliest", track_order=True) as f:
        f.attrs["Conventions"] = _text("CF-1.8 UGRID-1.0")
        f.attrs["title"] = _text("Wadi2D saved frames")
        f.attrs["source"] = _text(crs)
        nodes = _dimension(f, NODE_DIM, mesh.x.size)
        faces = _dimension(f, FACE_DIM, mesh.count)
        corners = _dimension(f, CORNER_DIM, 4)
        time = f.create_dataset("time", data=times, dtype="f8", chunks=(TIME_CHUNK,), maxshape=(None,))
        time.make_scale("time")
        for key, value in (("units", EPOCH), ("standard_name", "time"), ("calendar", "standard"), ("axis", "T")):
            time.attrs[key] = _text(value)
        _topology(f)
        for name, data, standard in (
            ("Mesh2_node_x", mesh.x, "projection_x_coordinate"),
            ("Mesh2_node_y", mesh.y, "projection_y_coordinate"),
        ):
            variable = f.create_dataset(name, data=data, dtype="f8")
            variable.attrs["standard_name"] = _text(standard)
            variable.attrs["units"] = _text("m")
            variable.dims[0].attach_scale(nodes)
        link = f.create_dataset(FACE_NODES, data=mesh.faces, dtype="i4", fillvalue=-1)
        link.attrs["cf_role"] = _text("face_node_connectivity")
        link.attrs["start_index"] = np.int32(0)
        link.attrs["_FillValue"] = np.int32(-1)
        link.dims[0].attach_scale(faces)
        link.dims[1].attach_scale(corners)
        chunk = (1, min(mesh.count, CHUNK_CELLS))
        for name, title, units in FIELDS:
            variable = f.create_dataset(
                name, (times.size, mesh.count), dtype="f4", chunks=chunk, compression="gzip",
                compression_opts=GZIP_LEVEL, fillvalue=FILL,
            )  # fmt: skip
            variable.attrs["_FillValue"] = np.float32(FILL)
            variable.attrs["units"] = _text(units)
            variable.attrs["long_name"] = _text(title)
            variable.attrs["mesh"] = _text(MESH)
            variable.attrs["location"] = _text("face")
            variable.dims[0].attach_scale(time)
            variable.dims[1].attach_scale(faces)


def cell_frame(depth: np.ndarray, speed: np.ndarray, mesh: CellMesh, rule: Pixels) -> dict[str, np.ndarray]:
    """One frame on the cells: below the depth floor a cell is left out, in all three."""
    d = depth[mesh.rows, mesh.columns].astype(np.float32)
    s = speed[mesh.rows, mesh.columns].astype(np.float32)
    hazard = classify(d, s, d * s, rule).astype(np.float32)
    dry = d < rule.depth_floor
    return {name: np.where(dry, FILL, field) for name, field in (("depth", d), ("speed", s), ("hazard", hazard))}


def frame_seconds(names: list[str]) -> np.ndarray:
    return np.array([float(int(name[1:])) for name in names], np.float64)


def write_frames(run: Path) -> Path:
    """``frames.nc`` beside the run's results, through a temporary name; an existing file newer than the results stands."""
    path = run / FRAMES_FILE
    results = run / "results.h5"
    if path.is_file() and path.stat().st_mtime >= results.stat().st_mtime:
        return path
    cfg = RunConfig.model_validate_json((run / "config.resolved.json").read_text(encoding="utf-8"))
    names = frame_names(results)
    if len(names) < 2:
        raise ValueError(f"This run saved {len(names)} map(s), and a time slider needs two. Save maps more often, or run longer.")
    mesh = run_mesh(run, cfg)
    with h5py.File(results, "r") as f:
        crs = str(f.attrs.get("crs", ""))
    tmp = path.with_name(f"{path.stem}.tmp{path.suffix}")
    tmp.unlink(missing_ok=True)
    _create(tmp, mesh, frame_seconds(names), crs)
    rule = cfg.outputs.pixels
    with h5py.File(tmp, "r+", libver="earliest") as f:
        for index, (depth, _, speed) in enumerate(read_frames(results, names)):
            for name, values in cell_frame(depth, speed, mesh, rule).items():
                f[name][index, :] = values
    tmp.replace(path)
    return path
