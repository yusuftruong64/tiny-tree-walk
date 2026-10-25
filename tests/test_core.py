import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from tiny_tree_walk import walk, WalkEntry


class TestWalk(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="tiny-tree-walk-")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _mkdir(self, *parts):
        p = os.path.join(self.tmp, *parts)
        os.makedirs(p, exist_ok=True)
        return p

    def _touch(self, *parts):
        p = os.path.join(self.tmp, *parts)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w"):
            pass
        return p

    def test_single_dir_with_files(self):
        self._touch("root", "a.txt")
        self._touch("root", "b.txt")

        entries = list(walk(os.path.join(self.tmp, "root")))
        self.assertEqual(len(entries), 1)
        e = entries[0]
        self.assertEqual(e.dirs, [])
        self.assertEqual(e.files, ["a.txt", "b.txt"])

    def test_nested_dirs_preorder(self):
        self._mkdir("a", "b", "c")
        self._touch("a", "b", "c", "f.txt")
        self._touch("a", "x.txt")

        entries = list(walk(os.path.join(self.tmp, "a")))
        self.assertEqual(len(entries), 3)
        self.assertEqual(entries[0].dirs, ["b"])
        self.assertEqual(entries[0].files, ["x.txt"])
        self.assertEqual(entries[1].dirs, ["c"])
        self.assertEqual(entries[1].files, [])
        self.assertEqual(entries[2].dirs, [])
        self.assertEqual(entries[2].files, ["f.txt"])

    def test_stable_case_insensitive_sort(self):
        self._mkdir("root")
        self._touch("root", "Banana.txt")
        self._touch("root", "apple.txt")
        self._touch("root", "Cherry.txt")

        entries = list(walk(os.path.join(self.tmp, "root")))
        files = entries[0].files
        # Lowercase-first ordering: apple, Banana, Cherry.
        self.assertEqual(files, ["apple.txt", "Banana.txt", "Cherry.txt"])

    def test_prune_subtree(self):
        self._mkdir("root", "keep", "skip")
        self._mkdir("root", "skip", "deep")
        self._touch("root", "keep", "k.txt")
        self._touch("root", "skip", "s.txt")
        self._touch("root", "skip", "deep", "d.txt")

        def prune(path, dirs):
            return [d for d in dirs if d != "skip"]

        entries = list(walk(os.path.join(self.tmp, "root"), prune=prune))
        roots = [e.root for e in entries]
        self.assertIn(os.path.join(self.tmp, "root", "keep"), roots)
        self.assertNotIn(os.path.join(self.tmp, "root", "skip"), roots)
        self.assertEqual(len(entries), 2)

    def test_prune_all_children(self):
        self._mkdir("root", "a", "b")
        self._touch("root", "a", "1.txt")
        self._touch("root", "b", "2.txt")

        def prune(path, dirs):
            return []

        entries = list(walk(os.path.join(self.tmp, "root"), prune=prune))
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].dirs, ["a", "b"])

    def test_entry_retains_pruned_dirs_in_listing(self):
        self._mkdir("root", "skip")
        self._touch("root", "skip", "f.txt")

        def prune(path, dirs):
            return []

        entries = list(walk(os.path.join(self.tmp, "root"), prune=prune))
        # The entry still lists the pruned dir; it just wasn't visited.
        self.assertEqual(entries[0].dirs, ["skip"])

    def test_nonexistent_root_raises(self):
        with self.assertRaises(NotADirectoryError):
            list(walk(os.path.join(self.tmp, "does-not-exist")))

    def test_symlinked_dir_treated_as_file_by_default(self):
        if os.name == "nt":
            self.skipTest("symlink semantics differ on Windows")
        self._mkdir("real_dir")
        self._touch("real_dir", "inner.txt")
        self._mkdir("root")
        os.symlink(
            os.path.join(self.tmp, "real_dir"),
            os.path.join(self.tmp, "root", "link"),
        )

        entries = list(walk(os.path.join(self.tmp, "root")))
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].dirs, [])
        self.assertEqual(entries[0].files, ["link"])

    def test_follow_symlinks_descends(self):
        if os.name == "nt":
            self.skipTest("symlink semantics differ on Windows")
        self._mkdir("real_dir")
        self._touch("real_dir", "inner.txt")
        self._mkdir("root")
        os.symlink(
            os.path.join(self.tmp, "real_dir"),
            os.path.join(self.tmp, "root", "link"),
        )

        entries = list(
            walk(os.path.join(self.tmp, "root"), follow_symlinks=True)
        )
        # root, then the linked dir.
        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[0].dirs, ["link"])
        self.assertEqual(entries[1].files, ["inner.txt"])

    def test_empty_directory(self):
        self._mkdir("empty")
        entries = list(walk(os.path.join(self.tmp, "empty")))
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].dirs, [])
        self.assertEqual(entries[0].files, [])

    def test_broken_symlink_listed_as_file(self):
        if os.name == "nt":
            self.skipTest("symlink semantics differ on Windows")
        self._mkdir("root")
        os.symlink(
            os.path.join(self.tmp, "nowhere"),
            os.path.join(self.tmp, "root", "dangling"),
        )
        self._touch("root", "real.txt")

        entries = list(walk(os.path.join(self.tmp, "root")))
        self.assertEqual(entries[0].files, ["dangling", "real.txt"])
        self.assertEqual(entries[0].dirs, [])

    def test_root_must_be_directory_not_file(self):
        f = self._touch("plain.txt")
        with self.assertRaises(NotADirectoryError):
            list(walk(f))


if __name__ == "__main__":
    unittest.main()
