import unittest

from nautilus_my_computer import column_state as cs
from nautilus_my_computer.column_state import (
    ApplySelection,
    ColumnState,
    Navigate,
    SetPreview,
    Truncate,
)

A, B, C = "file:///a", "file:///a/b", "file:///a/b/c"


def chain(*path, active=None, **kw):
    return ColumnState(path=tuple(path), active=len(path) - 1 if active is None else active, **kw)


def navs(effects):
    return [e for e in effects if isinstance(e, Navigate)]


class Invariants(unittest.TestCase):
    """The rules that kept regressing; one named test each."""

    def test_background_click_clears_selection_and_ends_path(self):
        state, fx = cs.click_background(chain(A, B, C, selection=(C + "/f",)), 0)
        self.assertEqual(state.path, (A,))
        self.assertEqual(state.selection, ())
        self.assertEqual(state.active, 0)
        self.assertEqual(state.location, A)
        self.assertIn(Truncate(0), fx)
        self.assertIn(ApplySelection(0, ()), fx)

    def test_background_click_on_deepest_only_clears(self):
        state, fx = cs.click_background(chain(A, B, selection=(B + "/f",)), 1)
        self.assertEqual(state.path, (A, B))
        self.assertEqual(state.selection, ())
        self.assertEqual(navs(fx), [])

    def test_background_click_navigates_to_where_the_path_ends(self):
        state, fx = cs.click_background(chain(A, B, C), 0)
        self.assertEqual(navs(fx), [Navigate(A, (), True)])
        self.assertEqual(navs(fx)[-1].uri, state.location)
        self.assertIn(SetPreview(None), fx)


class PaintPlan(unittest.TestCase):
    """Exactly one column reads as accent (#189 follow-up)."""

    def accents(self, plan):
        return [i for i, p in enumerate(plan) if p.accent]

    def test_focused_column_with_selection_is_the_only_accent(self):
        plan = cs.paint_plan([B, C, None], [False, False, True], focused=2)
        self.assertEqual(self.accents(plan), [2])
        self.assertEqual([p.path_uri for p in plan], [B, C, None])

    def test_empty_focused_column_hands_accent_to_its_lead_in(self):
        plan = cs.paint_plan([B, None], [False, False], focused=1)
        self.assertEqual(self.accents(plan), [0])

    def test_focused_column_with_only_a_mark_keeps_the_accent(self):
        # Background click keeps the chain: one blue column, not two.
        plan = cs.paint_plan([B, C, None], [False, False, False], focused=1)
        self.assertEqual(self.accents(plan), [1])

    def test_empty_first_column_keeps_the_accent(self):
        self.assertEqual(self.accents(cs.paint_plan([None], [False], focused=0)), [0])

    def test_drag_hover_drops_marks_from_the_hovered_column(self):
        plan = cs.paint_plan([B, C, None], [True, False, False], focused=0, dnd_hover_index=1)
        self.assertEqual([p.path_uri for p in plan], [B, None, None])
        self.assertEqual(self.accents(plan), [0])

    def test_no_columns(self):
        self.assertEqual(cs.paint_plan([], [], focused=0), [])


if __name__ == "__main__":
    unittest.main()
