import ipaddress
import logging
import re

from django.core.management.base import BaseCommand
from django.db import transaction

from micboard.models import (
    Building,
    Charger,
    ChargerSlot,
    DiscoveredDevice,
    DiscoveryCIDR,
    DiscoveryFQDN,
    DiscoveryJob,
    DiscoveryQueue,
    Location,
    Manufacturer,
    WirelessChassis,
    WirelessUnit,
)

logger = logging.getLogger("clean_seed")


class Command(BaseCommand):
    help = "Clean all discovery/device data and seed example Shure data."

    def handle(self, *args, **options):
        self.clean_db()
        self.seed_data()
        self.stdout.write(self.style.SUCCESS("Cleanup and seeding complete."))

    def validate_cidr(self, cidr):
        try:
            ipaddress.ip_network(cidr, strict=False)
            return True
        except ValueError as e:
            logger.error(f"Invalid CIDR {cidr}: {e}")
            return False

    def validate_fqdn(self, fqdn):
        pattern = r"^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z0-9][a-z0-9-]{0,61}[a-z0-9]$"
        if re.match(pattern, fqdn, re.IGNORECASE):
            return True
        logger.error(f"Invalid FQDN {fqdn}")
        return False

    def clean_db(self):
        logger.info("Cleaning database of all existing devices and discovery logs...")
        models_to_clear = [
            WirelessUnit,
            ChargerSlot,
            Charger,
            WirelessChassis,
            DiscoveredDevice,
            DiscoveryQueue,
            DiscoveryJob,
            DiscoveryCIDR,
            DiscoveryFQDN,
        ]
        for model in models_to_clear:
            count = model.objects.all().delete()[0]
            logger.info(f"  Deleted {count} records from {model._meta.verbose_name}")

    def seed_data(self):
        logger.info("Seeding clean discovery data...")
        with transaction.atomic():
            shure, _ = Manufacturer.objects.get_or_create(
                code="shure", defaults={"name": "Shure", "is_active": True}
            )
            building, _ = Building.objects.get_or_create(name="Main Campus")
            location, _ = Location.objects.get_or_create(name="Rack Room A", building=building)
            cidrs = ["172.21.0.0/19", "10.0.5.0/24"]
            for cidr in cidrs:
                if self.validate_cidr(cidr):
                    DiscoveryCIDR.objects.create(manufacturer=shure, cidr=cidr)
                    logger.info(f"  Added Discovery CIDR: {cidr}")
            fqdns = ["shure-receiver-01.local", "shure-mgmt.internal.net"]
            for fqdn in fqdns:
                if self.validate_fqdn(fqdn):
                    DiscoveryFQDN.objects.create(manufacturer=shure, fqdn=fqdn)
                    logger.info(f"  Added Discovery FQDN: {fqdn}")
            manual_devices = [
                {
                    "name": "Manual AD4Q",
                    "model": "AD4Q",
                    "serial": "MANUAL-SN-001",
                    "ip": "172.21.10.5",
                    "role": "receiver",
                },
                {
                    "name": "Manual Charger",
                    "model": "SBC220",
                    "serial": "MANUAL-SN-002",
                    "ip": "172.21.10.6",
                    "role": "charger",
                },
            ]
            for dev in manual_devices:
                if dev["role"] == "charger":
                    Charger.objects.create(
                        manufacturer=shure,
                        location=location,
                        name=dev["name"],
                        model=dev["model"],
                        serial_number=dev["serial"],
                        ip=dev["ip"],
                        status="online",
                    )
                else:
                    WirelessChassis.objects.create(
                        manufacturer=shure,
                        location=location,
                        name=dev["name"],
                        model=dev["model"],
                        serial_number=dev["serial"],
                        ip=dev["ip"],
                        role=dev["role"],
                        api_device_id=f"API-{dev['serial']}",
                        status="online",
                    )
                logger.info(f"  Created manual {dev['role']}: {dev['name']} at {dev['ip']}")
