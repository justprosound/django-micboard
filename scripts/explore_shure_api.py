#!/usr/bin/env python3
"""Explore Shure System API endpoints to understand the real API structure."""

import json

import requests
from urllib3.exceptions import InsecureRequestWarning

requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

# Read the API key
with open("/mnt/c/ProgramData/Shure/SystemAPI/Standalone/Security/sharedkey.txt") as f:
    api_key = f.read().strip()

BASE_URL = "https://localhost:10000"
headers = {"x-api-key": api_key, "Authorization": f"Bearer {api_key}"}


def explore_endpoint(path, method="GET"):
    """Explore an API endpoint."""
    url = f"{BASE_URL}{path}"
    try:
        if method == "GET":
            resp = requests.get(url, headers=headers, verify=False, timeout=5)  # nosec B501 - SSL verification disabled for API exploration
        elif method == "POST":
            resp = requests.post(url, headers=headers, verify=False, timeout=5, json={})  # nosec B501 - SSL verification disabled for API exploration

        print(f"\n{'=' * 80}")
        print(f"{method} {path}")
        print(f"Status: {resp.status_code}")
        print(f"{'=' * 80}")

        if resp.status_code == 200:
            try:
                data = resp.json()
                print(json.dumps(data, indent=2)[:2000])  # Limit output
            except Exception:
                print(resp.text[:2000])
        else:
            print(f"Error: {resp.text[:500]}")

        return resp
    except Exception as e:
        print(f"Error exploring {path}: {e}")
        return None


# Explore key endpoints
print("=" * 80)
print("SHURE SYSTEM API EXPLORATION")
print("=" * 80)

endpoints = [
    "/api/v1",
    "/api/v1/devices",
    "/api/v1/config",
    "/api/v1/config/discovery",
    "/api/v1/config/discovery/ips",
    "/api/v1/system",
    "/api/v1/system/info",
]

for endpoint in endpoints:
    explore_endpoint(endpoint)

print("\n" + "=" * 80)
print("EXPLORATION COMPLETE")
print("=" * 80)
