import unittest

from nautilus_my_computer import selection as sel
from nautilus_my_computer.selection import Kind, Selection

ORDER = ["a", "b", "c", "d", "e"]


class SelectionRules(unittest.TestCase):
    def test_kind_is_derived(self):
        self.assertIs(Selection().kind, Kind.EMPTY)
        self.assertIs(sel.click(Selection(), "a").kind, Kind.SINGLE)
        self.assertIs(Selection(frozenset("ab")).kind, Kind.MULTI)

    def test_click_selects_only_that_uri(self):
        s = sel.click(Selection(frozenset("ab"), "a"), "c")
        self.assertEqual(s, Selection(frozenset("c"), "c"))

    def test_ctrl_click_toggles(self):
        s = sel.ctrl_click(sel.click(Selection(), "a"), "b")
        self.assertEqual(s.uris, frozenset("ab"))
        self.assertEqual(s.anchor, "b")
        s = sel.ctrl_click(s, "b")
        self.assertIs(s.kind, Kind.SINGLE)
        self.assertEqual(s.uris, frozenset("a"))

    def test_ctrl_click_down_to_none_is_empty(self):
        s = sel.ctrl_click(sel.click(Selection(), "a"), "a")
        self.assertIs(s.kind, Kind.EMPTY)

    def test_shift_click_range_from_anchor(self):
        s = sel.shift_click(sel.click(Selection(), "b"), "d", ORDER)
        self.assertEqual(s.uris, frozenset("bcd"))
        self.assertEqual(s.anchor, "b")

    def test_shift_click_backwards(self):
        s = sel.shift_click(sel.click(Selection(), "d"), "b", ORDER)
        self.assertEqual(s.uris, frozenset("bcd"))

    def test_shift_click_without_anchor_selects_only_clicked(self):
        s = sel.shift_click(Selection(), "c", ORDER)
        self.assertEqual(s, Selection(frozenset("c"), "c"))

    def test_shift_click_extend_without_anchor_keeps_others(self):
        s = sel.shift_click(Selection(frozenset("a")), "c", ORDER, extend=True)
        self.assertEqual(s.uris, frozenset("ac"))

    def test_shift_click_follows_current_order(self):
        s = sel.click(Selection(), "b")
        self.assertEqual(sel.shift_click(s, "d", ["d", "c", "b", "a", "e"]).uris, frozenset("bcd"))
        self.assertEqual(sel.shift_click(s, "d", ["b", "e", "d", "c", "a"]).uris, frozenset("bed"))

    def test_shift_click_extend_keeps_other_rows(self):
        s = sel.ctrl_click(sel.click(Selection(), "a"), "c")
        s = sel.shift_click(s, "e", ORDER, extend=True)
        self.assertEqual(s.uris, frozenset("ace" + "d"))

    def test_select_all(self):
        self.assertEqual(sel.select_all(ORDER).uris, frozenset(ORDER))

    def test_clear_empties_single_and_multi(self):
        self.assertIs(sel.clear(sel.click(Selection(), "a")).kind, Kind.EMPTY)
        self.assertIs(sel.clear(sel.select_all(ORDER)).kind, Kind.EMPTY)

    def test_target_inside_group_keeps_group(self):
        group = Selection(frozenset("ab"), "a")
        self.assertIs(sel.target(group, "b"), group)

    def test_target_outside_group_selects_only_that(self):
        group = Selection(frozenset("ab"), "a")
        self.assertEqual(sel.target(group, "d").uris, frozenset("d"))

    def test_reconcile_drops_vanished_uri_and_anchor(self):
        s = Selection(frozenset("abc"), "c")
        r = sel.reconcile(s, ["a", "b", "d"])
        self.assertEqual(r.uris, frozenset("ab"))
        self.assertIsNone(r.anchor)

    def test_reconcile_survives_pure_sort(self):
        s = Selection(frozenset("ab"), "a")
        self.assertEqual(sel.reconcile(s, list(reversed(ORDER))), s)

    def test_reconcile_against_empty_listing_clears(self):
        self.assertIs(sel.reconcile(Selection(frozenset("a"), "a"), []).kind, Kind.EMPTY)

    def test_ordered_uris_follow_display_order(self):
        s = Selection(frozenset("eb"))
        self.assertEqual(sel.ordered_uris(s, ORDER), ("b", "e"))


class PendingWrite(unittest.TestCase):
    def pending(self, uris):
        p = sel.PendingSelection()
        p.set("folder", uris)
        return p

    def test_complete_match_is_written_once(self):
        p = self.pending("ab")
        self.assertEqual(p.resolve(frozenset("abc"), final=False), frozenset("ab"))
        self.assertFalse(p.active)
        self.assertIsNone(p.resolve(frozenset("abc"), final=True))

    def test_partial_match_is_never_written(self):
        p = self.pending("ab")
        self.assertIsNone(p.resolve(frozenset("a"), final=False))
        self.assertTrue(p.active)
        self.assertIsNone(p.resolve(frozenset("a"), final=True))
        self.assertFalse(p.active)

    def test_partial_then_complete_after_more_rows(self):
        p = self.pending("ab")
        self.assertIsNone(p.resolve(frozenset("a"), final=False))
        self.assertEqual(p.resolve(frozenset("ab"), final=True), frozenset("ab"))

    def test_clear_request_on_empty_folder_resolves(self):
        p = self.pending("")
        self.assertEqual(p.resolve(frozenset(), final=True), frozenset())

    def test_native_selection_right_after_write_is_not_overwritten(self):
        p = self.pending("a")
        p.resolve(frozenset("ab"), final=False)
        # The user then selects natively: nothing is pending any more.
        self.assertIsNone(p.resolve(frozenset("ab"), final=True))

    def test_native_selection_drops_a_waiting_request(self):
        p = self.pending("ab")
        p.resolve(frozenset("a"), final=False)
        p.drop()
        self.assertIsNone(p.resolve(frozenset("ab"), final=True))


class AdoptNative(unittest.TestCase):
    def test_empty_selection_is_adopted(self):
        self.assertTrue(sel.adopt_native(loading=False, writing=False, pending=False))

    def test_loading_is_a_transition_not_a_clear(self):
        self.assertFalse(sel.adopt_native(loading=True, writing=False, pending=False))

    def test_own_write_and_pending_request_are_not_adopted(self):
        self.assertFalse(sel.adopt_native(loading=False, writing=True, pending=False))
        self.assertFalse(sel.adopt_native(loading=False, writing=False, pending=True))


if __name__ == "__main__":
    unittest.main()
