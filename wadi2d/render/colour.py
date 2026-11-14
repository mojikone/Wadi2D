"""Values to a picture. The colours are whoever asks for the picture's to choose; here they are only laid on.

A ramp is ``{"kind": ..., "stops": [[value, red, green, blue, alpha], ...]}`` with rising values and colours 0 to 255.
``interpolated`` eases between stops and holds the end colours beyond them; ``classes`` gives a value the colour of the
last stop at or below it. The picture is blue, green, red, alpha, a byte each, colour already multiplied by alpha, which
is what a Qt image of format ARGB32_Premultiplied holds on this byte order. A dry pixel is clear.
"""

from __future__ import annotations

INTERPOLATED, CLASSES = "interpolated", "classes"
FULL = 255.0
BGRA = (2, 1, 0)
"""Where red, green and blue of a stop go."""


def to_bgra(xp, values, ramp: dict):
    """(height, width, 4) bytes from (height, width) values; NaN is clear."""
    stops = sorted(ramp["stops"], key=lambda stop: stop[0])
    if not stops or any(len(stop) != 5 for stop in stops):
        raise ValueError("a ramp needs stops of a value and four colour numbers")
    at = xp.asarray([stop[0] for stop in stops], xp.float32)
    colours = xp.asarray([stop[1:] for stop in stops], xp.float32)
    dry = xp.isnan(values)
    flat = xp.where(dry, at[0], values).ravel()
    kind = ramp.get("kind", INTERPOLATED)
    if kind == INTERPOLATED:
        channels = [xp.interp(flat, at, colours[:, n]) for n in range(4)]
    elif kind == CLASSES:
        index = xp.clip(xp.searchsorted(at, flat, side="right") - 1, 0, len(stops) - 1)
        channels = [colours[index, n] for n in range(4)]
    else:
        raise ValueError(f"no ramp kind {kind!r}: {INTERPOLATED} or {CLASSES}")
    alpha = xp.where(dry.ravel(), 0.0, channels[3])
    out = xp.empty((flat.size, 4), xp.uint8)
    for place, channel in zip(BGRA, channels[:3], strict=True):
        out[:, place] = xp.rint(channel * alpha / FULL).astype(xp.uint8)
    out[:, 3] = xp.rint(alpha).astype(xp.uint8)
    return out.reshape(values.shape[0], values.shape[1], 4)
