import unittest

from nautilus_my_computer import column_state as cs
from nautilus_my_computer.column_state import (
    Append,
    ApplySelection,
    ColumnState,
    Focus,
    Navigate,
    Reroot,
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

    def test_every_user_navigation_restores_focus_and_names_selection(self):
        s = chain(A, B, C)
        results = [
            cs.click_background(s, 0),
            cs.click_row(s, 0, B, True),
            cs.click_row(s, 0, A + "/file.txt", False),
            cs.click_row(chain(A), 0, B, True),
            cs.multi_select(s, 0, (A + "/x", A + "/y")),
        ]
        for _, fx in results:
            for nav in navs(fx):
                self.assertTrue(nav.focus)
                self.assertIsInstance(nav.select, tuple)

    def test_location_is_what_navigate_sent(self):
        for state, fx in [
            cs.click_background(chain(A, B, C), 0),
            cs.click_row(chain(A, B), 0, A + "/d", True),
            cs.click_row(chain(A, B, C), 1, B + "/file", False),
        ]:
            self.assertEqual(navs(fx)[-1].uri, state.location)

    def test_only_active_column_has_a_selection(self):
        state, _ = cs.click_row(chain(A, B), 0, B, True)
        self.assertEqual(state.active, 0)
        self.assertEqual(state.selection, (B,))
        self.assertEqual(state.path_mark(0), B)

    def test_file_click_in_ancestor_truncates_previews_and_navigates(self):
        file = A + "/file.txt"
        state, fx = cs.click_row(chain(A, B, C), 0, file, False)
        self.assertEqual(state.path, (A,))
        self.assertEqual(state.preview, file)
        self.assertIn(Truncate(0), fx)
        self.assertIn(SetPreview(file), fx)
        # The file stays selected instead of Nautilus selecting B.
        self.assertEqual(navs(fx), [Navigate(A, (file,), True)])

    def test_file_click_in_deepest_column_does_not_navigate(self):
        state, fx = cs.click_row(chain(A, B), 1, B + "/f", False)
        self.assertEqual(navs(fx), [])
        self.assertEqual(state.preview, B + "/f")

    def test_echo_of_our_navigate_changes_nothing_but_focus(self):
        state, fx = cs.click_background(chain(A, B), 0)
        state, fx = cs.location_changed(state, A + "/")
        self.assertEqual(fx, [Focus(0)])
        self.assertIsNone(state.pending_echo)

    def test_echo_without_pending_navigate_has_no_effect(self):
        self.assertEqual(cs.location_changed(chain(A, B), B)[1], [])

    def test_superseded_echo_is_forgotten(self):
        state, _ = cs.click_background(chain(A, B), 0)
        state, _ = cs.location_changed(state, "file:///elsewhere")
        self.assertIsNone(state.pending_echo)


class Clicks(unittest.TestCase):
    def test_folder_click_opens_a_column(self):
        state, fx = cs.click_row(chain(A), 0, B, True)
        self.assertEqual(state.path, (A, B))
        self.assertEqual(fx[0], Append(B))

    def test_folder_click_replaces_deeper_chain(self):
        state, fx = cs.click_row(chain(A, B, C), 0, A + "/d", True)
        self.assertEqual(state.path, (A, A + "/d"))
        self.assertEqual(fx[:2], [Truncate(0), Append(A + "/d")])

    def test_reclicking_open_folder_keeps_its_column(self):
        state, fx = cs.click_row(chain(A, B, C), 0, B, True)
        self.assertEqual(state.path, (A, B))
        self.assertEqual(fx[0], Truncate(1))
        self.assertNotIn(Append(B), fx)

    def test_multi_select_closes_deeper_columns(self):
        picks = (A + "/x", A + "/y")
        state, fx = cs.multi_select(chain(A, B), 0, picks)
        self.assertEqual(state.path, (A,))
        self.assertEqual(state.selection, picks)
        self.assertIn(SetPreview(None, picks), fx)


class Keys(unittest.TestCase):
    def test_left_selects_the_folder_we_came_from(self):
        state, fx = cs.key_left(chain(A, B))
        self.assertEqual((state.active, state.selection), (0, (B,)))
        self.assertIn(Focus(0), fx)

    def test_left_at_first_column_is_a_noop(self):
        self.assertEqual(cs.key_left(chain(A, active=0))[1], [])

    def test_right_promotes_path_mark_to_selection(self):
        state, _ = cs.key_right(chain(A, B, C, active=0))
        self.assertEqual((state.active, state.selection), (1, (C,)))

    def test_right_at_last_column_is_a_noop(self):
        self.assertEqual(cs.key_right(chain(A, B))[1], [])


class LocationChanged(unittest.TestCase):
    def test_ancestor_truncates(self):
        state, fx = cs.location_changed(chain(A, B, C), A)
        self.assertEqual(state.path, (A,))
        self.assertIn(Truncate(0), fx)

    def test_child_of_open_column_extends_the_chain(self):
        state, fx = cs.location_changed(chain(A, B), A + "/d")
        self.assertEqual(state.path, (A, A + "/d"))
        self.assertIn(Truncate(0), fx)
        self.assertIn(Append(A + "/d"), fx)

    def test_unrelated_location_reroots(self):
        state, fx = cs.location_changed(chain(A, B), "file:///other")
        self.assertEqual(state.path, ("file:///other",))
        self.assertEqual(fx, [Reroot("file:///other")])

    def test_root_does_not_swallow_every_location(self):
        state, fx = cs.location_changed(chain("file:///"), "file:///x/y")
        self.assertEqual(fx, [Reroot("file:///x/y")])


class Adopt(unittest.TestCase):
    def test_native_selection_lands_in_deepest_column(self):
        state, fx = cs.native_selection_changed(chain(A, B, active=0), (B + "/f",))
        self.assertEqual((state.active, state.selection), (1, (B + "/f",)))
        self.assertIn(ApplySelection(1, (B + "/f",)), fx)

    def test_same_selection_is_a_noop(self):
        s = chain(A, selection=(A + "/f",))
        self.assertEqual(cs.native_selection_changed(s, (A + "/f",))[1], [])


class Rename(unittest.TestCase):
    def test_open_columns_follow_the_rename(self):
        state, _ = cs.renamed(chain(A, B, C), B, "file:///a/z")
        self.assertEqual(state.path, (A, "file:///a/z", "file:///a/z/c"))

    def test_unrelated_rename_is_a_noop(self):
        self.assertEqual(cs.renamed(chain(A, B), "file:///q", "file:///r")[1], [])


if __name__ == "__main__":
    unittest.main()
