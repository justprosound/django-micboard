#!/usr/bin/env python3
import json

import requests


def expand_python_versions(version_str):
    # Accepts formats like "3.10 - 3.13" or "3.8 - 3.12 (added in 4.2.8)"
    import re

    match = re.match(r"(\d+\.\d+)\s*-\s*(\d+\.\d+)", version_str)
    if not match:
        # Try to extract all version numbers
        return re.findall(r"\d+\.\d+", version_str)
    start, end = match.groups()
    start_major, start_minor = map(int, start.split("."))
    end_major, end_minor = map(int, end.split("."))
    versions = []
    major = start_major
    minor = start_minor
    while True:
        versions.append(f"{major}.{minor}")
        if major == end_major and minor == end_minor:
            break
        minor += 1
        if minor > 99:  # unlikely, but just in case
            major += 1
            minor = 0
    return versions


def get_supported_django_python_pairs():
    resp = requests.get("https://endoflife.date/api/v1/products/django")
    resp.raise_for_status()
    api = resp.json()
    releases = api["result"]["releases"]
    matrix = []
    for v in releases:
        # Only consider supported Django releases
        if v.get("isMaintained") and not v.get("isEol"):
            django_version = v["name"]
            # Only include numeric cycles (no pre-releases)
            if not django_version.replace(".", "").isdigit():
                continue
            py_versions_str = v.get("custom", {}).get("supportedPythonVersions", "")
            py_versions = expand_python_versions(py_versions_str)
            for py_version in py_versions:
                if py_version.replace(".", "").isdigit():
                    matrix.append({"django-version": django_version, "python-version": py_version})
    return matrix


def main():
    matrix = get_supported_django_python_pairs()
    # Fallback: if matrix is empty, add a default supported combo
    if not matrix:
        # Safe fallback: Django 4.2 and Python 3.11 (both LTS and widely supported)
        matrix = [{"django-version": "4.2", "python-version": "3.11"}]
    print(json.dumps({"include": matrix}))


if __name__ == "__main__":
    main()
