#!/usr/bin/env python
"""Run discovery with Shure credentials from Windows."""

import os
import sys

import django

from micboard.models import Manufacturer
from micboard.tasks.sync.discovery import run_discovery_sync_task


def main():
    # Get Shure shared key from Windows
    if os.path.exists("/mnt/c/ProgramData/Shure/SystemAPI/Standalone/Security/sharedkey.txt"):
        with open("/mnt/c/ProgramData/Shure/SystemAPI/Standalone/Security/sharedkey.txt", "r") as f:
            shared_key = f.read().strip()
            os.environ["MICBOARD_SHURE_API_SHARED_KEY"] = shared_key

    # Setup Django
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "example_project.settings")
    django.setup()

    # Get Shure manufacturer
    try:
        manufacturer = Manufacturer.objects.get(code="shure")
    except Manufacturer.DoesNotExist:
        sys.exit(1)

    # Run discovery sync with CIDR and FQDN scanning
    result = run_discovery_sync_task(
        manufacturer_id=manufacturer.id,
        scan_cidrs=True,
        scan_fqdns=True,
        max_hosts=1024,
    )

    if result.get("errors"):
        for _error in result.get("errors", []):
            pass


if __name__ == "__main__":
    main()
