"""Counted ledger checks (ticket 5): no long or short dash in the repo's prose, and the README suite
count equals what pytest collects. Frozen run records, EVAL.md, and quoted source papers are out of
scope for the dash check because they are never edited."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

DASHES = ("\u2014", "\u2013")
SKIP_DIRS = ("runs/", "pyx/tasks/", ".git/", ".venv/", "node_modules/")
SKIP_FILES = ("EVAL.md",)
_README = re.compile(r"The suite collects (\d+) tests")
_COLLECTED = re.compile(r"^(\d+) tests? collected", re.M)


def prose_files(root: Path) -> List[Path]:
    out = []
    for p in sorted(root.rglob("*.md")):
        rel = p.relative_to(root).as_posix()
        if rel in SKIP_FILES or rel.startswith(SKIP_DIRS) or "/." in f"/{rel}":
            continue
        out.append(p)
    return out


def dash_hits(paths: Iterable[Path]) -> List[Tuple[Path, int]]:
    hits = []
    for p in paths:
        for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), start=1):
            if any(d in line for d in DASHES):
                hits.append((p, n))
    return hits


def readme_count(text: str) -> Optional[int]:
    m = _README.search(text)
    return int(m.group(1)) if m else None


def collected_count(output: str) -> int:
    m = _COLLECTED.search(output)
    if m is None:
        raise ValueError("no 'N tests collected' line in pytest output")
    return int(m.group(1))
