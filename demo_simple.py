#!/usr/bin/env python
"""Simple demonstration showing the key concepts of manufacturer-agnostic architecture.
This doesn't require live API connections - just shows the code structure.
"""

import os
import sys

import django

# Setup Django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "example_project.settings")
sys.path.insert(0, os.path.dirname(__file__))
django.setup()

from micboard.manufacturers import get_manufacturer_plugin
from micboard.models import Manufacturer


def main():
    # Show plugin system

    # Show current manufacturers
    manufacturers = Manufacturer.objects.all()
    for mfg in manufacturers:
        try:
            get_manufacturer_plugin(mfg.code)
        except Exception:
            pass

    # Show sync process

    # Show models

    # Show deduplication

    # Show bi-directional sync

    # Show how to add new manufacturer


if __name__ == "__main__":
    main()
