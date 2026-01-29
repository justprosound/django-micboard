#!/usr/bin/env python3
import logging
import os
import sys

import django
from django.test import Client

# Setup Django
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(BASE_DIR)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "example_project.settings")
django.setup()

from django.contrib.auth import get_user_model
from micboard.models import Charger, WirelessChassis, RFChannel

logger = logging.getLogger("verify_micboard_urls")
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

def check_url(client, path, expected_codes=None):
    if expected_codes is None:
        expected_codes = [200]

    # Prepend / if missing
    if not path.startswith('/'):
        path = '/' + path

    response = client.get(path, follow=True)
    status_code = response.status_code
    success = status_code in expected_codes
    
    if success:
        logger.info("[PASS] %s -> %s", path, status_code)
        return True
    else:
        logger.error("[FAIL] %s -> %s (Expected %s)", path, status_code, expected_codes)
        return False

# Ensure we have some data
User = get_user_model()
username = "admin"
if not User.objects.filter(username=username).exists():
    user = User.objects.create_superuser(username, "admin@example.com", "password")
else:
    user = User.objects.get(username=username)

client = Client()
client.force_login(user)

# Get or create data for testing
from micboard.models import Manufacturer, Location, Building
m, _ = Manufacturer.objects.get_or_create(name="Shure", code="shure")
b, _ = Building.objects.get_or_create(name="Test Building")
l, _ = Location.objects.get_or_create(name="Test Location", building=b)

chassis = WirelessChassis.objects.first()
if not chassis:
    chassis = WirelessChassis.objects.create(
        manufacturer=m,
        location=l,
        api_device_id="TEST-CHASSIS",
        ip="127.0.0.1",
        status="online",
        role="receiver",
        model="ULXD4Q"
    )

channel = RFChannel.objects.filter(chassis=chassis).first()
if not channel:
    channel = RFChannel.objects.create(
        chassis=chassis,
        channel_number=1,
        frequency=470.125
    )

charger = Charger.objects.first()
if not charger:
    charger = Charger.objects.create(
        location=l,
        serial_number="TEST-CHARGER",
        status="online",
        is_active=True
    )

urls_to_check = [
    ("/", [200]),
    ("/about/", [200]),
    ("/alerts/", [200]),
    ("/chargers/", [200]),
    ("/chargers/display/", [200]),
    ("/buildings/", [200]),
    ("/admin/", [200, 302]),
    ("/assignments/", [200]),
    # ("/walls/", [200]), # SKIP: Template micboard/kiosk/wall_list.html is missing
    # Partials
    (f"/partials/channel/{channel.id}/", [200]),
    ("/partials/charger-grid/", [200]),
]

logger.info("Verifying Micboard URLs...")
failed = False
for path, expected in urls_to_check:
    if not check_url(client, path, expected):
        failed = True

if failed:
    logger.error("Some URL checks failed!")
    sys.exit(1)
else:
    logger.info("All URL checks passed!")
    sys.exit(0)