import unittest

from nautilus_my_computer import uris


class Normalize(unittest.TestCase):
    def test_drops_trailing_slashes(self):
        self.assertEqual(uris.normalize("file:///home/a/"), "file:///home/a")
        self.assertEqual(uris.normalize("file:///home/a//"), "file:///home/a")

    def test_leaves_plain_uri_alone(self):
        self.assertEqual(uris.normalize("file:///home/a"), "file:///home/a")
        self.assertEqual(uris.normalize("recent:"), "recent:")

    def test_keeps_scheme_root(self):
        self.assertEqual(uris.normalize("file:///"), "file:///")
        self.assertEqual(uris.normalize("trash:///"), "trash:///")

    def test_other_schemes(self):
        self.assertEqual(uris.normalize("smb://host/share/"), "smb://host/share")


class SameUri(unittest.TestCase):
    def test_trailing_slash_is_ignored(self):
        self.assertTrue(uris.same_uri("file:///a/", "file:///a"))

    def test_different_locations(self):
        self.assertFalse(uris.same_uri("file:///a", "file:///b"))

    def test_root_is_not_a_bare_scheme(self):
        self.assertTrue(uris.same_uri("file:///", "file:///"))
        self.assertFalse(uris.same_uri("file:///", "file:"))


class IsWithin(unittest.TestCase):
    def test_child_and_grandchild(self):
        self.assertTrue(uris.is_within("file:///a/b", "file:///a"))
        self.assertTrue(uris.is_within("file:///a/b/c", "file:///a/"))

    def test_self_is_not_within(self):
        self.assertFalse(uris.is_within("file:///a/", "file:///a"))

    def test_sibling_name_prefix(self):
        self.assertFalse(uris.is_within("file:///a/foo", "file:///a/fo"))

    def test_root(self):
        self.assertTrue(uris.is_within("file:///a", "file:///"))
        self.assertFalse(uris.is_within("file:///", "file:///"))

    def test_other_scheme(self):
        self.assertFalse(uris.is_within("trash:///a", "file:///"))


class Rebase(unittest.TestCase):
    def test_self_becomes_new(self):
        self.assertEqual(
            uris.rebase("file:///a/old", "file:///a/old", "file:///a/new"), "file:///a/new"
        )

    def test_descendant_keeps_relative_path(self):
        self.assertEqual(
            uris.rebase("file:///a/old/b/c", "file:///a/old/", "file:///a/new"),
            "file:///a/new/b/c",
        )

    def test_unrelated_is_unchanged(self):
        self.assertEqual(
            uris.rebase("file:///a/oldx", "file:///a/old", "file:///a/new"), "file:///a/oldx"
        )

    def test_from_root(self):
        self.assertEqual(uris.rebase("file:///a", "file:///", "file:///mnt/"), "file:///mnt/a")


class Parent(unittest.TestCase):
    def test_nested(self):
        self.assertEqual(uris.parent("file:///a/b/"), "file:///a")

    def test_top_level_goes_to_root(self):
        self.assertEqual(uris.parent("file:///a"), "file:///")

    def test_roots_have_no_parent(self):
        self.assertIsNone(uris.parent("file:///"))
        self.assertIsNone(uris.parent("smb://host"))
        self.assertIsNone(uris.parent("recent:"))

    def test_network_share(self):
        self.assertEqual(uris.parent("smb://host/share"), "smb://host")
