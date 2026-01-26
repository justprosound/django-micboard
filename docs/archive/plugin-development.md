# Plugin Development Guide

This guide explains how to develop plugins for additional wireless microphone manufacturers in Django Micboard.

## Overview

Django Micboard uses a plugin architecture to support multiple wireless microphone manufacturers. Each manufacturer is implemented as a plugin that inherits from the `ManufacturerPlugin` abstract base class.

## Plugin Architecture

### Base Plugin Class

All manufacturer plugins must inherit from `ManufacturerPlugin` located in `micboard/plugins/base.py`:

```python
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any
from django.db import models

class ManufacturerPlugin(ABC):
    """Abstract base class for manufacturer plugins"""

    @property
    @abstractmethod
    def manufacturer_code(self) -> str:
        """Unique code identifying the manufacturer (e.g., 'shure', 'sennheiser')"""
        pass

    @property
    @abstractmethod
    def manufacturer_name(self) -> str:
        """Human-readable manufacturer name"""
        pass

    @abstractmethod
    def get_devices(self) -> List[Dict[str, Any]]:
        """Retrieve device information from the manufacturer's API"""
        pass

    @abstractmethod
    def transform_device_data(self, device_data: Dict[str, Any]) -> Dict[str, Any]:
        """Transform raw device data into Micboard's internal format"""
        pass

    @abstractmethod
    def check_health(self) -> Dict[str, Any]:
        """Check the health/status of the manufacturer's API"""
        pass

### Health Check Contract

Plugins must implement `check_health()` returning a dictionary with at least the `status` key. Example:

```python
return {
    'status': 'healthy'|'unhealthy',
    'status_code': 200,
    'error': None,
}
```

This contract is used by the UI and the admin context processor to show per-manufacturer health in the footer and in administrative dashboards.

### Admin Hardware Layout Implications

Plugins should ensure device discovery and channel data include frequency information when available. The Admin hardware layout view focuses on `Receiver -> Channel -> Frequency`, so plugin transformers should populate `frequency` and `channels` fields in transformed data where possible.
```

### Plugin Registration

Plugins are automatically discovered and loaded by the `get_manufacturer_plugin()` function in `micboard/plugins/__init__.py`. To register a new plugin:

1. Create a plugin class inheriting from `ManufacturerPlugin`
2. Place it in a module under `micboard/plugins/`
3. Ensure the module is imported in `micboard/plugins/__init__.py`

## Developing a New Plugin

### Step 1: Create Plugin Directory Structure

Create a new directory under `micboard/manufacturers/` for your manufacturer:

```
micboard/manufacturers/
├── shure/          # Existing Shure plugin
│   ├── __init__.py
│   └── plugin.py
└── your_manufacturer/
    ├── __init__.py
    └── plugin.py
```

### Step 2: Implement the Plugin Class

Create `micboard/plugins/your_manufacturer/plugin.py`:

```python
from typing import Dict, List, Optional, Any
from micboard.plugins.base import ManufacturerPlugin
import requests

class YourManufacturerPlugin(ManufacturerPlugin):
    """Plugin for Your Manufacturer wireless systems"""

    @property
    def manufacturer_code(self) -> str:
        return "your_manufacturer"

    @property
    def manufacturer_name(self) -> str:
        return "Your Manufacturer Name"

    def __init__(self, manufacturer: 'Manufacturer'):
        self.manufacturer = manufacturer
        self.api_url = manufacturer.config.get('api_url')
        self.api_key = manufacturer.config.get('api_key')
        # Initialize any other required attributes

    def get_devices(self) -> List[Dict[str, Any]]:
        """Retrieve device information from Your Manufacturer API"""
        try:
            response = requests.get(
                f"{self.api_url}/devices",
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=30
            )
            response.raise_for_status()
            return response.json().get('devices', [])
        except requests.RequestException as e:
            raise Exception(f"Failed to retrieve devices from {self.manufacturer_name}: {e}")

    def transform_device_data(self, device_data: Dict[str, Any]) -> Dict[str, Any]:
        """Transform Your Manufacturer device data to Micboard format"""
        return {
            'type': device_data.get('model', 'unknown'),
            'ip': device_data.get('ip_address'),
            'channels': device_data.get('channel_count', 0),
            # Add other fields as needed
        }

    def check_health(self) -> Dict[str, Any]:
        """Check Your Manufacturer API health"""
        try:
            response = requests.get(
                f"{self.api_url}/health",
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=10
            )
            return {
                'status': 'healthy' if response.status_code == 200 else 'unhealthy',
                'response_time': response.elapsed.total_seconds(),
                'details': response.json() if response.status_code == 200 else None
            }
        except requests.RequestException as e:
            return {
                'status': 'unhealthy',
                'error': str(e)
            }
```

### Step 3: Create Package Init File

