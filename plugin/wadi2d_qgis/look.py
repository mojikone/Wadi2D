# Wadi2D QGIS plugin. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""The look of the dock (W99): the palette and the metrics of the W94 mockup as named constants, and one style sheet.

Every colour and size the dock's own frame uses is here and nowhere else. :data:`LIGHT` is the mockup's palette;
:data:`DARK` is the same roles for a dark QGIS theme, where a white card would leave the theme's light text unreadable.
:func:`sheet` is set on the dock's own containers and matched by object name, so the QGIS widgets inside the sections
keep the look of the user's theme. A state is never told by colour alone: a badge, a pill and a step always carry
words or a mark.
"""

from __future__ import annotations

from dataclasses import dataclass

from .section_status import MISSING, OPTIONAL, READY


@dataclass(frozen=True)
class Palette:
    page: str
    card: str
    line: str
    line_strong: str
    text: str
    muted: str
    accent: str
    accent_strong: str
    on_accent: str
    badges: dict
    """Model type to (text, fill) of its badge; the empty key is a model with no type."""
    tag_2d: tuple[str, str]
    tag_lumped: tuple[str, str]
    status: dict
    """Section status to (text, fill, card border)."""


LIGHT = Palette(
    page="#f4f5f7",
    card="#ffffff",
    line="#dfe3e8",
    line_strong="#c7ced6",
    text="#1c2430",
    muted="#4f5b68",
    accent="#1d5f9e",
    accent_strong="#123f6b",
    on_accent="#ffffff",
    badges={
        "2d": ("#1d5f9e", "#e4eef8"),
        "lumped": ("#8a4b00", "#fbecd9"),
        "hybrid_lumped": ("#5b3a8a", "#ece4f6"),
        "hybrid_2d": ("#5b3a8a", "#ece4f6"),
        "": ("#4f5b68", "#eef0f3"),
    },
    tag_2d=("#1d4f80", "#dcebf8"),
    tag_lumped=("#7a4200", "#f9e3c8"),
    status={
        READY: ("#1e6b34", "#e2f2e6", "#dfe3e8"),
        OPTIONAL: ("#4f5b68", "#eef0f3", "#dfe3e8"),
        MISSING: ("#9b1c13", "#fbe1df", "#e6a49f"),
    },
)
"""The W94 mockup's palette."""

DARK = Palette(
    page="#26292d",
    card="#30343a",
    line="#474d55",
    line_strong="#5c646e",
    text="#e8ebee",
    muted="#aeb6c0",
    accent="#6fb0ea",
    accent_strong="#9cc9f2",
    on_accent="#10202f",
    badges={
        "2d": ("#a9d2f7", "#1f3d5a"),
        "lumped": ("#f3c78f", "#4a3312"),
        "hybrid_lumped": ("#d3bdf0", "#3b2d55"),
        "hybrid_2d": ("#d3bdf0", "#3b2d55"),
        "": ("#c3cad2", "#3d434a"),
    },
    tag_2d=("#a9d2f7", "#1f3d5a"),
    tag_lumped=("#f3c78f", "#4a3312"),
    status={
        READY: ("#9be0ae", "#1f3d29", "#474d55"),
        OPTIONAL: ("#c3cad2", "#3d434a", "#474d55"),
        MISSING: ("#ffb3ab", "#4d2420", "#a55a52"),
    },
)
"""The same roles on a dark QGIS theme (Night Mapping, Blend of Gray)."""

DARK_BELOW = 128
"""A theme whose window colour is darker than this lightness (0 to 255) gets :data:`DARK`."""

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
BODY_MARGIN = 4
"""Left and right of the cards: with a card's own edge and padding it is the margin the sections had before the cards, so a
wide section still fits a dock of the same width."""
CARD_PAD = 4
PILL_TOP = 3
"""How far under the card's edge the status pill sits, on the line of the section's own title."""

# Object names the sheet matches
FRAME = "w2dFrame"
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
BODY = "w2dBody"
SECTION_CARD = "w2dSectionCard"
STATUS_WORDS = "w2dStatusWords"
FOOTER = "w2dFooter"
PILL = "w2dPill"
STEP = "w2dStep"
STRIP = "w2dStrip"
NEEDS = "w2dNeeds"


def is_dark(palette) -> bool:
    """Whether a Qt palette is a dark theme's."""
    from qgis.PyQt.QtGui import QPalette

    return palette.color(QPalette.Window).lightness() < DARK_BELOW


def _pair(name: str, prop: str, value: str, colours: tuple[str, str]) -> str:
    text, fill = colours
    return f'QLabel#{name}[{prop}="{value}"] {{ color: {text}; background: {fill}; }}\n'


