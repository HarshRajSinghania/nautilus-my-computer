"""Pure state model for Column View: where the path ends and what is selected.

One immutable ColumnState answers "which folders are open, which column is
active, what is selected, what is previewed". Every user input is a function
(state, input) -> (new state, effects). The effects are plain data the view
executes in order; nothing here knows about GTK, GIO or Nautilus, so the rules
that used to be spread over GTK handlers are unit-tested.

Modelled on Nautilus's window slot: one location, one selection, and every
move is a single "go to location with this selection" step (Navigate), which
mirrors nautilus_window_slot_open_location_full(location, selection).
"""

from dataclasses import dataclass, replace

from . import uris


@dataclass(frozen=True)
class ColumnState:
    path: tuple[str, ...]  # open folder URIs, root first
    active: int = 0  # column holding the accent row and keyboard focus
    selection: tuple[str, ...] = ()  # selection inside path[active], the only real one
    preview: str | None = None  # file shown in the preview column
    # URI of our own Navigate whose echo is still on its way back from Nautilus.
    pending_echo: str | None = None

    @property
    def location(self) -> str:
        """What Nautilus's slot location must be: the deepest open folder."""
        return self.path[-1]

    def path_mark(self, index: int) -> str | None:
        """The row column `index` marks as part of the path: the next column's
        folder, or the previewed file for the last one. Derived, never stored."""
        if index + 1 < len(self.path):
            return self.path[index + 1]
        return self.preview


# Effects, executed in order by the view.


@dataclass(frozen=True)
class Truncate:
    """Drop every column deeper than `index`."""

    index: int


@dataclass(frozen=True)
class Append:
    """Open a new deepest column on `uri`."""

    uri: str


@dataclass(frozen=True)
class Reroot:
    """Throw the chain away and start a single column on `uri`."""

    uri: str


@dataclass(frozen=True)
class SetPreview:
    uri: str | None
    # Several files selected: the preview shows their stack instead.
    uris: tuple[str, ...] = ()


@dataclass(frozen=True)
class ApplySelection:
    """Make `uris` the selection of column `index` (empty clears it)."""

    index: int
    uris: tuple[str, ...]


@dataclass(frozen=True)
class Navigate:
    """Open `uri` in Nautilus's slot with `select` selected there (possibly
    nothing), as open_location_full does. `focus` re-arms keyboard focus on
    the active column once the echo arrives."""

    uri: str
    select: tuple[str, ...]
    focus: bool


@dataclass(frozen=True)
class Focus:
    index: int


@dataclass(frozen=True)
class Repaint:
    """Refresh path marks and the accent column from the state."""


Effect = Truncate | Append | Reroot | SetPreview | ApplySelection | Navigate | Focus | Repaint
Result = tuple[ColumnState, list[Effect]]


def root(uri: str) -> ColumnState:
    return ColumnState(path=(uri,))


def _index_of(state: ColumnState, uri: str) -> int | None:
    return next((i for i, p in enumerate(state.path) if uris.same_uri(p, uri)), None)


def _navigate(state: ColumnState, select: tuple[str, ...] = ()) -> tuple[ColumnState, Navigate]:
    """Every user-driven location change goes through here, so each one carries
    an explicit selection and restores keyboard focus."""
    state = replace(state, pending_echo=state.location)
    return state, Navigate(state.location, select, focus=True)


def click_background(state: ColumnState, col: int) -> Result:
    """Click on empty space in column `col`: its selection clears and the path
    ends there (Finder). Columns to the right close and the location follows."""
    effects: list[Effect] = []
    truncated = col < len(state.path) - 1
    state = replace(state, path=state.path[: col + 1], active=col, selection=(), preview=None)
    if truncated:
        effects.append(Truncate(col))
    effects += [ApplySelection(col, ()), SetPreview(None)]
    if truncated:
        state, nav = _navigate(state)
        effects.append(nav)
    effects.append(Repaint())
    return state, effects


