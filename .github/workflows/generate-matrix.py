#!/usr/bin/env python3
import datetime
import json

import requests


def get_supported_django_python_pairs():
    resp = requests.get("https://endoflife.date/api/v1/products/django")
    resp.raise_for_status()
    versions = resp.json()
    today = datetime.datetime.now(tz=datetime.timezone.utc).date()
    matrix = []
    for v in versions:
        # Only consider supported Django releases
        if (
            v.get("eol")
            and datetime.datetime.strptime(v["eol"], "%Y-%m-%d")
            .replace(tzinfo=datetime.timezone.utc)
            .date()
            > today
        ):
            django_version = v["cycle"]
            # Only include numeric cycles (no pre-releases)
            if not django_version.replace(".", "").isdigit():
                continue
            for py_version in v.get("supportedPythonVersions", []):
                # Only include numeric python versions
                if py_version.replace(".", "").isdigit():
                    matrix.append({"django-version": django_version, "python-version": py_version})
    return matrix


def main():
    matrix = get_supported_django_python_pairs()
    print(json.dumps({"include": matrix}))


if __name__ == "__main__":
    main()
