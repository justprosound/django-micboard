#!/usr/bin/env python
"""Check Charger model fields."""

import os
import sys

import django

from micboard.models import Charger


def main():
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "example_project.settings")
    django.setup()
    # Access fields safely after Django setup
    for _field in Charger._meta.fields:
        pass


if __name__ == "__main__":
    main()
