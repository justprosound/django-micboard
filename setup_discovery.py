#!/usr/bin/env python
"""Setup discovery configuration and run sync."""

import os
import sys

import django

# Setup Django
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "example_project.settings")
django.setup()

from micboard.models import DiscoveryCIDR, DiscoveryFQDN, Manufacturer
from micboard.tasks.discovery_tasks import run_discovery_sync_task

# Get or create Shure manufacturer
try:
    manufacturer = Manufacturer.objects.get(code="shure")
except Manufacturer.DoesNotExist:
    manufacturer = Manufacturer.objects.create(code="shure", name="Shure", is_active=True)

# Add CIDRs
cidrs_to_add = ["172.21.0.0/22"]
for cidr in cidrs_to_add:
    obj, created = DiscoveryCIDR.objects.get_or_create(manufacturer=manufacturer, cidr=cidr)
    status = "created" if created else "already exists"

# Add FQDNs
fqdns_to_add = ["howeyl3wm.amx.gatech.edu", "howeyl4wm.amx.gatech.edu", "howeyl1wm.amx.gatech.edu"]
for fqdn in fqdns_to_add:
    obj, created = DiscoveryFQDN.objects.get_or_create(manufacturer=manufacturer, fqdn=fqdn)
    status = "created" if created else "already exists"

# Also add the individual IPs as a workaround CIDR
ip_cidrs = ["172.21.5.144/32", "172.21.7.150/32", "172.21.7.193/32"]
for cidr in ip_cidrs:
    obj, created = DiscoveryCIDR.objects.get_or_create(manufacturer=manufacturer, cidr=cidr)
    status = "created" if created else "already exists"


# Run discovery sync with CIDR and FQDN scanning
result = run_discovery_sync_task(
    manufacturer_id=manufacturer.id, scan_cidrs=True, scan_fqdns=True, max_hosts=1024
)


if result.get("errors"):
    for _error in result.get("errors", []):
        pass
