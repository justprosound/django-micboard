#!/usr/bin/env python
"""Check WirelessChassis model fields."""

import os
import sys

import django

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "example_project.settings")
django.setup()

from micboard.models import WirelessChassis

for _field in WirelessChassis._meta.fields:
    pass
