"""
Management command to synchronize discovered devices with local DB and manage Shure discovery list.

Usage:
  python manage.py sync_shure_discovery --manufacturer=shure
  python manage.py sync_shure_discovery --add-cidrs 192.168.1.0/24,10.0.0.0/8
  python manage.py sync_shure_discovery --add-fqdns "*.example.com"

This will:
 - Poll the Shure System API for currently discovered devices and add/update local Receivers
 - For any local Receiver IP that is not discovered by the Shure API, add its IP to the manual discovery list
 - Optionally store CIDR ranges and FQDN patterns in MICBOARD_CONFIG for future use
"""

from __future__ import annotations

import ipaddress
import json
import logging
from typing import Any

from django.core.management.base import BaseCommand

from micboard.manufacturers import get_manufacturer_plugin
from micboard.manufacturers.shure.discovery_sync import run_discovery_sync
from micboard.models import Manufacturer, MicboardConfig

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = (
        "Sync Shure discovery: import discovered devices, add missing local IPs to Shure discovery"
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--manufacturer",
            required=True,
            help="Manufacturer code to sync (e.g., shure)",
        )
        parser.add_argument(
            "--add-cidrs",
            type=str,
            help="Comma-separated CIDR ranges to store for discovery",
        )
        parser.add_argument(
            "--add-fqdns",
            type=str,
            help="Comma-separated FQDN patterns to store for discovery (e.g., *.example.com)",
        )
        parser.add_argument(
            "--scan-cidrs",
            action="store_true",
            help="Expand stored CIDRs and add discovered IPs to Shure discovery",
        )
        parser.add_argument(
            "--max-hosts",
            type=int,
            default=1024,
            help="Maximum hosts to expand per CIDR range when scanning (default: 1024)",
        )
        parser.add_argument(
            "--scan-fqdns",
            action="store_true",
            help="Resolve stored FQDNs and add resolved IPs to Shure discovery",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        manufacturer_code = options["manufacturer"]

        try:
            manufacturer = Manufacturer.objects.get(code=manufacturer_code)
        except Manufacturer.DoesNotExist:
            self.stderr.write(self.style.ERROR(f"Manufacturer {manufacturer_code} not found"))
            return

        # Optionally add CIDR and FQDN entries to config
        if options.get("add_cidrs"):
            cidrs = [c.strip() for c in options["add_cidrs"].split(",") if c.strip()]
            # Validate CIDR formats
            valid = []
            for c in cidrs:
                try:
                    ipaddress.ip_network(c)
                    valid.append(c)
                except Exception:
                    self.stderr.write(self.style.WARNING(f"Invalid CIDR ignored: {c}"))
            if valid:
                key = "SHURE_DISCOVERY_CIDRS"
                cfg_obj, _ = MicboardConfig.objects.get_or_create(
                    key=key, manufacturer=manufacturer, defaults={"value": json.dumps(valid)}
                )
                if _ is False:
                    # Merge
                    existing = json.loads(cfg_obj.value or "[]")
                    merged = list(set(existing + valid))
                    cfg_obj.value = json.dumps(merged)
                    cfg_obj.save()
                self.stdout.write(self.style.SUCCESS(f"Added CIDRs: {', '.join(valid)}"))

        if options.get("add_fqdns"):
            fqdns = [f.strip() for f in options["add_fqdns"].split(",") if f.strip()]
            if fqdns:
                key = "SHURE_DISCOVERY_FQDNS"
                cfg_obj, _ = MicboardConfig.objects.get_or_create(
                    key=key, manufacturer=manufacturer, defaults={"value": json.dumps(fqdns)}
                )
                if _ is False:
                    existing = json.loads(cfg_obj.value or "[]")
                    merged = list(set(existing + fqdns))
                    cfg_obj.value = json.dumps(merged)
                    cfg_obj.save()
                self.stdout.write(self.style.SUCCESS(f"Added FQDN patterns: {', '.join(fqdns)}"))

        # Main sync logic
        try:
            plugin_class = get_manufacturer_plugin(manufacturer.code)
            # Instantiate plugin (client will be used further down);
            plugin_class(manufacturer)
        except Exception as exc:
            self.stderr.write(self.style.ERROR(f"Failed to initialize plugin: {exc}"))
            logger.exception("Plugin init error")
            return

        # Delegate to shared discovery helper
        scan_cidrs = options.get("scan_cidrs", False)
        scan_fqdns = options.get("scan_fqdns", False)
        max_hosts = options.get("max_hosts", 1024)

        add_cidrs = [c.strip() for c in options.get("add_cidrs", "").split(",") if c.strip()]
        add_fqdns = [f.strip() for f in options.get("add_fqdns", "").split(",") if f.strip()]

        result = run_discovery_sync(
            manufacturer_code,
            add_cidrs=add_cidrs or None,
            add_fqdns=add_fqdns or None,
            scan_cidrs=scan_cidrs,
            scan_fqdns=scan_fqdns,
            max_hosts=max_hosts,
        )

        if result.get("status") == "success":
            self.stdout.write(self.style.SUCCESS("Discovery sync completed successfully"))
        else:
            self.stderr.write(self.style.ERROR(f"Discovery sync failed: {result.get('errors')}"))