Create `micboard/plugins/your_manufacturer/__init__.py`:

```python
from .plugin import YourManufacturerPlugin

__all__ = ['YourManufacturerPlugin']
```

### Step 4: Register the Plugin

Update `micboard/plugins/__init__.py` to import your plugin:

```python
# ... existing imports ...
from .your_manufacturer import YourManufacturerPlugin

# ... existing plugin registry ...
_PLUGIN_CLASSES = {
    # ... existing plugins ...
    'your_manufacturer': YourManufacturerPlugin,
}
```

## Configuration

### Manufacturer Configuration

Each manufacturer needs to be configured in the database with:

- **code**: Unique identifier (matches `manufacturer_code` property)
- **name**: Human-readable name
- **config**: JSON configuration object with API credentials and settings

Example configuration:

```json
{
  "api_url": "https://api.yourmanufacturer.com/v1",
  "api_key": "your-api-key-here",
  "timeout": 30,
  "additional_setting": "value"
}
```

### Micboard Configuration

Manufacturer-specific settings can be stored in `MicboardConfig` with `manufacturer` foreign key set.

## Data Transformation

### Required Device Fields

The `transform_device_data()` method must return a dictionary with these fields:

- **type**: Device model/type (string)
- **ip**: IP address (string)
- **channels**: Number of channels (integer)

### Optional Device Fields

Additional fields can be included for manufacturer-specific features:

- **firmware**: Firmware version
- **serial**: Serial number
- **capabilities**: List of device capabilities

## Testing

### Unit Tests

Create comprehensive unit tests for your plugin:

```python
import unittest
from unittest.mock import Mock, patch
from micboard.plugins.your_manufacturer import YourManufacturerPlugin
from micboard.models.devices import Manufacturer

class YourManufacturerPluginTest(unittest.TestCase):

    def setUp(self):
        self.manufacturer = Manufacturer.objects.create(
            code="your_manufacturer",
            name="Your Manufacturer",
            config={"api_url": "https://api.test.com", "api_key": "test-key"}
        )
        self.plugin = YourManufacturerPlugin(self.manufacturer)

    @patch('requests.get')
    def test_get_devices_success(self, mock_get):
        mock_response = Mock()
        mock_response.json.return_value = {
            'devices': [
                {'model': 'RX-1', 'ip_address': '192.168.1.100', 'channel_count': 2}
            ]
        }
        mock_get.return_value = mock_response

        devices = self.plugin.get_devices()
        self.assertEqual(len(devices), 1)
        self.assertEqual(devices[0]['model'], 'RX-1')

    def test_transform_device_data(self):
        device_data = {
            'model': 'RX-1',
            'ip_address': '192.168.1.100',
            'channel_count': 2
        }

        result = self.plugin.transform_device_data(device_data)
        expected = {
            'type': 'RX-1',
            'ip': '192.168.1.100',
            'channels': 2
        }
        self.assertEqual(result, expected)
```

### Integration Tests

Test the plugin with the full Micboard system:

- API discovery endpoints
- Data polling
- Health checks
- Manufacturer filtering

## Error Handling

### Network Errors

Handle network timeouts, connection failures, and API errors gracefully:

```python
def get_devices(self) -> List[Dict[str, Any]]:
    try:
        response = requests.get(self.api_url, timeout=self.timeout)
        response.raise_for_status()
        return response.json()
    except requests.Timeout:
        raise Exception(f"Timeout connecting to {self.manufacturer_name} API")
    except requests.ConnectionError:
        raise Exception(f"Connection failed to {self.manufacturer_name} API")
    except requests.HTTPError as e:
        raise Exception(f"HTTP error from {self.manufacturer_name} API: {e}")
```

### Data Validation

Validate API responses and handle malformed data:

```python
def get_devices(self) -> List[Dict[str, Any]]:
    response = requests.get(f"{self.api_url}/devices")
    data = response.json()

    if not isinstance(data, dict) or 'devices' not in data:
        raise Exception("Invalid API response format")

    devices = data['devices']
    if not isinstance(devices, list):
        raise Exception("Devices data is not a list")

    return devices
```

## Best Practices

### Configuration Management

- Store sensitive credentials securely
- Use environment variables for secrets
- Validate configuration on plugin initialization

### Error Messages

- Provide clear, actionable error messages
- Include manufacturer name in error messages
- Log detailed errors for debugging

### Performance

- Implement appropriate timeouts
- Cache API responses when possible
- Use connection pooling for multiple requests

### Security

- Use HTTPS for all API communications
- Validate SSL certificates
- Implement proper authentication
- Never log sensitive credentials

## Example: Complete Sennheiser Plugin

See `micboard/plugins/shure/` for a complete working example. The Sennheiser plugin would follow the same pattern but with Sennheiser-specific API calls and data transformations.
