"""A named family of interchangeable implementations (engineering rule 4).

Interface: :class:`Registry`. Storm builders here, and losses, transforms, routing and baseflow in
:mod:`wadi2d.hydrology`, each own one instance. Adding a method is one new class with one decorator; nothing
in the core changes.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Any


class Registry[T]:
    """Maps a method name to the callable that builds it."""

    def __init__(self, family: str) -> None:
        self._family = family
        self._entries: dict[str, Callable[..., T]] = {}

    def register(self, name: str) -> Callable[[Callable[..., T]], Callable[..., T]]:
        """Class decorator: file the class under ``name``; a second entry of that name raises."""

        def add(entry: Callable[..., T]) -> Callable[..., T]:
            if name in self._entries:
                raise ValueError(f"{self._family} method {name!r} is already registered")
            self._entries[name] = entry
            return entry

        return add

    def build(self, name: str, **parameters: Any) -> T:
        """An instance of the method ``name``."""
        if name not in self._entries:
            raise KeyError(f"unknown {self._family} method {name!r}; known: {sorted(self._entries)}")
        return self._entries[name](**parameters)

    def __contains__(self, name: object) -> bool:
        return name in self._entries

    def __iter__(self) -> Iterator[str]:
        return iter(self._entries)
