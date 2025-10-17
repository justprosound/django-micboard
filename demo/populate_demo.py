"""Populate demo data for django-micboard.

This script is designed to be fed into `python manage.py shell --settings=demo.settings`.
It creates a small set of Locations, Receivers, and Transmitters so the UI shows data.

It's safe to re-run (it will avoid creating duplicates by name).
"""

from django.db import transaction

from micboard.models.devices import Receiver, Transmitter
from micboard.models.locations import Location

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
    # create locations
    locations = {}
    for name, desc in SAMPLE_LOCATIONS:
        loc, _ = Location.objects.get_or_create(name=name, defaults={"description": desc})
        locations[name] = loc

    # create receivers
    receivers = {}
    for code, desc in SAMPLE_RECEIVERS:
        rx, _ = Receiver.objects.get_or_create(code=code, defaults={"name": desc})
        receivers[code] = rx

    # create transmitters and link to receivers
    for code, name, rx_code in SAMPLE_TRANSMITTERS:
        rx = receivers.get(rx_code)
        if not rx:
            continue
        tx, created = Transmitter.objects.get_or_create(code=code, defaults={"name": name})
        if created:
            tx.receiver = rx
            tx.save()


if __name__ == "__main__":
    run()
