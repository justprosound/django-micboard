"""Contract tests for the documentation frontmatter check.

Every page under ``docs/`` must declare a frontmatter ``title``. The documentation site
renders that field as the page heading, so a page that also kept its Markdown ``# Heading``
would render the title twice, and a page with no title cannot be rendered at all.
"""

from __future__ import annotations

from scripts.check_docs_frontmatter import iter_docs, problems, repair


def test_every_documentation_page_declares_a_title() -> None:
    """A page without usable frontmatter would break the documentation build."""
    failures = [str(problem) for path in iter_docs() for problem in problems(path)]

    assert failures == []


def test_repair_lifts_the_leading_heading_into_frontmatter() -> None:
    """The heading becomes the title and is removed from the body."""
    repaired, reason = repair("# Quick Start Guide\n\nInstall the app.\n")

    assert reason is None
    assert repaired == '---\ntitle: "Quick Start Guide"\n---\nInstall the app.\n'


def test_repair_shortens_verbose_sred_titles_for_the_sidebar() -> None:
    """Long, repetitive titles get a readable sidebar label instead."""
    repaired, reason = repair("# SRED Project Summary — 2026 Unify Settings Proxy\n\nBody.\n")

    assert reason is None
    assert 'title: "SRED Project Summary — 2026 Unify Settings Proxy"' in repaired
    assert 'label: "Unify Settings Proxy"' in repaired


def test_repair_leaves_pages_that_already_have_a_title_untouched() -> None:
    """Hand-written frontmatter is authoritative and must not be rewritten."""
    content = '---\ntitle: "Kept"\n---\n# Also a heading\n'

    repaired, reason = repair(content)

    assert reason is None
    assert repaired == content


def test_repair_reports_a_page_with_no_heading_to_derive_a_title_from() -> None:
    """The check fails loudly instead of inventing a title."""
    _, reason = repair("Just a paragraph.\n")

    assert reason is not None
    assert "no leading '# ' heading" in reason
