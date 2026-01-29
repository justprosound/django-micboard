#!/usr/bin/env python3
"""
Clean start script for discovery.
Removes all existing devices and seeds example data for Shure devices.
Validates new entries against predefined schemas (regex/ipaddress).
"""

import os
import sys
import re
import ipaddress
import logging

import django
from django.db import transaction

# Setup Django
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(BASE_DIR)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "example_project.settings")
django.setup()

from micboard.models import (
    WirelessChassis, WirelessUnit, Charger, ChargerSlot,
    DiscoveredDevice, DiscoveryQueue, DiscoveryJob,
    DiscoveryCIDR, DiscoveryFQDN, Manufacturer, Location, Building
)

logger = logging.getLogger("clean_seed")
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

def validate_cidr(cidr):
    try:
        ipaddress.ip_network(cidr, strict=False)
        return True
    except ValueError as e:
        logger.error(f"Invalid CIDR {cidr}: {e}")
        return False

def validate_fqdn(fqdn):
    # Basic FQDN regex
    pattern = r'^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z0-9][a-z0-9-]{0,61}[a-z0-9]$'
    if re.match(pattern, fqdn, re.IGNORECASE):
        return True
    logger.error(f"Invalid FQDN {fqdn}")
    return False

def clean_db():
    logger.info("Cleaning database of all existing devices and discovery logs...")
    models_to_clear = [
        WirelessUnit, ChargerSlot, Charger, WirelessChassis,
        DiscoveredDevice, DiscoveryQueue, DiscoveryJob,
        DiscoveryCIDR, DiscoveryFQDN
    ]
    for model in models_to_clear:
        count = model.objects.all().delete()[0]
        logger.info(f"  Deleted {count} records from {model._meta.verbose_name}")

def seed_data():
    logger.info("Seeding clean discovery data...")
    
    with transaction.atomic():
        # 1. Ensure Shure Manufacturer exists
        shure, _ = Manufacturer.objects.get_or_create(
            code="shure",
            defaults={"name": "Shure", "is_active": True}
        )
        
        # 2. Setup Buildings and Locations
        building, _ = Building.objects.get_or_create(name="Main Campus")
        location, _ = Location.objects.get_or_create(name="Rack Room A", building=building)
        
        # 3. Add Discovery CIDRs
        cidrs = ["172.21.0.0/19", "10.0.5.0/24"]
        for cidr in cidrs:
            if validate_cidr(cidr):
                DiscoveryCIDR.objects.create(manufacturer=shure, cidr=cidr)
                logger.info(f"  Added Discovery CIDR: {cidr}")
        
        # 4. Add Discovery FQDNs
        fqdns = ["shure-receiver-01.local", "shure-mgmt.internal.net"]
        for fqdn in fqdns:
            if validate_fqdn(fqdn):
                DiscoveryFQDN.objects.create(manufacturer=shure, fqdn=fqdn)
                logger.info(f"  Added Discovery FQDN: {fqdn}")
        
        # 5. Create Manual Chassis (Redundant mapping check)
        # These should map back to network objects (Manufacturer and Location)
        manual_devices = [
            {
                "name": "Manual AD4Q",
                "model": "AD4Q",
                "serial": "MANUAL-SN-001",
                "ip": "172.21.10.5",
                "role": "receiver"
            },
            {
                "name": "Manual Charger",
                "model": "SBC220",
                "serial": "MANUAL-SN-002",
                "ip": "172.21.10.6",
                "role": "charger"
            }
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
                    status="online"
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
                    status="online"
                )
            logger.info(f"  Created manual {dev['role']}: {dev['name']} at {dev['ip']}")

if __name__ == "__main__":
    clean_db()
    seed_data()
    logger.info("Cleanup and seeding complete.")
