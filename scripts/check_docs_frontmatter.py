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


# The closing fence may be the last line of a file, with no trailing newline.
CLOSING_FENCE = re.compile(r"\n---[ \t]*(?:\n|\Z)")
TITLE_FIELD = re.compile(r"^title:[ \t]*(?P<value>.*?)[ \t]*$", re.MULTILINE)
LEADING_HEADING = re.compile(r"# (?P<title>.+?)[ \t]*(?:\n|\Z)")


def split_frontmatter(content: str) -> tuple[str | None, str]:
    """Return the raw frontmatter block (without fences) and the remaining body."""
    if not content.startswith("---\n"):
        return None, content
    fence = CLOSING_FENCE.search(content, 3)
    if fence is None:
        return None, content
    return content[4 : fence.start()], content[fence.end() :]


def frontmatter_title(frontmatter: str) -> str | None:
    """Return the declared title, unquoting the simple scalars this project uses."""
    match = TITLE_FIELD.search(frontmatter)
    if match is None:
        return None
    value = match.group("value")
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        value = value[1:-1].replace('\\"', '"').replace("\\\\", "\\")
    return value.strip()


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


def build_frontmatter(title: str, existing: str = "") -> str:
    """Return a frontmatter block declaring ``title``, keeping any existing fields."""
    lines = [f"title: {quote(title)}"]
    label = sidebar_label(title)
    if label and not re.search(r"^sidebar:", existing, re.MULTILINE):
        lines += ["sidebar:", f"  label: {quote(label)}"]
    kept = existing.strip("\n")
    if kept:
        lines.append(kept)
    return "---\n" + "\n".join(lines) + "\n---\n"


def repair(content: str) -> tuple[str, str | None]:
    """Return the repaired page content, plus the reason a repair was impossible."""
    frontmatter, body = split_frontmatter(content)
    stripped = body.lstrip("\n")
    heading = LEADING_HEADING.match(stripped)
    declared = frontmatter_title(frontmatter) if frontmatter is not None else None

    if declared is not None:
        if heading is None:
            return content, None
        # Removing a heading that says something else would discard content, so a
        # mismatch is reported for a human to reconcile instead of being rewritten.
        if heading.group("title").strip() != declared:
            return content, (
                f"body heading {heading.group('title').strip()!r} differs from the "
                f"frontmatter title {declared!r}; reconcile them manually"
            )
        return f"---\n{frontmatter}\n---\n" + stripped[heading.end() :].lstrip("\n"), None

    if heading is None:
        return content, "no frontmatter title and no leading '# ' heading to derive one from"

    remainder = stripped[heading.end() :].lstrip("\n")
    title = heading.group("title").strip()
    return build_frontmatter(title, frontmatter or "") + remainder, None


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
            Problem(
                path,
                "body starts with a '# ' heading; the frontmatter title is already "
                "rendered as the page heading",
            )
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
