#!/usr/bin/env python3
# ruff: noqa: T201
"""Verify (or repair) the Starlight frontmatter required by every documentation page.

Starlight renders the ``title`` frontmatter field as the page heading, so a page that
keeps its Markdown ``# Heading`` would render two level-one headings. This check keeps
``docs/`` authored as plain Markdown while guaranteeing the small amount of frontmatter
the documentation site needs.
"""

from __future__ import annotations

import argparse
import re
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS_DIR = ROOT / "docs"

# Sidebar labels are derived from the page title so long, repetitive titles stay
# readable in the navigation without hand-maintaining a label per page.
LABEL_PREFIXES = ("SRED Project Summary — 2026 ", "SRED Project Index — ")


@dataclass(frozen=True)
class Problem:
    """A single frontmatter defect found in a documentation page."""

    path: Path
    message: str

    def __str__(self) -> str:
        return f"{self.path.relative_to(ROOT)}: {self.message}"


def iter_docs() -> Iterator[Path]:
    """Yield every Markdown page that the documentation site renders."""
    for path in sorted(DOCS_DIR.rglob("*.md")):
        if any(part.startswith("_") for part in path.relative_to(DOCS_DIR).parts):
            continue
        yield path


def split_frontmatter(content: str) -> tuple[str | None, str]:
    """Return the raw frontmatter block (without fences) and the remaining body."""
    if not content.startswith("---\n"):
        return None, content
    end = content.find("\n---\n", 3)
    if end == -1:
        return None, content
    return content[4:end], content[end + 5 :]


def quote(value: str) -> str:
    """Return a double-quoted YAML scalar safe for titles containing colons or dashes."""
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def sidebar_label(title: str) -> str | None:
    """Return a shortened sidebar label for verbose, prefixed page titles."""
    for prefix in LABEL_PREFIXES:
        if title.startswith(prefix):
            return title.removeprefix(prefix).strip()
    return None


def build_frontmatter(title: str) -> str:
    """Return the frontmatter block for a page with the given title."""
    lines = ["---", f"title: {quote(title)}"]
    label = sidebar_label(title)
    if label:
        lines += ["sidebar:", f"  label: {quote(label)}"]
    lines += ["---", ""]
    return "\n".join(lines)


def repair(content: str) -> tuple[str, str | None]:
    """Return the repaired page content, plus the reason a repair was impossible."""
    frontmatter, body = split_frontmatter(content)
    if frontmatter is not None and re.search(r"^title:", frontmatter, re.MULTILINE):
        return content, None

    stripped = body.lstrip("\n")
    match = re.match(r"# (?P<title>.+?)[ \t]*\n", stripped)
    if match is None:
        return content, "no frontmatter title and no leading '# ' heading to derive one from"

    remainder = stripped[match.end() :].lstrip("\n")
    return build_frontmatter(match.group("title").strip()) + remainder, None


def problems(path: Path) -> list[Problem]:
    """Return the frontmatter defects for a single page."""
    content = path.read_text(encoding="utf-8")
    frontmatter, body = split_frontmatter(content)
    if frontmatter is None:
        return [Problem(path, "missing YAML frontmatter with a 'title' field")]
    if not re.search(r"^title:", frontmatter, re.MULTILINE):
        return [Problem(path, "frontmatter does not define 'title'")]
    if re.match(r"\n*# ", body):
        return [
            Problem(path, "body starts with a '# ' heading that duplicates the frontmatter title")
        ]
    return []


def main() -> int:
    """Report, or with ``--fix`` repair, documentation frontmatter defects."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fix", action="store_true", help="rewrite pages in place")
    arguments = parser.parse_args()

    failures: list[Problem] = []
    fixed: list[Path] = []
    for path in iter_docs():
        if arguments.fix:
            content = path.read_text(encoding="utf-8")
            repaired, reason = repair(content)
            if reason is not None:
                failures.append(Problem(path, reason))
                continue
            if repaired != content:
                path.write_text(repaired, encoding="utf-8")
                fixed.append(path)
        failures.extend(problems(path))

    for path in fixed:
        print(f"fixed {path.relative_to(ROOT)}")
    if not failures:
        return 0

    print("Documentation frontmatter is invalid; run: just docs-frontmatter")
    for failure in failures:
        print(f"  - {failure}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
