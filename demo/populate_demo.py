"""Populate demo data for django-micboard.

This script is designed to be fed into `python manage.py shell --settings=demo.settings`.
It creates a small set of Locations, Receivers, and Transmitters so the UI shows data.

It's safe to re-run (it will avoid creating duplicates by name).
"""

from typing import Optional

from django.db import transaction
from micboard.models.receiver import Receiver
from micboard.models.transmitter import Transmitter

from micboard.models.locations import Location

try:
    from micboard.manufacturers.shure.client import ShureSystemAPIClient

    ShureSystemAPIClientType: Optional[type] = ShureSystemAPIClient
except Exception:
    ShureSystemAPIClientType = None

SAMPLE_LOCATIONS = [
    ("Main Hall", "First floor main hall"),
    ("Control Room", "Backstage control room"),
]

SAMPLE_RECEIVERS = [
    ("RX-1", "Main Hall Receiver"),
    ("RX-2", "Control Room Receiver"),
]

SAMPLE_TRANSMITTERS = [
    ("TX-1", "Mic 1", "RX-1"),
    ("TX-2", "Mic 2", "RX-2"),
]


@transaction.atomic
def run():
    # If a live Shure API is configured and healthy, avoid inserting mock data
    if ShureSystemAPIClientType is not None:
        try:
            client = ShureSystemAPIClientType()
            health = client.check_health()
            if health.get("status") == "healthy":
                print("Live Shure API detected and healthy - skipping mock data population.")
                return
        except Exception:
            # Fall through to populate mock data
            pass
    # create locations
    locations = {}
    for name, desc in SAMPLE_LOCATIONS:
        loc, _ = Location.objects.get_or_create(name=name, defaults={"description": desc})
        locations[name] = loc

    # create receivers
    receivers = {}
    for code, desc in SAMPLE_RECEIVERS:
        rx, _ = Receiver.objects.get_or_create(api_device_id=code, defaults={"name": desc})
        receivers[code] = rx

    # create transmitters and link to receivers
    for _code, name, rx_code in SAMPLE_TRANSMITTERS:
        rx = receivers.get(rx_code)
        if not rx:
            continue
        tx, created = Transmitter.objects.get_or_create(
            channel__receiver=rx, defaults={"name": name}
        )
        if created:
            # For demo, associate transmitter with a channel; create a channel if needed
            # Find or create channel 1 for this receiver
            from micboard.models import Channel

            channel, _ = Channel.objects.get_or_create(receiver=rx, channel_number=1)
            tx.channel = channel
            tx.save()


if __name__ == "__main__":
    run()
