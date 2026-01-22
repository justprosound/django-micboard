#!/usr/bin/env python
"""
Monitor Shure System API device discovery over an extended period.
"""
import os
import sys
import time
import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Setup Django
sys.path.insert(0, '/home/skuonen/django-micboard')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'demo.settings')
import django
django.setup()

from django.conf import settings

config = getattr(settings, "MICBOARD_CONFIG", {})
BASE_URL = config.get("SHURE_API_BASE_URL", "https://localhost:10000")
SHARED_KEY = config.get("SHURE_API_SHARED_KEY")

headers = {
    "Authorization": f"Bearer {SHARED_KEY}",
    "x-api-key": str(SHARED_KEY),
    "Content-Type": "application/json"
}

def main():
    devices_endpoint = f"{BASE_URL}/api/v1/devices"
    
    print("Monitoring Shure System API device discovery...")
    print(f"Checking: {devices_endpoint}")
    print("=" * 70)
    
    last_count = 0
    check_interval = 5  # seconds
    max_duration = 300  # 5 minutes
    elapsed = 0
    
    while elapsed < max_duration:
        try:
            response = requests.get(
                devices_endpoint,
                headers=headers,
                verify=False,
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                devices = data.get('devices', [])
                current_count = len(devices)
                
                timestamp = time.strftime("%H:%M:%S")
                
                if current_count > last_count:
                    print(f"[{timestamp}] {current_count} devices discovered (↑ +{current_count - last_count})")
                    last_count = current_count
                    
                    # Show first few new devices
                    if current_count <= 5:
                        print("  Devices:")
                        for device in devices:
                            model = device.get('modelName', 'Unknown')
                            ip = device.get('ipAddress', 'N/A')
                            status = device.get('deviceStatus', 'Unknown')
                            print(f"    - {model:15} {ip:15} ({status})")
                else:
                    print(f"[{timestamp}] {current_count} devices discovered")
            
            elapsed += check_interval
            if elapsed < max_duration:
                time.sleep(check_interval)
                
        except Exception as e:
            print(f"Error: {e}")
            elapsed += check_interval
            if elapsed < max_duration:
                time.sleep(check_interval)
    
    print()
    print(f"Final count: {last_count} devices discovered")

if __name__ == '__main__':
    main()
