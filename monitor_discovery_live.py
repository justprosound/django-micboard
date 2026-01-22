#!/usr/bin/env python
"""
Continuous monitoring of Shure System API device discovery.
Watches for devices as they are discovered asynchronously.
"""
import os
import sys
import time
import json
from datetime import datetime
import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Load from .env.local if available
def load_env_file(filename=".env.local"):
    """Load environment variables from .env.local file."""
    if not os.path.exists(filename):
        return
    
    with open(filename) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                os.environ.setdefault(key.strip(), value.strip())

load_env_file()

BASE_URL = os.environ.get("SHURE_API_BASE_URL", "https://localhost:10000")
SHARED_KEY = os.environ.get("SHURE_API_SHARED_KEY")

if not SHARED_KEY:
    print("Error: SHURE_API_SHARED_KEY not set")
    print("Please set it in .env.local or as an environment variable")
    sys.exit(1)

headers = {
    "x-api-key": SHARED_KEY,
    "Accept": "application/json",
    "Content-Type": "application/json"
}

def get_discovery_ips():
    """Get list of configured discovery IPs."""
    try:
        response = requests.get(
            f"{BASE_URL}/api/v1/config/discovery/ips",
            headers=headers,
            verify=False,
            timeout=10
        )
        if response.status_code == 200:
            return response.json().get('ips', [])
    except Exception as e:
        print(f"Error getting discovery IPs: {e}")
    return []

def get_devices():
    """Get all discovered devices."""
    try:
        response = requests.get(
            f"{BASE_URL}/api/v1/devices",
            headers=headers,
            verify=False,
            timeout=10
        )
        if response.status_code == 200:
            data = response.json()
            devices = []
            for edge in data.get('edges', []):
                node = edge.get('node', {})
                devices.append({
                    'model': node.get('softwareIdentity', {}).get('model', 'Unknown'),
                    'firmware': node.get('softwareIdentity', {}).get('firmwareVersion', 'N/A'),
                    'ip': node.get('communicationProtocol', {}).get('address', 'N/A'),
                    'state': node.get('deviceState', 'Unknown'),
                    'deviceId': node.get('hardwareIdentity', {}).get('deviceId', 'N/A'),
                    'serial': node.get('hardwareIdentity', {}).get('serialNumber', 'N/A'),
                })
            return devices
    except Exception as e:
        print(f"Error getting devices: {e}")
    return []

def format_duration(seconds):
    """Format duration in human-readable format."""
    if seconds < 60:
        return f"{int(seconds)}s"
    elif seconds < 3600:
        return f"{int(seconds/60)}m {int(seconds%60)}s"
    else:
        h = int(seconds / 3600)
        m = int((seconds % 3600) / 60)
        return f"{h}h {m}m"

def main():
    print("="*80)
    print("Shure System API - Device Discovery Monitor")
    print("="*80)
    print(f"API: {BASE_URL}")
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    # Get initial state
    discovery_ips = get_discovery_ips()
    print(f"Configured discovery IPs: {len(discovery_ips)}")
    
    devices = get_devices()
    print(f"Currently discovered devices: {len(devices)}")
    print()
    
    if devices:
        print("Current devices:")
        for device in devices[:10]:
            print(f"  {device['model']:20} {device['ip']:15} {device['state']:12} fw:{device['firmware']}")
        if len(devices) > 10:
            print(f"  ... and {len(devices) - 10} more")
        print()
    
    print("-"*80)
    print("Monitoring for new discoveries... (Ctrl+C to stop)")
    print("-"*80)
    print()
    
    last_device_count = len(devices)
    last_states = {}
    device_registry = {d['deviceId']: d for d in devices}
    check_count = 0
    start_time = time.time()
    
    try:
        while True:
            check_count += 1
            elapsed = time.time() - start_time
            
            # Get current devices
            current_devices = get_devices()
            current_count = len(current_devices)
            
            # Track states
            current_states = {}
            for device in current_devices:
                state = device['state']
                current_states[state] = current_states.get(state, 0) + 1
            
            # Detect changes
            new_devices = []
            state_changes = []
            
            for device in current_devices:
                device_id = device['deviceId']
                if device_id not in device_registry:
                    new_devices.append(device)
                    device_registry[device_id] = device
                elif device_registry[device_id]['state'] != device['state']:
                    old_state = device_registry[device_id]['state']
                    new_state = device['state']
                    state_changes.append((device, old_state, new_state))
                    device_registry[device_id] = device
            
            # Report changes
            timestamp = datetime.now().strftime("%H:%M:%S")
            
            if new_devices:
                print(f"[{timestamp}] 🆕 {len(new_devices)} NEW DEVICE(S) DISCOVERED:")
                for device in new_devices:
                    print(f"  ├─ {device['model']:20} @ {device['ip']:15}")
                    print(f"  │  State: {device['state']:12} Firmware: {device['firmware']:10} Serial: {device['serial']}")
                print()
            
            if state_changes:
                print(f"[{timestamp}] 🔄 STATE CHANGE(S):")
                for device, old_state, new_state in state_changes:
                    print(f"  ├─ {device['model']:20} @ {device['ip']:15}")
                    print(f"  │  {old_state} → {new_state}")
                print()
            
            # Periodic summary
            if check_count % 12 == 0 or current_count != last_device_count:
                state_summary = ", ".join([f"{state}:{cnt}" for state, cnt in sorted(current_states.items())])
                print(f"[{timestamp}] 📊 SUMMARY (after {format_duration(elapsed)}):")
                print(f"  Total devices: {current_count} ({state_summary})")
                print(f"  Discovery IPs: {len(discovery_ips)} configured")
                print(f"  Checks: {check_count}")
                print()
            
            last_device_count = current_count
            last_states = current_states
            
            # Wait before next check
            time.sleep(5)
            
    except KeyboardInterrupt:
        print()
        print("="*80)
        print("Monitoring stopped by user")
        print(f"Total runtime: {format_duration(time.time() - start_time)}")
        print(f"Final device count: {last_device_count}")
        if last_states:
            print("Final state breakdown:")
            for state, cnt in sorted(last_states.items()):
                print(f"  {state}: {cnt}")
        print("="*80)

if __name__ == '__main__':
    main()