def sheet(dark: bool = False) -> str:
    """The style sheet of the dock's own frame, in the mockup's palette or its dark counterpart."""
    p = DARK if dark else LIGHT
    parts = [
        f"QWidget#{FRAME}, QWidget#{START}, QWidget#{BODY} {{ background: {p.page}; }}",
        f"QFrame#{TYPE_CARD} {{ background: {p.card}; border: 1px solid {p.line}; border-radius: {RADIUS}px; }}",
        f"QFrame#{TYPE_CARD}:hover {{ border: 1px solid {p.accent}; }}",
        f'QFrame#{TYPE_CARD}[current="true"] {{ border: 2px solid {p.accent}; }}',
        f"QFrame#{TYPE_CARD}:focus {{ border: 2px solid {p.accent_strong}; }}",
        f"QLabel#{CARD_TITLE} {{ color: {p.text}; font-size: {FONT_CARD}px; font-weight: 600; background: transparent; }}",
        f"QLabel#{WORDS} {{ color: {p.muted}; font-size: {FONT_SMALL}px; background: transparent; }}",
        f"QLabel#{CAPTION} {{ color: {p.muted}; font-size: {FONT_SMALL}px; font-weight: 600; background: transparent; }}",
        f"QLabel#{BADGE} {{ font-size: {FONT_TINY}px; font-weight: 600; padding: 2px 8px; border-radius: {RADIUS_BADGE}px; }}",
        f"QLabel#{TAG} {{ font-size: {FONT_TINY}px; padding: 2px 6px; border-radius: {RADIUS_TAG}px; }}",
        f"QFrame#{HEADER} {{ background: {p.card}; border: none; border-bottom: 1px solid {p.line}; }}",
        f"QLabel#{HEADER_TITLE} {{ color: {p.text}; font-size: {FONT_CARD}px; font-weight: 700; background: transparent; }}",
        f"QPushButton#{QUIET_BUTTON} {{ min-height: {BUTTON_HEIGHT - 2}px; padding: 0 {PAD}px; border: 1px solid {p.line_strong};"
        f" border-radius: {RADIUS_BUTTON}px; background: {p.card}; color: {p.text}; font-size: {FONT_BODY}px; }}",
        f"QPushButton#{QUIET_BUTTON}:hover {{ border-color: {p.accent}; }}",
        f"QPushButton#{QUIET_BUTTON}:disabled {{ color: {p.line_strong}; }}",
        f"QPushButton#{PRIMARY_BUTTON} {{ min-height: {PRIMARY_HEIGHT - 2}px; padding: 0 22px; border: none;"
        f" border-radius: {RADIUS_BUTTON}px; background: {p.accent}; color: {p.on_accent}; font-size: 14px; font-weight: 600; }}",
        f"QPushButton#{PRIMARY_BUTTON}:hover {{ background: {p.accent_strong}; }}",
        f"QPushButton#{PRIMARY_BUTTON}:disabled {{ background: {p.line_strong}; color: {p.card}; }}",
        f"QFrame#{FOOTER} {{ background: {p.card}; border: none; border-top: 1px solid {p.line}; }}",
        f"QFrame#{STRIP} {{ background: {p.card}; border: none; border-bottom: 1px solid {p.line}; }}",
        f"QFrame#{SECTION_CARD} {{ background: {p.card}; border: 1px solid {p.line}; border-radius: {RADIUS}px; }}",
        f"QLabel#{STATUS_WORDS} {{ color: {p.muted}; font-size: {FONT_SMALL}px; background: transparent; }}",
        f"QLabel#{NEEDS} {{ color: {p.muted}; font-size: {FONT_SMALL}px; background: transparent; }}",
        f"QLabel#{PILL} {{ font-size: {FONT_TINY}px; font-weight: 600; padding: 1px 8px; border-radius: {RADIUS_BADGE}px; }}",
        f"QPushButton#{STEP} {{ font-size: {FONT_TINY}px; font-weight: 600; padding: 5px 2px; border: 1px solid transparent;"
        f" border-radius: {RADIUS_TAG}px; }}",
        f"QPushButton#{STEP}:hover {{ border: 1px solid {p.accent}; }}",
        f'QPushButton#{STEP}[current="true"] {{ border: 1px solid {p.accent}; }}',
    ]
    text = "\n".join(parts) + "\n"
    for kind, colours in p.badges.items():
        text += _pair(BADGE, "kind", kind, colours)
    text += _pair(TAG, "lumped", "true", p.tag_lumped) + _pair(TAG, "lumped", "false", p.tag_2d)
    for status, (ink_colour, fill, border) in p.status.items():
        text += _pair(PILL, "status", status, (ink_colour, fill))
        text += f'QPushButton#{STEP}[status="{status}"] {{ color: {ink_colour}; background: {fill}; }}\n'
        text += f'QFrame#{SECTION_CARD}[status="{status}"] {{ border: 1px solid {border}; }}\n'
    missing = p.status[MISSING][0]
    text += f'QLabel#{STATUS_WORDS}[status="{MISSING}"], QLabel#{NEEDS}[status="{MISSING}"] {{ color: {missing}; }}\n'
    text += f'QLabel#{NEEDS}[status="{READY}"] {{ color: {p.status[READY][0]}; }}\n'
    return text


def ink(widget, dark: bool = False) -> None:
    """The widget's own text in the palette's text colour, for a native widget on one of the dock's cards: a style
    sheet rule on a check box would take its indicator's drawing away from the theme."""
    from qgis.PyQt.QtGui import QColor, QPalette

    palette = widget.palette()
    for role in (QPalette.WindowText, QPalette.ButtonText, QPalette.Text):
        palette.setColor(role, QColor((DARK if dark else LIGHT).text))
    widget.setPalette(palette)


def restyle(widget) -> None:
    """After a property the sheet matches has changed: Qt reads a widget's properties once, when it first styles it."""
    widget.style().unpolish(widget)
    widget.style().polish(widget)
    widget.update()
