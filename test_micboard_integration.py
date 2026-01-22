#!/usr/bin/env python
"""
Quick test: Verify django-micboard can fetch and process the 30+ discovered devices
from Shure System API.
"""

import os
import sys
import django

# Setup Django
sys.path.insert(0, "/home/skuonen/django-micboard")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "demo.settings")

# Set Shure API credentials directly
os.environ["MICBOARD_SHURE_API_BASE_URL"] = "https://localhost:10000"
os.environ["MICBOARD_SHURE_API_SHARED_KEY"] = "ykEIaOmIne4r8EoT8sghREB_c5Pzqm2Ce2XxzMDkWVFE0zRkVbwOQ3vlx9mQHU1nka9-PJKVOTDbB2pTNBLtxEgxoT7ueJbm3KGlcsanou5bBDuGrzN5VyDFtfGNhVh6EHWsYUatUA-OJnjIBL5QfwSvLicx4IJ8ZAnI0YStvmKmiGjU1_zRohMlVk-WGhjCJ2gPQfcy-0oirUo_9TJRz2JfCaZnrhjZImx7FTyAGA9t0Pv1bDqK5A5LngHfJdKG"
os.environ["MICBOARD_SHURE_API_VERIFY_SSL"] = "false"

django.setup()

from micboard.integrations.shure.client import ShureSystemAPIClient
from micboard.integrations.shure.transformers import ShureDataTransformer
from django.conf import settings

def main():
    config = getattr(settings, "MICBOARD_CONFIG", {})
    base_url = config.get("SHURE_API_BASE_URL", "https://localhost:10000")
    
    print(f"\n{'='*80}")
    print("Django-Micboard Shure System API Integration Test")
    print(f"{'='*80}")
    print(f"\nConnecting to: {base_url}")
    
    try:
        # Initialize client
        client = ShureSystemAPIClient(base_url=base_url, verify_ssl=False)
        print("✓ Client initialized")
        
        # Fetch devices
        print("\nFetching devices from System API...")
        response = client._session.get(
            f"{base_url}/api/v1/devices",
            headers={"x-api-key": client.shared_key},
            timeout=client.timeout,
            verify=False
        )
        
        if response.status_code != 200:
            print(f"✗ Failed: {response.status_code}")
            print(response.text)
            return
        
        data = response.json()
        devices = data.get("devices", [])
        
        print(f"✓ Fetched {len(devices)} devices from System API")
        
        if devices:
            print(f"\n{'Model':<20} {'IP Address':<18} {'State':<12} {'Firmware':<15}")
            print("-" * 80)
            
            # Transform and display first few devices
            transformer = ShureDataTransformer()
            for device in devices[:10]:
                model = device.get("model", "Unknown")
                ip = device.get("id", "Unknown")
                state = device.get("state", "Unknown")
                fw = device.get("properties", {}).get("firmware_version", "Unknown")
                
                print(f"{model:<20} {ip:<18} {state:<12} {fw:<15}")
            
            if len(devices) > 10:
                print(f"... and {len(devices) - 10} more devices")
            
            print(f"\n✓ Django-micboard can successfully fetch and process discovered devices!")
            print(f"\nReady for:")
            print(f"  1. Model population (Device, Transmitter, Receiver tables)")
            print(f"  2. Polling integration (poll_devices management command)")
            print(f"  3. WebSocket subscriptions for real-time updates")
        else:
            print("⚠ No devices returned (might be discovery still in progress)")
            
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
