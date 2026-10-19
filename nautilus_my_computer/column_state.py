"""Pure Column View rules that kept regressing, kept out of GTK so they are unit-tested.

- click_background: a click on a column's empty space, as (state, col) ->
  (new state, effects). The effects are plain data ColumnView._execute runs in
  order. Navigate mirrors nautilus_window_slot_open_location_full(location,
  selection): one location, one explicit selection.
- paint_plan: which row each column marks as the path, and which single column
  reads as accent (#189).
"""

from dataclasses import dataclass, replace


@dataclass(frozen=True)
class ColumnState:
    path: tuple[str, ...]  # open folder URIs, root first
    active: int = 0  # column holding the accent row and keyboard focus
    selection: tuple[str, ...] = ()  # selection inside path[active], the only real one
    preview: str | None = None  # file shown in the preview column

    @property
    def location(self) -> str:
        """What Nautilus's slot location must be: the deepest open folder."""
        return self.path[-1]


# Effects, executed in order by the view.


@dataclass(frozen=True)
class Truncate:
    """Drop every column deeper than `index`."""

    index: int


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
    nothing), as open_location_full does. `focus` restores keyboard focus on
    the active column once the slot has moved."""

    uri: str
    select: tuple[str, ...]
    focus: bool


@dataclass(frozen=True)
class Repaint:
    """Refresh path marks and the accent column from the state."""


Effect = Truncate | SetPreview | ApplySelection | Navigate | Repaint
Result = tuple[ColumnState, list[Effect]]


@dataclass(frozen=True)
class ColumnPaint:
    """What one column paints: the row its path runs through, and whether its
    rows read as accent. At most one column of a plan has `accent` set."""

    path_uri: str | None
    accent: bool


def paint_plan(
    marks: list[str | None],
    has_selection: list[bool],
    focused: int,
    dnd_hover_index: int | None = None,
) -> list[ColumnPaint]:
    """Paint every column at once, so exactly one column is blue (#189).

    `marks[i]` is the row column i marks as the path (the next column's
    folder, or the previewed file for the last one), `has_selection[i]`
    whether it has a selection. The accent column is the focused one when it
    shows something (a selection or a path mark), else the column leading
    into it (an empty folder just opened keeps the folder row blue). During a
    drag hover-open, columns from the hovered one rightwards drop their mark:
    the dragged selection stays the only blue."""
    if dnd_hover_index is not None:
        marks = [None if i >= dnd_hover_index else m for i, m in enumerate(marks)]
    accent = focused
    if 0 <= focused < len(marks) and not has_selection[focused] and marks[focused] is None:
        if focused > 0:
            accent = focused - 1
    return [ColumnPaint(m, i == accent) for i, m in enumerate(marks)]


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
        # A user-driven move: explicit (empty) selection, keyboard focus restored.
        effects.append(Navigate(state.location, (), focus=True))
    effects.append(Repaint())
    return state, effects
