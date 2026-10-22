import shutil
import subprocess
from pathlib import Path

import pytest

from scripts.changelog_fragments import (
    changed_fragment_paths,
    clear_fragments,
    collect_changelog,
    load_fragments,
    validate_pull_request_fragment,
)


def test_collect_changelog_groups_legacy_notes_and_fragments_by_category(tmp_path: Path) -> None:
    """Release notes include legacy entries and fragments in deterministic order."""
    changelog = tmp_path / "CHANGELOG.md"
    fragment_dir = tmp_path / "changelog.d"
    fragment_dir.mkdir()
    changelog.write_text(
        "# Changelog\n\n## [Unreleased]\n\n### Added\n\n- Legacy note\n\n"
        "### Changed\n\n- Existing behavior\n\n## [26.01.01] - 2026-01-01\n",
        encoding="utf-8",
    )
    (fragment_dir / "pr-12.md").write_text(
        "### Changed\n\n- Twelfth pull request\n", encoding="utf-8"
    )
    (fragment_dir / "pr-3.md").write_text("### Added\n\n- Third pull request\n", encoding="utf-8")

    notes = collect_changelog(changelog, fragment_dir)

    assert notes == (
        "### Added\n\n- Legacy note\n\n- Third pull request\n\n"
        "### Changed\n\n- Existing behavior\n\n- Twelfth pull request"
    )


def test_load_fragments_rejects_invalid_names(tmp_path: Path) -> None:
    """Fragments use the pull-request number so concurrent changes never share a file."""
    fragment_dir = tmp_path / "changelog.d"
    fragment_dir.mkdir()
    (fragment_dir / "change.md").write_text("### Added\n\n- A note\n", encoding="utf-8")

    with pytest.raises(ValueError, match=r"pr-<number>\.md"):
        load_fragments(fragment_dir)


def test_load_fragments_rejects_unknown_categories(tmp_path: Path) -> None:
    """Fragments cannot silently introduce unrecognized release-note sections."""
    fragment_dir = tmp_path / "changelog.d"
    fragment_dir.mkdir()
    (fragment_dir / "pr-12.md").write_text("### Features\n\n- A note\n", encoding="utf-8")

    with pytest.raises(ValueError, match="unsupported changelog category"):
        load_fragments(fragment_dir)


def test_load_fragments_rejects_sections_without_bullets(tmp_path: Path) -> None:
    """Every fragment section contains at least one user-readable bullet."""
    fragment_dir = tmp_path / "changelog.d"
    fragment_dir.mkdir()
    (fragment_dir / "pr-12.md").write_text("### Added\n\n", encoding="utf-8")

    with pytest.raises(ValueError, match="must contain a bullet"):
        load_fragments(fragment_dir)


def test_load_fragments_rejects_empty_fragments(tmp_path: Path) -> None:
    """An empty fragment cannot satisfy the pull request changelog requirement."""
    fragment_dir = tmp_path / "changelog.d"
    fragment_dir.mkdir()
    (fragment_dir / "pr-12.md").write_text("", encoding="utf-8")

    with pytest.raises(ValueError, match="fragment must contain a category"):
        load_fragments(fragment_dir)


def test_validate_pull_request_fragment_requires_its_own_file() -> None:
    """A pull request cannot pass validation by editing another fragment."""
    validate_pull_request_fragment(["changelog.d/pr-12.md"], 12, Path("changelog.d"))

    with pytest.raises(ValueError, match=r"Add changelog\.d/pr-12\.md"):
        validate_pull_request_fragment(["changelog.d/pr-11.md"], 12, Path("changelog.d"))

    with pytest.raises(ValueError, match="Do not modify another"):
        validate_pull_request_fragment(
            ["changelog.d/pr-12.md", "changelog.d/pr-11.md"],
            12,
            Path("changelog.d"),
        )


def test_changed_fragment_paths_finds_files_added_after_base(tmp_path: Path) -> None:
    """CI diff detection recognizes a pull request's newly added fragment."""
    git_executable = shutil.which("git")
    if git_executable is None:
        pytest.skip("Git is required to validate pull request diffs")

    def git(*args: str) -> str:
        result = subprocess.run(  # noqa: S603
            [git_executable, *args],
            check=True,
            capture_output=True,
            text=True,
            cwd=tmp_path,
        )
        return result.stdout.strip()

    git("init", "--quiet")
    git("config", "user.email", "changelog-test@example.com")
    git("config", "user.name", "Changelog test")
    (tmp_path / "README.md").write_text("Base\n", encoding="utf-8")
    git("add", "README.md")
    git("commit", "--quiet", "-m", "base")
    base = git("rev-parse", "HEAD")

    fragment_dir = tmp_path / "changelog.d"
    fragment_dir.mkdir()
    (fragment_dir / "pr-12.md").write_text("### Added\n\n- New behavior\n", encoding="utf-8")
    git("add", "changelog.d/pr-12.md")
    git("commit", "--quiet", "-m", "add release note")

    assert changed_fragment_paths(base, Path("changelog.d"), cwd=tmp_path) == [
        "changelog.d/pr-12.md"
    ]


def test_clear_fragments_removes_only_validated_fragments(tmp_path: Path) -> None:
    """Promoting a release removes fragment files after validating their contents."""
    fragment_dir = tmp_path / "changelog.d"
    fragment_dir.mkdir()
    fragment = fragment_dir / "pr-12.md"
    fragment.write_text("### Fixed\n\n- Resolve a defect\n", encoding="utf-8")

    assert clear_fragments(fragment_dir) == 1
    assert not fragment.exists()
