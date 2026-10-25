from __future__ import annotations

import os
import stat
from dataclasses import dataclass
from typing import Callable, Iterator, List, Optional


@dataclass(frozen=True)
class WalkEntry:
    """One directory yielded by `walk`.

    We snapshot the contents of each directory up front instead of delegating to
    `os.scandir` lazily. The reason is purely ordering: a consumer that prunes a
    subtree needs the remaining entries to be in a stable, predictable order, and
    interleaving pruning with a half-consumed generator makes the ordering
    depend on exactly when the consumer decides to stop. By reading the whole
    listing first we guarantee that `dirs` and `files` are fully known before any
    downstream code runs.
    """
    root: str
    dirs: List[str]
    files: List[str]


def walk(
    top: str,
    *,
    prune: Optional[Callable[[str, List[str]], List[str]]] = None,
    follow_symlinks: bool = False,
) -> Iterator[WalkEntry]:
    """Walk `top` depth-first, yielding `WalkEntry` objects.

    Args:
        top: Root directory to walk. Must exist and be a directory.
        prune: Optional callable ``(full_path, dir_names) -> retained_dir_names``.
            Called for every directory before it is recursed into. The returned
            list determines which subdirectories are visited; names that are
            dropped are treated as pruned and never recursed into. Returning an
            empty list prevents descent entirely.
        follow_symlinks: If False (the default) symlinked directories are treated
            as files: they appear in `entry.files` and are never followed. This
            avoids silent cycles and crossing filesystem boundaries. Set True to
            follow symlinks to directories; the caller is responsible for cycle
            safety in that case.

    Yields:
        One `WalkEntry` per visited directory, in pre-order. Within each entry,
        `dirs` and `files` are sorted to give reproducible output independent of
        the filesystem's own ordering.
    """
    if not os.path.isdir(top):
        raise NotADirectoryError(f"{top!r} is not a directory")

    # Non-existent prune function defaults to "keep everything".  A None check
    # here means callers can omit the argument entirely; the more explicit
    # identity-lambda form is discouraged to avoid hiding the default.
    _prune: Callable[[str, List[str]], List[str]] = prune or (lambda _p, d: d)

    stack: List[str] = [top]
    # Visited set guards against symlink cycles when following is enabled.
    # We key on realpath so that two symlinks pointing at the same target are
    # recognised as duplicates rather than separate directories.
    seen: set = set()

    while stack:
        current = stack.pop()

        if follow_symlinks:
            real = os.path.realpath(current)
            if real in seen:
                continue
            seen.add(real)

        try:
            names = os.listdir(current)
        except PermissionError:
            # We cannot read this directory; yield what we know (empty listing)
            # rather than crashing the entire walk. The consumer still sees the
            # directory exists, just that its contents are inaccessible.
            yield WalkEntry(root=current, dirs=[], files=[])
            continue

        dirs: List[str] = []
        files: List[str] = []

        for name in sorted(names, key=lambda s: s.lower()):
            full = os.path.join(current, name)
            try:
                st = os.stat(full, follow_symlinks=follow_symlinks)
            except OSError:
                # Broken symlink, vanished file, or stat failure: treat as a
                # file so the caller sees it exists rather than silently
                # dropping it from the listing.
                files.append(name)
                continue

            if stat.S_ISDIR(st.st_mode):
                dirs.append(name)
            else:
                files.append(name)

        # Pre-order yield: the consumer sees the parent before children, so it
        # can decide prunes with full knowledge of siblings.
        entry = WalkEntry(root=current, dirs=dirs, files=files)
        yield entry

        # Apply prune after yielding so the entry the consumer receives is the
        # unfiltered truth. The pruned list only governs recursion.
        retained = _prune(current, dirs)

        # Push children in reverse sorted order so that popping gives forward
        # sorted order on the stack (depth-first, leftmost-first).
        for name in reversed(retained):
            stack.append(os.path.join(current, name))
