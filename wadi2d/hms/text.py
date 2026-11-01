"""Layer 1: lossless tokenizer and writer for the HEC-HMS block grammar.

Every HMS text file is a sequence of column-0 ``Type: Name`` blocks closed by ``End:`` (or ``End <Type>:``
for ``Computation Point``). Inside a block, lines are ``Key: Value``; sub-blocks exist only because of their
closing ``End X:`` line, so an opener is indistinguishable from an empty-valued key until the closer is
seen. Nothing is normalised: the indent, the separator with its spaces, the value with its trailing spaces
and the line ending of every line are kept, so :func:`dumps` reproduces the source byte for byte.

Interface: :func:`parse`, :func:`load`, :func:`dumps`, :func:`dump`, and the data types :class:`Line`,
:class:`Block`, :class:`Document`.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

BOM_UTF8 = b"\xef\xbb\xbf"
UTF8 = "utf-8"
LATIN1 = "latin-1"  # total on bytes, so the fallback is always lossless (HMS writes km2 with a single byte)

END_KEY = "End"
END_PREFIX = "End "
# Ordinary keys that happen to look like the closer of a block.
NOT_TERMINATORS = frozenset({"End Date", "End Time"})

_LINE_RE = re.compile(r"[^\r\n]*(?:\r\n|\n|\r)|[^\r\n]+\Z")
_FIELD_RE = re.compile(r"([ \t]*)([^:\s][^:]*)(:[ \t]*)(.*)", re.DOTALL)
_EOL_RE = re.compile(r"(\r\n|\n|\r)\Z")


@dataclass(slots=True)
class Line:
    """One physical line. A raw line (no ``key``) keeps its whole text in ``value``."""

    indent: str = ""
    key: str | None = None
    sep: str = ""
    value: str = ""
    eol: str = ""

    @property
    def is_field(self) -> bool:
        """True for a ``Key: Value`` line."""
        return self.key is not None

    @property
    def is_blank(self) -> bool:
        """True for a raw line holding only white space."""
        return self.key is None and not self.value.strip()

    def render(self) -> str:
        """The line exactly as it stood in the file."""
        return f"{self.indent}{self.key or ''}{self.sep}{self.value}{self.eol}"


@dataclass(slots=True)
class Block:
    """A block or sub-block: opener line, items in file order, closer (None when the file ended first)."""

    opener: Line
    items: list[Line | Block] = field(default_factory=list)
    closer: Line | None = None

    @property
    def kind(self) -> str:
        """The opener key: ``Subbasin``, ``Break Point`` ..."""
        return self.opener.key or ""

    @property
    def name(self) -> str:
        """The opener value without surrounding spaces."""
        return self.opener.value.strip()

    def fields(self) -> Iterator[Line]:
        """Direct ``Key: Value`` lines, repeated keys included, in file order."""
        return (item for item in self.items if isinstance(item, Line) and item.is_field)

    def blocks(self, kind: str | None = None) -> list[Block]:
        """Direct sub-blocks, optionally of one kind."""
        return [i for i in self.items if isinstance(i, Block) and (kind is None or i.kind == kind)]

    def get(self, key: str, default: str | None = None) -> str | None:
        """The stripped value of the first direct field named ``key``."""
        return next((line.value.strip() for line in self.fields() if line.key == key), default)

    def get_all(self, key: str) -> list[str]:
        """The stripped values of every direct field named ``key``, in order."""
        return [line.value.strip() for line in self.fields() if line.key == key]

    def render(self) -> str:
        """The block exactly as it stood in the file."""
        body = "".join(item.render() for item in self.items)
        return f"{self.opener.render()}{body}{self.closer.render() if self.closer else ''}"


@dataclass(slots=True)
class Document:
    """A tokenized file: top-level blocks and the lines between them, plus how to encode it back."""

    items: list[Line | Block] = field(default_factory=list)
    encoding: str = UTF8
    bom: bytes = b""

    def blocks(self, kind: str | None = None) -> list[Block]:
        """Top-level blocks, optionally of one kind."""
        return [i for i in self.items if isinstance(i, Block) and (kind is None or i.kind == kind)]

    def block(self, kind: str, name: str | None = None) -> Block | None:
        """The first top-level block of a kind, optionally with a given name."""
        return next((b for b in self.blocks(kind) if name is None or b.name == name), None)

    def unclosed(self) -> list[Block]:
        """Top-level blocks that reached the end of the file without a closer."""
        return [b for b in self.blocks() if b.closer is None]


def _decode(data: bytes) -> tuple[str, str]:
    try:
        return data.decode(UTF8), UTF8
    except UnicodeDecodeError:
        return data.decode(LATIN1), LATIN1


def _tokenize(raw: str) -> Line:
    eol_match = _EOL_RE.search(raw)
    eol = eol_match.group(1) if eol_match else ""
    body = raw[: len(raw) - len(eol)]
    match = _FIELD_RE.fullmatch(body)
    if match is None:
        return Line(value=body, eol=eol)
    return Line(indent=match[1], key=match[2], sep=match[3], value=match[4], eol=eol)


def _opens_block(line: Line) -> bool:
    if line.key is None or line.indent:
        return False
    return line.key != END_KEY and not line.key.startswith(END_PREFIX)


def _closes_block(line: Line, kind: str) -> bool:
    return not line.indent and line.key in (END_KEY, f"{END_PREFIX}{kind}")


def _is_terminator(line: Line) -> bool:
    return bool(line.key) and line.key.startswith(END_PREFIX) and line.key not in NOT_TERMINATORS


def _exact(key: str, target: str) -> bool:
    return key == target


def _suffix(key: str, target: str) -> bool:
    return key.endswith(f" {target}")


def _prefix(key: str, target: str) -> bool:
    return key.startswith(f"{target} ")


def _partner(items: list[Line | Block], closer: Line) -> int | None:
    """Index of the opener of ``closer`` in ``items``.

    ``End Layer:`` closes ``Element Layer:`` and ``Evaporation Method:`` is closed by ``End Evaporation:``,
    so the search runs from the exact key to the loose forms. The indent must agree: ``Layer:13`` inside a
    ``Map Layer:`` body is not the opener of ``End Layer:``. A closer with a value
    (``End Variant: Variant-1``) takes an exact key and the same value.
    """
    target = (closer.key or "")[len(END_PREFIX) :]
    value = closer.value.strip()
    for matches in (_exact,) if value else (_exact, _suffix, _prefix):
        for index in range(len(items) - 1, -1, -1):
            item = items[index]
            if not isinstance(item, Line) or item.key is None or item.indent != closer.indent:
                continue
            if matches(item.key, target) and (not value or item.value.strip() == value):
                return index
    return None


def _nest(lines: list[Line]) -> list[Line | Block]:
    """Fold sub-blocks: each ``End X:`` reduces the items back to its opener."""
    items: list[Line | Block] = []
    for line in lines:
        index = _partner(items, line) if _is_terminator(line) else None
        if index is None:
            items.append(line)
            continue
        opener = items[index]
        assert isinstance(opener, Line)
        body = items[index + 1 :]
        del items[index:]
        items.append(Block(opener, body, line))
    return items


def _group(lines: list[Line]) -> list[Line | Block]:
    items: list[Line | Block] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        if not _opens_block(line):
            items.append(line)
            index += 1
            continue
        kind = line.key or ""
        end = next((j for j in range(index + 1, len(lines)) if _closes_block(lines[j], kind)), None)
        stop = len(lines) if end is None else end
        closer = None if end is None else lines[end]
        items.append(Block(line, _nest(lines[index + 1 : stop]), closer))
        index = stop + 1
    return items


def parse(data: bytes) -> Document:
    """Tokenize the bytes of an HMS text file."""
    bom = BOM_UTF8 if data.startswith(BOM_UTF8) else b""
    text, encoding = _decode(data[len(bom) :])
    lines = [_tokenize(match.group()) for match in _LINE_RE.finditer(text)]
    return Document(items=_group(lines), encoding=encoding, bom=bom)


def load(path: str | Path) -> Document:
    """Tokenize an HMS text file; it is only read."""
    return parse(Path(path).read_bytes())


def dumps(document: Document) -> bytes:
    """The exact bytes the document was parsed from."""
    return document.bom + "".join(item.render() for item in document.items).encode(document.encoding)


def dump(document: Document, path: str | Path) -> None:
    """Write the document to ``path``."""
    Path(path).write_bytes(dumps(document))
