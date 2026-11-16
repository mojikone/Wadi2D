# Wadi2D QGIS plugin. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""The look of the dock (W99): the palette and the metrics of the W94 mockup as named constants, and one style sheet.

Every colour and size the dock's own frame uses is here and nowhere else. The sheet is set on the dock's own
containers and matched by object name, so the QGIS widgets inside the sections keep the look of the user's theme. A
state is never told by colour alone: a badge, a pill and a step always carry their words.
"""

from __future__ import annotations

# Palette (W94 mockup)
PAGE = "#f4f5f7"
CARD = "#ffffff"
LINE = "#dfe3e8"
LINE_STRONG = "#c7ced6"
TEXT = "#1c2430"
MUTED = "#4f5b68"
ACCENT = "#1d5f9e"
ACCENT_DARK = "#123f6b"
TRACK = "#e6e9ed"
ON_ACCENT = "#ffffff"

BADGES = {
    "2d": ("#1d5f9e", "#e4eef8"),
    "lumped": ("#8a4b00", "#fbecd9"),
    "hybrid_lumped": ("#5b3a8a", "#ece4f6"),
    "hybrid_2d": ("#5b3a8a", "#ece4f6"),
    "": (MUTED, "#eef0f3"),
}
"""Model type to (text, fill) of its badge; the empty key is a model with no type."""
TAG_2D = ("#1d4f80", "#dcebf8")
TAG_LUMPED = ("#7a4200", "#f9e3c8")

READY, OPTIONAL, MISSING = "ready", "optional", "missing"
STATUS = {
    READY: ("#1e6b34", "#e2f2e6", LINE),
    OPTIONAL: (MUTED, "#eef0f3", LINE),
    MISSING: ("#9b1c13", "#fbe1df", "#e6a49f"),
}
"""Section status to (text, fill, card border)."""
STATUS_WORDS = {READY: "Ready", OPTIONAL: "Optional", MISSING: "Missing"}

# Metrics, px
RADIUS = 8
RADIUS_BUTTON = 6
RADIUS_TAG = 4
RADIUS_BADGE = 10
GAP = 8
PAD = 12
PAD_PAGE = 16
FONT_TITLE = 17
FONT_CARD = 15
FONT_BODY = 13
FONT_SMALL = 12
FONT_TINY = 11
BUTTON_HEIGHT = 32
PRIMARY_HEIGHT = 40

# Object names the sheet matches
START = "w2dStart"
TYPE_CARD = "w2dTypeCard"
CARD_TITLE = "w2dCardTitle"
WORDS = "w2dWords"
CAPTION = "w2dCaption"
BADGE = "w2dBadge"
TAG = "w2dTag"
HEADER = "w2dHeader"
HEADER_TITLE = "w2dHeaderTitle"
QUIET_BUTTON = "w2dQuiet"
PRIMARY_BUTTON = "w2dPrimary"
FOOTER = "w2dFooter"
PILL = "w2dPill"
STEP = "w2dStep"
STRIP = "w2dStrip"
NEEDS = "w2dNeeds"


def _pair(name: str, prop: str, value: str, colours: tuple[str, str]) -> str:
    text, fill = colours
    return f'QLabel#{name}[{prop}="{value}"] {{ color: {text}; background: {fill}; }}\n'


def sheet() -> str:
    """The style sheet of the dock's own frame."""
    parts = [
        f"QWidget#{START} {{ background: {PAGE}; }}",
        f"QFrame#{TYPE_CARD} {{ background: {CARD}; border: 1px solid {LINE}; border-radius: {RADIUS}px; }}",
        f"QFrame#{TYPE_CARD}:hover {{ border: 1px solid {ACCENT}; }}",
        f'QFrame#{TYPE_CARD}[current="true"] {{ border: 2px solid {ACCENT}; }}',
        f"QFrame#{TYPE_CARD}:focus {{ border: 2px solid {ACCENT_DARK}; }}",
        f"QLabel#{CARD_TITLE} {{ color: {TEXT}; font-size: {FONT_CARD}px; font-weight: 600; background: transparent; }}",
        f"QLabel#{WORDS} {{ color: {MUTED}; font-size: {FONT_SMALL}px; background: transparent; }}",
        f"QLabel#{CAPTION} {{ color: {MUTED}; font-size: {FONT_SMALL}px; font-weight: 600; background: transparent; }}",
        f"QLabel#{BADGE} {{ font-size: {FONT_TINY}px; font-weight: 600; padding: 2px 8px; border-radius: {RADIUS_BADGE}px; }}",
        f"QLabel#{TAG} {{ font-size: {FONT_TINY}px; padding: 2px 6px; border-radius: {RADIUS_TAG}px; }}",
        f"QFrame#{HEADER} {{ background: {CARD}; border: none; border-bottom: 1px solid {LINE}; }}",
        f"QLabel#{HEADER_TITLE} {{ color: {TEXT}; font-size: {FONT_CARD}px; font-weight: 700; background: transparent; }}",
        f"QPushButton#{QUIET_BUTTON} {{ min-height: {BUTTON_HEIGHT - 2}px; padding: 0 {PAD}px; border: 1px solid {LINE_STRONG};"
        f" border-radius: {RADIUS_BUTTON}px; background: {CARD}; color: {TEXT}; font-size: {FONT_BODY}px; }}",
        f"QPushButton#{QUIET_BUTTON}:hover {{ border-color: {ACCENT}; }}",
        f"QPushButton#{QUIET_BUTTON}:disabled {{ color: {LINE_STRONG}; }}",
        f"QPushButton#{PRIMARY_BUTTON} {{ min-height: {PRIMARY_HEIGHT - 2}px; padding: 0 22px; border: none;"
        f" border-radius: {RADIUS_BUTTON}px; background: {ACCENT}; color: {ON_ACCENT}; font-size: 14px; font-weight: 600; }}",
        f"QPushButton#{PRIMARY_BUTTON}:hover {{ background: {ACCENT_DARK}; }}",
        f"QPushButton#{PRIMARY_BUTTON}:disabled {{ background: {LINE_STRONG}; }}",
        f"QFrame#{FOOTER} {{ background: {CARD}; border: none; border-top: 1px solid {LINE}; }}",
        f"QFrame#{STRIP} {{ background: {CARD}; border: none; border-bottom: 1px solid {LINE}; }}",
        f"QLabel#{NEEDS} {{ font-size: {FONT_SMALL}px; background: transparent; }}",
        f"QLabel#{PILL} {{ font-size: {FONT_TINY}px; font-weight: 600; padding: 2px 8px; border-radius: {RADIUS_BADGE}px; }}",
        f"QPushButton#{STEP} {{ font-size: {FONT_TINY}px; font-weight: 600; padding: 5px 2px; border: none;"
        f" border-radius: {RADIUS_TAG}px; }}",
    ]
    text = "\n".join(parts) + "\n"
    for kind, colours in BADGES.items():
        text += _pair(BADGE, "kind", kind, colours)
    text += _pair(TAG, "lumped", "true", TAG_LUMPED) + _pair(TAG, "lumped", "false", TAG_2D)
    for status, (ink, fill, _border) in STATUS.items():
        text += _pair(PILL, "status", status, (ink, fill))
        text += f'QPushButton#{STEP}[status="{status}"] {{ color: {ink}; background: {fill}; }}\n'
    return text


def ink(widget, colour: str = TEXT) -> None:
    """The widget's own text in a colour of the palette above, for a native widget on one of the dock's light cards:
    a style sheet rule on a check box would take its indicator's drawing away from the theme."""
    from qgis.PyQt.QtGui import QColor, QPalette

    palette = widget.palette()
    for role in (QPalette.WindowText, QPalette.ButtonText, QPalette.Text):
        palette.setColor(role, QColor(colour))
    widget.setPalette(palette)


def restyle(widget) -> None:
    """After a property the sheet matches has changed: Qt reads a widget's properties once, when it first styles it."""
    widget.style().unpolish(widget)
    widget.style().polish(widget)
    widget.update()
