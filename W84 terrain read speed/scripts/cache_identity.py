"""The hashes of the code that every grid, mask and strip cache key holds, of whichever package is on the path.
Run on the old package and on the new: the same three lines mean the old caches are still found."""

import wadi2d
from wadi2d.io.cache import BUILDER_SOURCES, STRIP_SOURCES, builder_identity, source_identity

print(wadi2d.__file__)
print("builder", builder_identity(), BUILDER_SOURCES)
print("strip  ", source_identity(STRIP_SOURCES), STRIP_SOURCES)
