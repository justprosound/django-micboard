"""Contract tests for the generated Python API reference in the documentation site.

The documentation build no longer extracts docstrings at render time, so these tests are
what keep the committed reference honest: the pages must be regenerated when the documented
modules change, they must still cover the public surface, and they must still carry the
Google-style docstring sections and source links the previous ``mkdocstrings`` pages had.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.generate_api_docs import OUTPUT_DIR, PAGES, load_package, render_page

ROOT = Path(__file__).resolve().parents[1]
DOCS_DIR = ROOT / "docs"
SOURCE_LINK = re.compile(
    r"\[Source\]\(https://github\.com/justprosound/django-micboard/blob/main/micboard/[^)]+#L\d+\)"
)
DOCUMENTED_SYMBOLS = (
    ("models", "WirelessChassis"),
    ("models", "WirelessUnit"),
    ("models", "RFChannel"),
    ("services", "HardwareLifecycleManager"),
    ("services", "PerformerAssignmentService"),
    ("services", "PluginRegistry"),
    ("management-commands", "Command"),
    ("websocket-consumers", "MicboardConsumer"),
    ("exceptions", "MicboardError"),
)


@pytest.mark.parametrize("page", PAGES, ids=lambda page: page.slug)
def test_generated_reference_matches_the_source_tree(page) -> None:
    """Committed reference pages must match what the extractor produces today."""
    expected = render_page(page, load_package())

    destination = OUTPUT_DIR / f"{page.slug}.md"
    assert destination.exists(), f"{destination} is missing; run: just docs-api"
    assert destination.read_text(encoding="utf-8") == expected, (
        f"{destination} is stale; regenerate it with: just docs-api"
    )


@pytest.mark.parametrize(("slug", "symbol"), DOCUMENTED_SYMBOLS)
def test_public_symbols_appear_in_the_reference(slug: str, symbol: str) -> None:
    """The curated public surface stays documented as the code moves around."""
    content = (OUTPUT_DIR / f"{slug}.md").read_text(encoding="utf-8")

    assert f"`{symbol}`" in content


def test_google_docstring_sections_are_rendered() -> None:
    """Args, Returns, and Raises sections must survive extraction."""
    content = (OUTPUT_DIR / "services.md").read_text(encoding="utf-8")

    assert "**Parameters:**" in content
    assert "**Returns:**" in content
    assert "**Raises:**" in content


def test_reference_pages_link_to_source_lines() -> None:
    """Every page keeps deep links into the source, as the autodoc pages did."""
    for page in PAGES:
        content = (OUTPUT_DIR / f"{page.slug}.md").read_text(encoding="utf-8")

        assert SOURCE_LINK.search(content), f"{page.slug}.md has no source links"


def test_no_autodoc_directives_remain() -> None:
    """A stray `::: module` block would silently render as text after the migration."""
    offenders = [
        path.relative_to(DOCS_DIR).as_posix()
        for path in DOCS_DIR.rglob("*.md")
        if re.search(r"^::: ", path.read_text(encoding="utf-8"), re.MULTILINE)
    ]

    assert offenders == []


def test_reference_generation_needs_no_django_settings() -> None:
    """The extractor reads source statically, so the docs build stays hermetic."""
    environment = {
        key: value for key, value in os.environ.items() if key != "DJANGO_SETTINGS_MODULE"
    }
    result = subprocess.run(
        [sys.executable, "scripts/generate_api_docs.py", "--check"],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
