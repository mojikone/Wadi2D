"""Terrain access and vector edits: the DEM never changes, objects act when the tables are built."""

from wadi2d.terrain.dem import GridWindow, RasterBed
from wadi2d.terrain.ground import Ground
from wadi2d.terrain.objects import TerrainEdits, apply_objects

__all__ = ["GridWindow", "Ground", "RasterBed", "TerrainEdits", "apply_objects"]
