"""Stateless selection rules for one file listing (#178).

A selection is a set of URIs plus a Shift-range anchor. Identity is the URI,
never a row position, so a selection survives a reload or a re-sort. Nothing
here knows about GTK, columns, or the Miller path: the view decides which
listing is active, then asks these functions what the selection becomes.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum


class Kind(Enum):
    EMPTY = "empty"
    SINGLE = "single"
    MULTI = "multi"


@dataclass(frozen=True)
class Selection:
    uris: frozenset[str] = frozenset()
    # Where a Shift-click range starts: the last URI clicked.
    anchor: str | None = None

    @property
    def kind(self) -> Kind:
        if not self.uris:
            return Kind.EMPTY
        return Kind.SINGLE if len(self.uris) == 1 else Kind.MULTI


def click(sel: Selection, uri: str) -> Selection:
    """Plain click: select only this URI."""
    return Selection(frozenset((uri,)), uri)


def ctrl_click(sel: Selection, uri: str) -> Selection:
    """Ctrl-click: add or remove one URI, leaving the rest alone."""
    return Selection(sel.uris ^ {uri}, uri)


def shift_click(
    sel: Selection, uri: str, ordered: Sequence[str], *, extend: bool = False
) -> Selection:
    """Shift-click: select from the anchor to this URI in display order.
    Without extend (Ctrl+Shift adds to the selection) every URI outside the
    range is dropped. The anchor stays where it was."""
    if sel.anchor is None or sel.anchor not in ordered or uri not in ordered:
        return Selection(sel.uris | {uri} if extend else frozenset((uri,)), uri)
    a, b = ordered.index(sel.anchor), ordered.index(uri)
    span = frozenset(ordered[min(a, b) : max(a, b) + 1])
    return Selection(sel.uris | span if extend else span, sel.anchor)


def select_all(ordered: Sequence[str]) -> Selection:
    return Selection(frozenset(ordered))


def clear(sel: Selection) -> Selection:
    """Drop the whole selection. Has no navigation side effects."""
    return Selection()


def target(sel: Selection, uri: str) -> Selection:
    """What a drag or a context menu on `uri` operates on: the whole group when
    the URI is inside it, else only that URI."""
    return sel if uri in sel.uris else click(sel, uri)


def reconcile(sel: Selection, ordered: Sequence[str]) -> Selection:
    """After a reload or a sort: keep URIs still listed, drop vanished ones."""
    present = frozenset(ordered)
    anchor = sel.anchor if sel.anchor in present else None
    return Selection(sel.uris & present, anchor)


def ordered_uris(sel: Selection, ordered: Sequence[str]) -> tuple[str, ...]:
    """The selected URIs in display order (for the stack preview and file ops)."""
    return tuple(uri for uri in ordered if uri in sel.uris)
