from scripts.promote_changelog import ReleaseSection, promote_changelog


def test_promote_changelog_moves_unreleased_notes_once() -> None:
    """Unreleased notes are moved into the new versioned release section exactly once."""
    content = """# Changelog

## [Unreleased]

### Added

- First release note

## [25.01.01] - 2025-01-01

- Previous release
"""
    section = ReleaseSection(
        version="26.08.06", release_date="2026-08-06", notes="### Added\n\n- First release note"
    )

    result = promote_changelog(content, section)

    assert result.count("First release note") == 1
    assert "## [Unreleased]\n\n## [26.08.06] - 2026-08-06" in result


def test_promote_changelog_keeps_consecutive_releases_distinct() -> None:
    """Multiple calls to promote_changelog keep release sections distinct and ordered."""
    first = promote_changelog(
        "# Changelog\n\n## [Unreleased]\n\n- First\n",
        ReleaseSection(version="26.08.06", release_date="2026-08-06", notes="- First"),
    )
    with_second_note = first.replace(
        "## [Unreleased]\n\n## [26.08.06]",
        "## [Unreleased]\n\n- Second\n\n## [26.08.06]",
    )

    result = promote_changelog(
        with_second_note,
        ReleaseSection(version="26.08.06.1", release_date="2026-08-06", notes="- Second"),
    )

    assert result.count("- First") == 1
    assert result.count("- Second") == 1
    assert result.index("## [26.08.06.1]") < result.index("## [26.08.06]")


def test_promote_changelog_supports_trailing_text_in_unreleased_heading() -> None:
    """Unreleased heading with trailing text is matched correctly."""
    content = "# Changelog\n\n## [Unreleased] - Draft\n\n- Note\n"
    section = ReleaseSection(version="26.08.06", release_date="2026-08-06", notes="- Note")
    result = promote_changelog(content, section)
    assert "## [26.08.06] - 2026-08-06" in result
    assert result.count("- Note") == 1


def test_promote_changelog_raises_value_error_if_unreleased_missing() -> None:
    """Missing Unreleased heading raises ValueError cleanly."""
    import pytest

    content = "# Changelog\n\n## [25.01.01] - 2025-01-01\n"
    section = ReleaseSection(version="26.08.06", release_date="2026-08-06", notes="- Note")
    with pytest.raises(ValueError, match=r"Changelog has no ## \[Unreleased\] heading"):
        promote_changelog(content, section)
