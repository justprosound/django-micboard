import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from django.conf import settings
from django.core.cache import cache
import logging
import time
from typing import Dict, List, Optional, Any
from functools import wraps

logger = logging.getLogger(__name__)


def rate_limit(calls_per_second: float = 10.0):
    """
    Decorator to rate limit method calls.
    Uses token bucket algorithm with Django cache.
    """
    def decorator(func):
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            cache_key = f'rate_limit_{self.__class__.__name__}_{func.__name__}'
            min_interval = 1.0 / calls_per_second
            
            last_call = cache.get(cache_key, 0)
            now = time.time()
            time_since_last = now - last_call
            
            if time_since_last < min_interval:
                sleep_time = min_interval - time_since_last
                logger.debug(f"Rate limiting {func.__name__}: sleeping {sleep_time:.3f}s")
                time.sleep(sleep_time)
                now = time.time()
            
            cache.set(cache_key, now, timeout=60)
            return func(self, *args, **kwargs)
        return wrapper
    return decorator


class ShureSystemAPIClient:
    """Client for interacting with Shure System API"""
    
    def __init__(self):
        config = getattr(settings, 'MICBOARD_CONFIG', {})
        self.base_url = config.get('SHURE_API_BASE_URL', 'http://localhost:8080').rstrip('/')
        self.username = config.get('SHURE_API_USERNAME')
        self.password = config.get('SHURE_API_PASSWORD')
        self.timeout = config.get('SHURE_API_TIMEOUT', 10)
        self.verify_ssl = config.get('SHURE_API_VERIFY_SSL', True)
        
        # Retry configuration
        self.max_retries = config.get('SHURE_API_MAX_RETRIES', 3)
        self.retry_backoff = config.get('SHURE_API_RETRY_BACKOFF', 0.5)  # seconds
        self.retry_status_codes = config.get('SHURE_API_RETRY_STATUS_CODES', [429, 500, 502, 503, 504])
        
        # Create session with retry strategy
        self.session = requests.Session()
        
        # Configure retry strategy
        retry_strategy = Retry(
            total=self.max_retries,
            backoff_factor=self.retry_backoff,
            status_forcelist=self.retry_status_codes,
            allowed_methods=["HEAD", "GET", "PUT", "DELETE", "OPTIONS", "TRACE", "POST"]
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        
        if self.username and self.password:
            self.session.auth = (self.username, self.password)
    
    def _make_request(self, method: str, endpoint: str, **kwargs) -> Optional[Any]:
        """Make HTTP request with error handling"""
        url = f"{self.base_url}{endpoint}"
        kwargs.setdefault('timeout', self.timeout)
        kwargs.setdefault('verify', self.verify_ssl)
        
        try:
            response = self.session.request(method, url, **kwargs)
            response.raise_for_status()
            return response.json() if response.content else None
        except requests.RequestException as e:
            logger.error(f"API request failed: {method} {url} - {e}")
            return None
    
    @rate_limit(calls_per_second=5.0)
    def get_devices(self) -> List[Dict]:
        """Get list of all devices from Shure System API"""
        result = self._make_request('GET', '/api/v1/devices')
        return result if isinstance(result, list) else []
    
    @rate_limit(calls_per_second=10.0)
    def get_device(self, device_id: str) -> Optional[Dict]:
        """Get detailed data for a specific device"""
        return self._make_request('GET', f'/api/v1/devices/{device_id}')
    
    @rate_limit(calls_per_second=10.0)
    def get_device_channels(self, device_id: str) -> List[Dict]:
        """Get channel data for a device"""
        result = self._make_request('GET', f'/api/v1/devices/{device_id}/channels')
        return result if isinstance(result, list) else []
    
    @rate_limit(calls_per_second=10.0)
    def get_transmitter_data(self, device_id: str, channel: int) -> Optional[Dict]:
        """Get transmitter data for a specific channel"""
        return self._make_request('GET', f'/api/v1/devices/{device_id}/channels/{channel}/tx')
    
    @rate_limit(calls_per_second=2.0)  # Discovery is more expensive
    def discover_devices(self) -> List[Dict]:
        """Discover devices on the network"""
        result = self._make_request('POST', '/api/v1/discover')
        return result if isinstance(result, list) else []
    
    def poll_all_devices(self) -> Dict[str, Dict]:
        """Poll all devices and return aggregated data with transmitter info"""
        devices = self.get_devices()
        data = {}
        
        for device in devices:
            device_id = device.get('id')
            if not device_id:
                continue
            
            device_data = self.get_device(device_id)
            if not device_data:
                continue
            
            # Get channel/transmitter data
            channels = self.get_device_channels(device_id)
            device_data['channels'] = channels
            
            # Transform to micboard format
            transformed = self._transform_device_data(device_data)
            if transformed:
                data[device_id] = transformed
        
        return data
    
    def _transform_device_data(self, api_data: Dict) -> Optional[Dict]:
        """Transform Shure API format to micboard format"""
        try:
            device_id = api_data.get('id')
            device_type = self._map_device_type(api_data.get('type', 'unknown'))
            
            result = {
                'id': device_id,
                'ip': api_data.get('ip_address', ''),
                'type': device_type,
                'name': api_data.get('model_name', ''),
                'firmware': api_data.get('firmware_version', ''),
                'channels': []
            }
            
            # Transform channel data
            for channel_data in api_data.get('channels', []):
                channel_num = channel_data.get('channel', 0)
                tx_data = channel_data.get('tx', {})
                
                if tx_data:
                    result['channels'].append({
                        'channel': channel_num,
                        'tx': {
                            'battery': tx_data.get('battery_bars', 255),
                            'battery_charge': tx_data.get('battery_charge', 0),
                            'audio_level': tx_data.get('audio_level', 0),
                            'rf_level': tx_data.get('rf_level', 0),
                            'frequency': tx_data.get('frequency', ''),
                            'antenna': tx_data.get('antenna', ''),
                            'tx_offset': tx_data.get('tx_offset', 255),
                            'quality': tx_data.get('audio_quality', 255),
                            'runtime': self._format_runtime(tx_data.get('battery_runtime_minutes')),
                            'status': tx_data.get('status', ''),
                            'name': tx_data.get('name', ''),
                            'name_raw': tx_data.get('name', ''),
                        }
                    })
            
            return result
        except Exception as e:
            logger.error(f"Error transforming device data: {e}")
            return None
    
    @staticmethod
    def _map_device_type(api_type: str) -> str:
        """Map Shure API device types to micboard types"""
        type_map = {
            'UHFR': 'uhfr',
            'QLXD': 'qlxd',
            'ULXD': 'ulxd',
            'AXIENT_DIGITAL': 'axtd',
            'P10T': 'p10t',
        }
        return type_map.get(api_type.upper(), 'unknown')
    
    @staticmethod
    def _format_runtime(minutes: Optional[int]) -> str:
        """Format battery runtime from minutes to HH:MM format"""
        if minutes is None or minutes < 0:
            return ''
        hours = minutes // 60
        mins = minutes % 60
        return f"{hours:02d}:{mins:02d}"