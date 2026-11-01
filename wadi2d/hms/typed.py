"""Layer 2 base: how a tokenized block becomes a typed model.

A model declares its HMS keys once, as field aliases (:func:`hms`, :func:`hms_list`). :class:`Cursor` fills
those fields from a block and tracks what was consumed, so whatever a model does not know stays in
``unknown`` and is reported, never dropped. A value that does not parse as its declared number stays there
too. Values are in the units of the file: the typed layer does not convert.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Self, get_args, get_origin

from pydantic import BaseModel, ConfigDict, Field

from wadi2d.hms.text import Block, Line

DATE_FORMAT = "%d %B %Y"  # 31 December 1999
STAMP_DATE_FORMAT = "%d%b%Y"  # 31Dec1999
STAMP_SEPARATOR = ","


def hms(key: str) -> Any:
    """A model field read from the first occurrence of the HMS key ``key``."""
    return Field(default=None, alias=key)


def hms_list(key: str) -> Any:
    """A model field holding every occurrence of a repeated HMS key, in order."""
    return Field(default_factory=list, alias=key)


class HmsModel(BaseModel):
    """Base of the typed layer: attributes by name, HMS keys as aliases, nothing silently accepted."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid", arbitrary_types_allowed=True)


class RawField(HmsModel):
    """A key and value kept verbatim (stripped). An empty key marks a line with no colon."""

    model_config = ConfigDict(frozen=True)

    key: str
    value: str


class RawBlock(HmsModel):
    """A block kept as data: kind, name, fields in file order and nested blocks."""

    kind: str
    name: str = ""
    fields: list[RawField] = Field(default_factory=list)
    blocks: list[RawBlock] = Field(default_factory=list)

    @classmethod
    def from_block(cls, block: Block) -> Self:
        """Copy a tokenized block."""
        return cls(
            kind=block.kind,
            name=block.name,
            fields=[RawField(key=f.key or "", value=f.value.strip()) for f in block.fields()],
            blocks=[cls.from_block(b) for b in block.blocks()],
        )

    def get(self, key: str) -> str | None:
        """The first value of ``key``."""
        return next((f.value for f in self.fields if f.key == key), None)

    def get_all(self, key: str) -> list[str]:
        """Every value of ``key``, in order."""
        return [f.value for f in self.fields if f.key == key]


class Method(HmsModel):
    """A method variant chosen by a selector key; ``method`` is the selector value verbatim."""

    method: str
    recognised: bool = True


class UnknownMethod(Method):
    """A selector value this reader has no model for; its parameters stay in the element's ``unknown``."""

    recognised: bool = False


@dataclass(frozen=True)
class UnknownEntry:
    """One item a model did not recognise: which block, which key, which value."""

    where: str
    key: str
    value: str


def _value_kind(annotation: Any) -> type:
    if get_origin(annotation) is list:
        return list
    args = get_args(annotation)
    return next((t for t in (float, int) if t in args or annotation is t), str)


class Cursor:
    """Reads the fields of one block, remembering which were consumed."""

    def __init__(self, block: Block) -> None:
        self._fields = list(block.fields())
        self._taken = [False] * len(self._fields)
        self._raw = [i.value for i in block.items if isinstance(i, Line) and not i.is_field]
        self._openers = {b.kind: b.name for b in reversed(block.blocks())}

    def _indices(self, key: str) -> list[int]:
        return [i for i, f in enumerate(self._fields) if f.key == key and not self._taken[i]]

    def take(self, key: str) -> str | None:
        """The first unread value of ``key``, else the name of a sub-block opened by ``key``, else None."""
        indices = self._indices(key)
        if not indices:
            return self._openers.get(key)
        self._taken[indices[0]] = True
        return self._fields[indices[0]].value.strip()

    def take_all(self, key: str) -> list[str]:
        """Every unread value of ``key``."""
        indices = self._indices(key)
        for index in indices:
            self._taken[index] = True
        return [self._fields[i].value.strip() for i in indices]

    def take_number(self, key: str, kind: type) -> float | int | None:
        """The first unread value as a number. An unparsable value is left unread, so it gets reported."""
        indices = self._indices(key)
        if not indices:
            return None
        text = self._fields[indices[0]].value.strip()
        number = None
        if text:
            try:
                number = float(text) if kind is float else int(text)
            except ValueError:
                return None
        self._taken[indices[0]] = True
        return number

    def fill(self, model: type[BaseModel]) -> dict[str, Any]:
        """Read every field of ``model`` declared with an HMS alias."""
        values: dict[str, Any] = {}
        for attribute, info in model.model_fields.items():
            if info.alias is None:
                continue
            kind = _value_kind(info.annotation)
            if kind is list:
                values[attribute] = self.take_all(info.alias)
            elif kind is str:
                values[attribute] = self.take(info.alias)
            else:
                values[attribute] = self.take_number(info.alias, kind)
        return values

    def leftovers(self) -> list[RawField]:
        """What nobody read, in file order; lines with no colon follow with an empty key."""
        unread = [
            RawField(key=f.key or "", value=f.value.strip())
            for f, taken in zip(self._fields, self._taken, strict=True)
            if not taken
        ]
        return unread + [RawField(key="", value=text.strip()) for text in self._raw if text.strip()]


