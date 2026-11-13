"""The saved maps of a run drawn on demand: one frame, one extent, one size, at the terrain pixel (W51).

RAS Mapper's way: the map for what is on screen is computed from the results file and the terrain, and nothing is
written for a time step. The rule is the product step's own (:mod:`wadi2d.products.pixels`), so a frame drawn here and
the rasters of record agree. ``wadi2d render <run>`` keeps one process open and answers one drawing at a time.
"""
