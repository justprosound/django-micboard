"""
MkDocs macros for Django Micboard documentation.

This module provides dynamic content generation for the documentation.
"""

import re
from datetime import datetime, timezone
from pathlib import Path


def define_env(env):
    """Define environment variables and macros for MkDocs."""

    @env.macro
    def current_year():
        """Return the current year."""
        return datetime.now(timezone.utc).year

    @env.macro
    def project_version():
        """Return the project version from pyproject.toml or a default."""
        try:
            pyproject_path = Path(env.project_dir) / "pyproject.toml"
            if pyproject_path.exists():
                content = pyproject_path.read_text()
                version_match = re.search(r'version\s*=\s*["\']([^"\']+)["\']', content)
                if version_match:
                    return version_match.group(1)
        except Exception:
            pass
        return "25.10.15"  # Fallback version

    @env.macro
    def python_version():
        """Return the minimum Python version requirement."""
        try:
            pyproject_path = Path(env.project_dir) / "pyproject.toml"
            if pyproject_path.exists():
                content = pyproject_path.read_text()
                python_match = re.search(r'python\s*=\s*["\']([^"\']+)["\']', content)
                if python_match:
                    return python_match.group(1).replace(">=", "")
        except Exception:
            pass
        return "3.9"

    @env.macro
    def django_version():
        """Return the Django version requirement."""
        try:
            pyproject_path = Path(env.project_dir) / "pyproject.toml"
            if pyproject_path.exists():
                content = pyproject_path.read_text()
                django_match = re.search(
                    r'django[^=]*=\s*["\']([^"\']+)["\']', content, re.IGNORECASE
                )
                if django_match:
                    return django_match.group(1)
        except Exception:
            pass
        return "4.2+ or 5.0+"

    @env.macro
    def file_count():
        """Return the count of Python files in the project."""
        try:
            python_files = list(Path(env.project_dir).rglob("*.py"))
            return len([f for f in python_files if not f.name.startswith("__pycache__")])
        except Exception:
            return "unknown"

    @env.macro
    def test_count():
        """Return the count of test files."""
        try:
            test_files = list(Path(env.project_dir).glob("tests/**/*.py"))
            return len(test_files)
        except Exception:
            return "unknown"

    @env.macro
    def last_commit_date():
        """Return the date of the last commit."""
        try:
            import subprocess

            result = subprocess.run(
                ["git", "log", "-1", "--format=%cd", "--date=short"],
                cwd=env.project_dir,
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception:
            pass
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")

    @env.macro
    def contributors_count():
        """Return the number of contributors."""
        try:
            import subprocess

            result = subprocess.run(
                ["git", "shortlog", "-sn", "--no-merges"],
                cwd=env.project_dir,
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                return len(result.stdout.strip().split("\n"))
        except Exception:
            pass
        return "unknown"

    @env.macro
    def license_info():
        """Return license information."""
        try:
            license_path = Path(env.project_dir) / "LICENSE"
            if license_path.exists():
                content = license_path.read_text()
                if "AGPL" in content:
                    return "AGPL-3.0-or-later"
        except Exception:
            pass
        return "AGPL-3.0-or-later"
