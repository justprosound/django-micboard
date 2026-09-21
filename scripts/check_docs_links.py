#!/usr/bin/env python3
# ruff: noqa: T201
"""Verify every internal link, anchor, and asset reference in the built documentation site.

Running against the built HTML (rather than the Markdown sources) catches the regressions
that matter after a file move or rename: links that no longer resolve to a page, assets that
were never copied, and fragments that point at headings which no longer exist. External URLs
are not requested, so the check is hermetic and safe to run offline in CI.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SITE_DIR = ROOT / "site"
ASTRO_CONFIG = ROOT / "astro.config.mjs"
EXTERNAL_SCHEME = re.compile(r"^(?:[a-z][a-z0-9+.-]*:|//)", re.IGNORECASE)
LINK_ATTRIBUTES = {"href", "src"}


class PageParser(HTMLParser):
    """Collect referenced URLs and the fragment identifiers a page defines."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.references: list[str] = []
        self.identifiers: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = {name: value for name, value in attrs if value is not None}
        for attribute in LINK_ATTRIBUTES:
            value = attributes.get(attribute)
            if value:
                self.references.append(value)
        for attribute in ("id", "name"):
            value = attributes.get(attribute)
            if value:
                self.identifiers.add(value)


def site_base() -> str:
    """Return the configured site base path, the single source of truth for URLs."""
    match = re.search(r'^const base = "([^"]*)";', ASTRO_CONFIG.read_text(), re.MULTILINE)
    if match is None:
        raise ValueError("could not read the `base` constant from astro.config.mjs")
    return match.group(1).rstrip("/")


def resolve(reference: str, *, page: Path, base: str) -> Path | None:
    """Return the file a reference points at, or None when it cannot be mapped."""
    path = reference.split("?", 1)[0]
    if path.startswith("/"):
        if base and not (path == base or path.startswith(f"{base}/")):
            return None
        path = path[len(base) :] or "/"
        target = SITE_DIR / path.lstrip("/")
    else:
        target = (page.parent / path).resolve()

    if target.is_dir():
        return target / "index.html"
    if target.suffix:
        return target
    candidate = target.with_suffix(".html")
    return candidate if candidate.exists() else target / "index.html"


def check_page(page: Path, base: str) -> list[str]:
    """Return the broken references found on a single built page."""
    parser = PageParser()
    parser.feed(page.read_text(encoding="utf-8"))
    relative_page = page.relative_to(SITE_DIR).as_posix()
    failures: list[str] = []

    for reference in parser.references:
        if not reference or EXTERNAL_SCHEME.match(reference) or reference.startswith("data:"):
            continue
        url, _, fragment = reference.partition("#")
        if not url:
            if fragment and fragment not in parser.identifiers:
                failures.append(f"{relative_page}: fragment #{fragment} has no target on the page")
            continue

        target = resolve(url, page=page, base=base)
        if target is None:
            failures.append(f"{relative_page}: {url} is outside the configured base path")
            continue
        if not target.exists():
            failures.append(f"{relative_page}: {url} does not resolve to a built file")
            continue
        if fragment and target.suffix == ".html":
            target_parser = PageParser()
            target_parser.feed(target.read_text(encoding="utf-8"))
            if fragment not in target_parser.identifiers:
                failures.append(f"{relative_page}: {url}#{fragment} has no matching target")
    return failures


def main() -> int:
    """Validate every built page and report each broken reference."""
    if not SITE_DIR.is_dir():
        print("site/ does not exist; build the documentation first with: just docs")
        return 1

    base = site_base()
    failures: list[str] = []
    pages = sorted(SITE_DIR.rglob("*.html"))
    for page in pages:
        failures.extend(check_page(page, base))

    if not failures:
        print(f"All internal references in {len(pages)} built pages resolve.")
        return 0

    print(f"Found {len(failures)} broken reference(s) in the built documentation:")
    for failure in failures:
        print(f"  - {failure}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
