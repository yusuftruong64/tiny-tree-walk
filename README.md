# tiny-tree-walk

Walk directory trees depth-first with prune rules and stable ordering.

```python
import os
import tempfile

from tiny_tree_walk import walk, WalkEntry

tmp = tempfile.mkdtemp()
os.makedirs(os.path.join(tmp, "subdir"))
with open(os.path.join(tmp, "a.txt"), "w"):
    pass

for entry in walk(tmp):
    print(entry.root, entry.dirs, entry.files)

# Prune any directory whose name starts with "."
def prune(path, dirs):
    return [d for d in dirs if not d.startswith(".")]

for entry in walk(tmp, prune=prune):
    print(entry.root, entry.files)
```

## Why

`os.walk` yields tuples, mutates its `dirs` list in place to communicate prunes,
and makes ordering depend on the filesystem. That works, but the in-place
mutation is easy to get wrong and the implicit contract is hard to test.

This library instead returns immutable `WalkEntry` values and takes an explicit
`prune` callable that returns the list of subdirectories to keep. The full
listing is always present on the entry so a consumer can see what was pruned.

The trade-off: every directory's full listing is read into memory before the
entry is yielded. For trees with millions of files in a single directory this is
wasteful. The bet is that prune-driven walks benefit more from a stable,
complete snapshot than from lazy streaming.

## Edge cases

- Sorting is case-insensitive (`str.lower`), so `Banana.txt` sorts between
  `apple.txt` and `Cherry.txt`. If you need byte-order sorting, post-process the
  lists yourself.
- Symlinks to directories are treated as files by default (`follow_symlinks=False`),
  which avoids silent cycles and filesystem-boundary crossings. Enable following
  at your own risk; cycle detection uses `realpath`.
- Broken symlinks and entries that fail `stat` are listed as files rather than
  dropped, so the caller can see they exist.
- Directories that raise `PermissionError` on `listdir` are yielded with empty
  listings instead of aborting the walk.
- The `prune` callable receives `(full_path, dir_names)` and returns the
  retained names. The entry's `dirs` list is the unfiltered truth; pruning only
  affects which children are recursed into.

## Design notes

The window stores values eagerly rather than keeping running aggregates. Running
sums drift with floating point over long streams, and recomputing from a small
buffer is cheap enough that the drift is not worth the speed.

## Performance

The window keeps a bounded buffer, so `push` is constant time and memory does not
grow with the length of the stream. `peak` and `trough` are linear in the window
size, which is the trade that keeps `push` cheap.

