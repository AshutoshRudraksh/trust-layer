"""Fail if README or docs prose uses an em dash or an en dash.

The house rule forbids U+2014 and U+2013 in repo prose. This file is the
enforcement. Scope is README.md and every markdown file under docs/, which is
where that prose lives. Spaced ASCII hyphens are out of scope: skipping list
markers and tables still leaves too many legitimate mid-sentence uses, and
the dash that slipped in was typographic. Fenced code blocks, inline code
spans, and URLs are skipped so a character inside a command or a link does
not fail the test.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EM = "\u2014"
EN = "\u2013"
FIGURE = "\u2012"
HORIZONTAL = "\u2015"
MINUS = "\u2212"
NAMES = {EM: "em dash (U+2014)", EN: "en dash (U+2013)"}
FENCE = re.compile(r"^( {0,3})(`{3,}|~{3,})")
URL = re.compile(r"https?://[^\s<>)'\"]+")
LINK_DEST = re.compile(r"\]\([^)]*\)")


def prose_markdown_files() -> list[Path]:
    return [ROOT / "README.md", *sorted((ROOT / "docs").rglob("*.md"))]


def _mask_code_spans(line: str) -> str:
    out: list[str] = []
    i = 0
    n = len(line)
    while i < n:
        if line[i] == "`":
            run = 1
            while i + run < n and line[i + run] == "`":
                run += 1
            j = i + run
            closer: int | None = None
            while j < n:
                if line[j] == "`":
                    close_run = 1
                    while j + close_run < n and line[j + close_run] == "`":
                        close_run += 1
                    if close_run == run:
                        closer = j + close_run
                        break
                    j += close_run
                else:
                    j += 1
            if closer is not None:
                out.append(" " * (closer - i))
                i = closer
                continue
        out.append(line[i])
        i += 1
    return "".join(out)


def _mask_skipped(line: str) -> str:
    masked = _mask_code_spans(line)
    masked = LINK_DEST.sub(lambda m: "]" + " " * (len(m.group(0)) - 1), masked)
    return URL.sub(lambda m: " " * len(m.group(0)), masked)


def typographic_dash_hits(path: Path, *, root: Path | None = None) -> list[str]:
    text = path.read_text(encoding="utf-8")
    try:
        label = path.resolve().relative_to((root or path.parent).resolve()).as_posix()
    except ValueError:
        label = path.name
    hits: list[str] = []
    in_fence = False
    fence_char = ""
    fence_len = 0
    fence_open_line = 0
    for lineno, line in enumerate(text.splitlines(), 1):
        match = FENCE.match(line)
        if match:
            mark = match.group(2)
            char, length = mark[0], len(mark)
            if not in_fence:
                in_fence = True
                fence_char, fence_len = char, length
                fence_open_line = lineno
                continue
            rest = line[match.end():]
            if (
                char == fence_char
                and length >= fence_len
                and all(c in " \t" for c in rest)
            ):
                in_fence = False
                fence_char, fence_len, fence_open_line = "", 0, 0
                continue
        if in_fence:
            continue
        for char in _mask_skipped(line):
            name = NAMES.get(char)
            if name is not None:
                hits.append(f"{label}:{lineno}: {name}")
    if in_fence:
        hits.append(f"{label}:{fence_open_line}: unclosed fenced code block")
    return hits


def test_scanner_reports_em_and_en_dashes_with_file_line_and_character(tmp_path: Path) -> None:
    path = tmp_path / "sample.md"
    path.write_text(f"plain\nhello {EM} world\nmid {EN} dash\n", encoding="utf-8")
    assert typographic_dash_hits(path) == [
        f"sample.md:2: {NAMES[EM]}",
        f"sample.md:3: {NAMES[EN]}",
    ]


def test_scanner_ignores_dashes_in_code_spans_urls_and_fenced_blocks(tmp_path: Path) -> None:
    path = tmp_path / "sample.md"
    path.write_text(
        "\n".join(
            [
                f"see `{EM}code` and `` a{EN}b ``",
                f"link https://example.com/foo{EM}bar and [x](https://example.com/a{EN}b)",
                "```",
                f"code {EM} here",
                "```",
                "~~~info",
                f"more {EN} here",
                "~~~",
                "ok",
                "",
            ]
        ),
        encoding="utf-8",
    )
    assert typographic_dash_hits(path) == []


def test_readme_and_docs_contain_no_typographic_dashes() -> None:
    found: list[str] = []
    for path in prose_markdown_files():
        found.extend(typographic_dash_hits(path, root=ROOT))
    assert found == [], "typographic dashes in prose:\n" + "\n".join(found)


def test_scanner_reports_unclosed_fence(tmp_path: Path) -> None:
    path = tmp_path / "sample.md"
    path.write_text(
        "\n".join(
            [
                "```",
                f"code {EM} here",
                "still open",
                "",
            ]
        ),
        encoding="utf-8",
    )
    assert typographic_dash_hits(path) == [
        "sample.md:1: unclosed fenced code block",
    ]


def test_closing_fence_with_trailing_text_does_not_close(tmp_path: Path) -> None:
    path = tmp_path / "sample.md"
    path.write_text(
        "\n".join(
            [
                "```",
                "code",
                "``` trailing",
                f"prose {EM} still in the fence",
                "",
            ]
        ),
        encoding="utf-8",
    )
    assert typographic_dash_hits(path) == [
        "sample.md:1: unclosed fenced code block",
    ]


def test_closing_fence_may_have_trailing_whitespace(tmp_path: Path) -> None:
    path = tmp_path / "sample.md"
    path.write_text("```\ncode\n```  \nprose\n", encoding="utf-8")
    assert typographic_dash_hits(path) == []


def test_scanner_reports_figure_dash_horizontal_bar_and_minus_sign(tmp_path: Path) -> None:
    path = tmp_path / "sample.md"
    path.write_text(
        f"a {FIGURE} b\nc {HORIZONTAL} d\ne {MINUS} f\n",
        encoding="utf-8",
    )
    assert typographic_dash_hits(path) == [
        "sample.md:1: figure dash (U+2012)",
        "sample.md:2: horizontal bar (U+2015)",
        "sample.md:3: minus sign (U+2212)",
    ]
