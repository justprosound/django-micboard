"""Contract tests for the documentation frontmatter check.

Every page under ``docs/`` must declare a frontmatter ``title``. The documentation site
renders that field as the page heading, so a page that also kept its Markdown ``# Heading``
would render the title twice, and a page with no title cannot be rendered at all.
"""

from __future__ import annotations

from scripts.check_docs_frontmatter import (
    iter_docs,
    problems,
    repair,
    split_frontmatter,
    title_defect,
)


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


def test_repair_leaves_a_page_that_is_already_valid_untouched() -> None:
    """Hand-written frontmatter is authoritative and must not be rewritten."""
    content = '---\ntitle: "Kept"\ndescription: "Also kept"\n---\nBody.\n'

    repaired, reason = repair(content)

    assert reason is None
    assert repaired == content


def test_repair_removes_a_body_heading_that_repeats_the_declared_title() -> None:
    """`--fix` has to be able to clear every defect that the check reports."""
    content = '---\ntitle: "Kept"\n---\n# Kept\n\nBody.\n'

    repaired, reason = repair(content)

    assert reason is None
    assert repaired == '---\ntitle: "Kept"\n---\nBody.\n'


def test_repair_refuses_to_delete_a_body_heading_that_says_something_else() -> None:
    """Silently dropping a differing heading would discard page content."""
    content = '---\ntitle: "Declared"\n---\n# Something else\n'

    repaired, reason = repair(content)

    assert repaired == content
    assert reason is not None
    assert "reconcile them manually" in reason


def test_repair_keeps_frontmatter_fields_when_adding_a_missing_title() -> None:
    """A partially populated frontmatter block must not lose its other fields."""
    content = '---\ndescription: "Keep me"\n---\n# Page Title\n\nBody.\n'

    repaired, reason = repair(content)

    assert reason is None
    assert 'title: "Page Title"' in repaired
    assert 'description: "Keep me"' in repaired


def test_frontmatter_is_recognized_without_a_trailing_newline() -> None:
    """A page whose closing fence ends the file still parses as frontmatter."""
    frontmatter, body = split_frontmatter('---\ntitle: "Terse"\n---')

    assert frontmatter == 'title: "Terse"'
    assert body == ""


def test_repair_reports_a_page_with_no_heading_to_derive_a_title_from() -> None:
    """The check fails loudly instead of inventing a title."""
    _, reason = repair("Just a paragraph.\n")

    assert reason is not None
    assert "no leading '# ' heading" in reason


def test_a_declared_title_must_be_a_non_empty_string() -> None:
    """An empty or non-textual title would render as an empty page heading."""
    assert title_defect('title: "Real"')[0] == "Real"
    assert title_defect("title: 'Also real'")[0] == "Also real"
    assert title_defect("title:")[1] == "frontmatter declares an empty or non-textual 'title'"
    assert title_defect("title: 42")[1] == "frontmatter declares an empty or non-textual 'title'"


def test_malformed_yaml_is_rejected_rather_than_pattern_matched() -> None:
    """An unterminated quote is invalid YAML, not a title that happens to start with one."""
    assert title_defect('title: "unterminated')[1] == "frontmatter is not valid YAML"


def test_repair_refuses_to_rewrite_around_a_broken_frontmatter_block() -> None:
    """Guessing at a fix could silently discard fields or duplicate the title key."""
    content = "---\ntitle:\n---\n# Real Title\n"

    repaired, reason = repair(content)

    assert repaired == content
    assert reason is not None
    assert "fix it manually" in reason


def test_repair_reads_a_multiline_yaml_title() -> None:
    """Titles are real YAML scalars, so folded and quoted forms both resolve."""
    content = "---\ntitle: >-\n  Folded Title\n---\n# Folded Title\n\nBody.\n"

    repaired, reason = repair(content)

    assert reason is None
    assert repaired == "---\ntitle: >-\n  Folded Title\n---\nBody.\n"
