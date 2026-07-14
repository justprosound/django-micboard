from pathlib import Path

from scripts import check_migration_integrity


def test_pull_request_diff_compares_origin_base_to_head(monkeypatch) -> None:
    calls: list[tuple[str, ...]] = []

    def fake_git_paths(*args: str) -> set[Path]:
        calls.append(args)
        return {Path("micboard/migrations/0001_initial.py")}

    monkeypatch.setenv("GITHUB_BASE_REF", "main")
    monkeypatch.setattr(check_migration_integrity, "git_paths", fake_git_paths)

    paths = check_migration_integrity.pull_request_diff(diff_filter="MD")

    assert paths == {Path("micboard/migrations/0001_initial.py")}
    assert calls == [("diff", "--name-only", "--diff-filter=MD", "origin/main...HEAD")]


def test_migration_paths_ignores_non_numbered_files() -> None:
    paths = {
        Path("micboard/migrations/0004_add_field.py"),
        Path("micboard/migrations/__init__.py"),
        Path("micboard/multitenancy/migrations/README.md"),
        Path("docs/migrations/0001_example.py"),
    }

    assert check_migration_integrity.migration_paths(paths) == {
        Path("micboard/migrations/0004_add_field.py"),
        Path("docs/migrations/0001_example.py"),
    }
