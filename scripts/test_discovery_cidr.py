#!/usr/bin/env python3
import logging
import os
import sys
from unittest.mock import MagicMock, patch

import django

# Setup Django
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(BASE_DIR)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "example_project.settings")
django.setup()

from django.conf import settings
from micboard.models import Manufacturer, DiscoveryCIDR, DiscoveryQueue, DiscoveryJob
from micboard.tasks.discovery_tasks import run_discovery_sync_task

logger = logging.getLogger("test_discovery")
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

def test_full_discovery():
    logger.info("Starting Full Discovery E2E Test...")
    
    # 1. Setup Manufacturer
    manufacturer, _ = Manufacturer.objects.get_or_create(
        code="shure", 
        defaults={"name": "Shure", "is_active": True}
    )
    
    # 2. Clear existing data
    DiscoveryQueue.objects.all().delete()
    DiscoveryJob.objects.all().delete()
    DiscoveryCIDR.objects.all().delete()
    
    # 3. Setup CIDR
    cidr_str = "172.21.0.0/19"
    DiscoveryCIDR.objects.get_or_create(manufacturer=manufacturer, cidr=cidr_str)
    
    # 4. Mock API Client
    mock_devices = [
        {
            "id": "AD4Q-1",
            "serial": "SN-RECEIVER-1",
            "ip": "172.21.0.10",
            "model": "AD4Q",
            "type": "receiver",
            "state": "ONLINE"
        },
        {
            "id": "SBC220-1",
            "serial": "SN-CHARGER-1",
            "ip": "172.21.0.20",
            "model": "SBC220",
            "type": "charger",
            "state": "ONLINE"
        }
    ]
    
    # Disable django-q globally for this test
    if not hasattr(settings, 'MICBOARD_CONFIG'):
        settings.MICBOARD_CONFIG = {}
    
    # Patch both the dependency check and the client
    with patch('micboard.utils.dependencies.HAS_DJANGO_Q', False):
        with patch('micboard.integrations.shure.client.ShureSystemAPIClient') as MockClient:
            instance = MockClient.return_value
            # Both ways Shure API client might be called
            instance.devices.get_devices.return_value = mock_devices
            instance.get_devices.return_value = mock_devices
            instance.add_discovery_ips.return_value = True
            
            logger.info(f"Running discovery sync for {cidr_str}...")
            # We bypass the trigger in models by patching HAS_DJANGO_Q above
            # Now run the task manually
            summary = run_discovery_sync_task(
                manufacturer_id=manufacturer.pk,
                scan_cidrs=True,
                max_hosts=10
            )
            
            logger.info(f"Discovery Task Summary: {summary}")
        
    # 5. Verify DiscoveryQueue
    queue_count = DiscoveryQueue.objects.count()
    logger.info(f"Devices in Discovery Queue: {queue_count}")
    
    found_types = []
    for item in DiscoveryQueue.objects.all():
        logger.info(f"  - [{item.device_type}] {item.name} ({item.model}) @ {item.ip} - Status: {item.status}")
        found_types.append(item.device_type)
        
    if queue_count == 2 and "charger" in found_types and "receiver" in found_types:
        logger.info("SUCCESS: Both receiver and charger found and added to queue.")
    else:
        logger.error(f"FAILED: Expected 2 items (1 receiver, 1 charger) in queue, found {queue_count} with types {found_types}")
        sys.exit(1)

if __name__ == "__main__":
    test_full_discovery()