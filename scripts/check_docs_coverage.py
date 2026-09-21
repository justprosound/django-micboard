#!/usr/bin/env python3
# ruff: noqa: T201
"""Assert that every documentation page in ``docs/`` produced a page in the built site.

The check is deliberately behavioural: it reads the "Edit page" link that Starlight renders
on every page, which names the source file the page was built from. A Markdown file that is
missing from that set was silently dropped by the build or excluded from the content
collection, which is the failure mode this guards against.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS_DIR = ROOT / "docs"
SITE_DIR = ROOT / "site"
EDIT_LINK = re.compile(r'href="https://github\.com/justprosound/django-micboard/edit/main/([^"]+)"')

# Pages that exist in the built site without a Markdown source of their own.
GENERATED_PAGES = {"404.html"}


def source_pages() -> set[str]:
    """Return every Markdown page the documentation site is expected to render."""
    pages = set()
    for path in DOCS_DIR.rglob("*.md"):
        relative = path.relative_to(ROOT)
        if any(part.startswith("_") for part in relative.parts):
            continue
        pages.add(relative.as_posix())
    return pages


def built_pages() -> tuple[set[str], int]:
    """Return the source files named by the built site, plus the page count."""
    sources: set[str] = set()
    count = 0
    for path in SITE_DIR.rglob("*.html"):
        if path.relative_to(SITE_DIR).as_posix() in GENERATED_PAGES:
            continue
        count += 1
        match = EDIT_LINK.search(path.read_text(encoding="utf-8"))
        if match:
            sources.add(match.group(1))
    return sources, count


def main() -> int:
    """Compare the documentation sources against the built site."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--report",
        action="store_true",
        help="print every source page and whether the build rendered it",
    )
    arguments = parser.parse_args()

    if not SITE_DIR.is_dir():
        print("site/ does not exist; build the documentation first with: just docs")
        return 1

    expected = source_pages()
    rendered, page_count = built_pages()

    if arguments.report:
        for page in sorted(expected):
            print(f"{'ok     ' if page in rendered else 'MISSING'} {page}")

    missing = sorted(expected - rendered)
    unexpected = sorted(rendered - expected)
    if not missing and not unexpected:
        print(f"{len(expected)} documentation pages rendered into {page_count} HTML pages.")
        return 0

    print("The built documentation site does not cover docs/ exactly:")
    for page in missing:
        print(f"  - missing from the build: {page}")
    for page in unexpected:
        print(f"  - built from a source that no longer exists: {page}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