class BlockModel(HmsModel):
    """A model filled from one block; ``unknown`` and ``blocks`` hold what it does not type."""

    name: str = ""
    unknown: list[RawField] = Field(default_factory=list)
    blocks: list[RawBlock] = Field(default_factory=list)

    @classmethod
    def extra_values(cls, cursor: Cursor, values: dict[str, Any]) -> dict[str, Any]:
        """Hook: more values read after the declared fields (method variants, for instance)."""
        return {}

    @classmethod
    def from_block(cls, block: Block) -> Self:
        """Build the model, keeping every unread key and every sub-block."""
        cursor = Cursor(block)
        values = cursor.fill(cls)
        values |= cls.extra_values(cursor, values)
        return cls(
            name=block.name,
            unknown=cursor.leftovers(),
            blocks=[RawBlock.from_block(b) for b in block.blocks()],
            **values,
        )

    def label(self) -> str:
        """How this block is named in a report."""
        return f"{type(self).__name__} {self.name}".strip()

    def unknown_report(self) -> list[UnknownEntry]:
        """The unread keys and the unrecognised method selectors of this block."""
        where = self.label()
        entries = [UnknownEntry(where, f.key, f.value) for f in self.unknown]
        methods = (v for v in self.__dict__.values() if isinstance(v, Method) and not v.recognised)
        return entries + [UnknownEntry(where, "method selector", m.method) for m in methods]


def _clock(time_text: str) -> timedelta:
    """``24:00`` is legal in HMS, so the clock is an offset from midnight, not a time of day."""
    hours, minutes, *rest = [int(part) for part in time_text.strip().split(":")]
    return timedelta(hours=hours, minutes=minutes, seconds=rest[0] if rest else 0)


def parse_date_time(date_text: str, time_text: str) -> datetime:
    """``31 December 1999`` and ``24:00`` as a datetime (2000-01-01 00:00)."""
    return datetime.strptime(date_text.strip(), DATE_FORMAT) + _clock(time_text)


def parse_stamp(stamp: str) -> datetime:
    """``01Jan2000, 15:35`` or ``31Dec1999, 24:00`` as a datetime."""
    date_text, time_text = stamp.split(STAMP_SEPARATOR)
    return datetime.strptime(date_text.strip(), STAMP_DATE_FORMAT) + _clock(time_text)


class TimeWindowModel(BlockModel):
    """The simulation window shared by a control file and a depth-area analysis."""

    time_zone_id: str | None = hms("Time Zone ID")
    time_zone_gmt_offset: int | None = hms("Time Zone GMT Offset")
    start_date: str | None = hms("Start Date")
    start_time: str | None = hms("Start Time")
    end_date: str | None = hms("End Date")
    end_time: str | None = hms("End Time")
    time_interval: float | None = hms("Time Interval")

    @property
    def start(self) -> datetime | None:
        """Start of the window."""
        if self.start_date is None or self.start_time is None:
            return None
        return parse_date_time(self.start_date, self.start_time)

    @property
    def end(self) -> datetime | None:
        """End of the window."""
        if self.end_date is None or self.end_time is None:
            return None
        return parse_date_time(self.end_date, self.end_time)

    @property
    def interval(self) -> timedelta | None:
        """The time step; the file holds it in minutes."""
        return None if self.time_interval is None else timedelta(minutes=self.time_interval)

    @property
    def n_steps(self) -> int | None:
        """Number of time points in the window, both ends included."""
        if self.start is None or self.end is None or self.interval is None:
            return None
        return int((self.end - self.start) / self.interval) + 1
