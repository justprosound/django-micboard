#!/usr/bin/env python
"""Quick test of Shure System API connectivity."""
import os
import sys
import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

BASE_URL = os.environ.get("MICBOARD_SHURE_API_BASE_URL", "https://localhost:10000")
SHARED_KEY = os.environ.get("MICBOARD_SHURE_API_SHARED_KEY")

if not SHARED_KEY:
    print("Error: MICBOARD_SHURE_API_SHARED_KEY not set")
    sys.exit(1)

print(f"Testing connection to: {BASE_URL}")
print(f"Shared Key (first 20 chars): {SHARED_KEY[:20]}...")

headers = {
    "x-api-key": SHARED_KEY,
    "Accept": "application/json"
}

# Test 1: GET current discovery IPs
print("\n1. Getting current discovery IPs...")
try:
    response = requests.get(
        f"{BASE_URL}/api/v1/config/discovery/ips",
        headers=headers,
        verify=False,
        timeout=10
    )
    print(f"   Status: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        print(f"   Current IPs: {len(data.get('ips', []))}")
    else:
        print(f"   Response: {response.text[:200]}")
except Exception as e:
    print(f"   Error: {e}")

# Test 2: GET devices
print("\n2. Getting devices...")
try:
    response = requests.get(
        f"{BASE_URL}/api/v1/devices",
        headers=headers,
        verify=False,
        timeout=10
    )
    print(f"   Status: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        edges = data.get('edges', [])
        print(f"   Devices found: {len(edges)}")
        for edge in edges[:3]:
            node = edge.get('node', {})
            model = node.get('softwareIdentity', {}).get('model', 'Unknown')
            ip = node.get('communicationProtocol', {}).get('address', 'N/A')
            state = node.get('deviceState', 'Unknown')
            print(f"     - {model:20} {ip:15} ({state})")
    else:
        print(f"   Response: {response.text[:200]}")
except Exception as e:
    print(f"   Error: {e}")

# Test 3: Add a test IP
print("\n3. Testing ADD endpoint with sample IP...")
try:
    response = requests.patch(
        f"{BASE_URL}/api/v1/config/discovery/ips/add",
        json={"ips": ["172.21.2.140"]},
        headers={**headers, "Content-Type": "application/json"},
        verify=False,
        timeout=10
    )
    print(f"   Status: {response.status_code}")
    if response.status_code == 202:
        print("   ✓ IP scheduled to be added!")
    else:
        print(f"   Response: {response.text[:200]}")
except Exception as e:
    print(f"   Error: {e}")

print("\nTest complete!")
