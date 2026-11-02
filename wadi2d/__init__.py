"""Wadi2D: a GPU 2D shallow-water solver with sub-grid terrain and HEC-HMS-style hydrology inside.

The package layout follows the design note in ``W1 research and design note/design_note.md``:
one job per module, one configuration schema as the single source of truth (``wadi2d.config``),
versioned data contracts (``wadi2d.io``), registries for every method family.
"""

__version__ = "0.1.0"