def click_row(state: ColumnState, col: int, uri: str, is_folder: bool) -> Result:
    """Plain click (or a committed arrow-key move) on a row of column `col`."""
    effects: list[Effect] = []
    if is_folder:
        keep = col + 1
        already_open = keep < len(state.path) and uris.same_uri(state.path[keep], uri)
        if already_open:
            if keep + 1 < len(state.path):
                effects.append(Truncate(keep))
            path = state.path[: keep + 1]
        else:
            if keep < len(state.path):
                effects.append(Truncate(col))
            effects.append(Append(uri))
            path = state.path[:keep] + (uri,)
        state = replace(state, path=path, active=col, selection=(uri,), preview=None)
        effects += [ApplySelection(col, (uri,)), SetPreview(None)]
        state, nav = _navigate(state)
        effects += [nav, Repaint()]
        return state, effects

    truncated = col < len(state.path) - 1
    state = replace(state, path=state.path[: col + 1], active=col, selection=(uri,), preview=uri)
    if truncated:
        effects.append(Truncate(col))
    effects += [ApplySelection(col, (uri,)), SetPreview(uri)]
    if truncated:
        # The path now ends here. The clicked file stays selected, instead of
        # Nautilus selecting the folder it came from.
        state, nav = _navigate(state, select=(uri,))
        effects.append(nav)
    effects.append(Repaint())
    return state, effects


def multi_select(state: ColumnState, col: int, selected: tuple[str, ...]) -> Result:
    """Several rows selected in column `col`: nothing opens to its right, the
    preview shows their stack."""
    effects: list[Effect] = []
    truncated = col < len(state.path) - 1
    state = replace(state, path=state.path[: col + 1], active=col, selection=selected, preview=None)
    if truncated:
        effects.append(Truncate(col))
    effects += [ApplySelection(col, selected), SetPreview(None, selected)]
    if truncated:
        state, nav = _navigate(state, select=selected)
        effects.append(nav)
    effects.append(Repaint())
    return state, effects


def key_left(state: ColumnState) -> Result:
    """Move to the parent column; the folder we came from becomes its selection."""
    if state.active == 0:
        return state, []
    col = state.active - 1
    selected = (state.path[col + 1],)
    state = replace(state, active=col, selection=selected)
    return state, [ApplySelection(col, selected), Focus(col), Repaint()]


def key_right(state: ColumnState) -> Result:
    """Move into the child column; its path mark becomes the selection."""
    if state.active + 1 >= len(state.path):
        return state, []
    col = state.active + 1
    mark = state.path_mark(col)
    selected = (mark,) if mark else ()
    state = replace(state, active=col, selection=selected)
    return state, [ApplySelection(col, selected), Focus(col), Repaint()]


def location_changed(state: ColumnState, uri: str) -> Result:
    """Nautilus's slot location changed: our own echo, the pathbar, Back/Forward,
    the sidebar, a bookmark. Only ever keeps columns that are already open."""
    awaited = state.pending_echo is not None and uris.same_uri(state.pending_echo, uri)
    state = replace(state, pending_echo=None)
    idx = _index_of(state, uri)
    if idx is not None:
        if idx == len(state.path) - 1:
            return state, [Focus(state.active)] if awaited else []
        state = replace(state, path=state.path[: idx + 1], active=idx, selection=(), preview=None)
        return state, [Truncate(idx), ApplySelection(idx, ()), SetPreview(None), Repaint()]

    parent = uris.parent(uri)
    parent_idx = _index_of(state, parent) if parent is not None else None
    if parent_idx is not None:
        effects: list[Effect] = []
        if parent_idx < len(state.path) - 1:
            effects.append(Truncate(parent_idx))
        effects += [Append(uri), SetPreview(None), Repaint()]
        state = replace(
            state,
            path=state.path[: parent_idx + 1] + (uri,),
            active=parent_idx + 1,
            selection=(),
            preview=None,
        )
        return state, effects
    return root(uri), [Reroot(uri)]


def native_selection_changed(state: ColumnState, selected: tuple[str, ...]) -> Result:
    """The selection changed in Nautilus's own view (List/Grid, then back):
    adopt it into the deepest column."""
    col = len(state.path) - 1
    if state.active == col and state.selection == selected:
        return state, []
    state = replace(state, active=col, selection=selected)
    return state, [ApplySelection(col, selected), Repaint()]


def renamed(state: ColumnState, old: str, new: str) -> Result:
    """`old` was renamed to `new`: every URI at or under it moves with it."""
    path = tuple(uris.rebase(p, old, new) for p in state.path)
    selection = tuple(uris.rebase(s, old, new) for s in state.selection)
    preview = uris.rebase(state.preview, old, new) if state.preview else None
    moved = (path, selection, preview) != (state.path, state.selection, state.preview)
    if not moved:
        return state, []
    effects: list[Effect] = [Repaint()]
    if preview != state.preview:
        effects.append(SetPreview(preview))
    return replace(state, path=path, selection=selection, preview=preview), effects
