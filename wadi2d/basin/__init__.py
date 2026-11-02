"""The basin model generated from a DEM: subbasins, reaches, junctions and reservoirs as data the user can read and edit.

``wadi2d basin`` writes ``basin.json`` (the contract, see :mod:`wadi2d.basin.contract`) and ``basin.gpkg`` (the map).
:func:`load_network` turns the file into the lumped engine's objects, :func:`junction_routes` says how each junction drains.
"""

from __future__ import annotations

from wadi2d.basin.contract import missing_of, read_model, refresh
from wadi2d.basin.loader import load_network
from wadi2d.basin.routes import JunctionRoute, junction_routes

__all__ = ["JunctionRoute", "junction_routes", "load_network", "missing_of", "read_model", "refresh"]
