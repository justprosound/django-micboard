from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.views import View
from django.core.cache import cache
from django.utils import timezone
import json
import logging

from .models import Device, Group, DiscoveredDevice, MicboardConfig
from .shure_api_client import ShureSystemAPIClient
from .decorators import rate_limit_view, rate_limit_user

logger = logging.getLogger(__name__)


def index(request):
    """Main dashboard view"""
    context = {
        'device_count': Device.objects.filter(is_active=True).count(),
        'group_count': Group.objects.count(),
    }
    return render(request, 'micboard/index.html', context)


@rate_limit_view(max_requests=120, window_seconds=60)  # 2 requests per second
def data_json(request):
    """API endpoint for device data, similar to micboard_json"""
    # Try to get fresh data from cache first
    cached_data = cache.get('micboard_device_data')
    if cached_data:
        return JsonResponse(cached_data)
    
    devices = []
    for device in Device.objects.filter(is_active=True).select_related('transmitter'):
        transmitter = getattr(device, 'transmitter', None)
        device_data = {
            'ip': device.ip,
            'type': device.device_type,
            'channel': device.channel,
            'slot': device.slot,
            'name': device.name,
            'api_device_id': device.api_device_id,
        }
        if transmitter:
            device_data['tx'] = [{
                'battery': transmitter.battery,
                'audio_level': transmitter.audio_level,
                'rf_level': transmitter.rf_level,
                'frequency': transmitter.frequency,
                'antenna': transmitter.antenna,
                'tx_offset': transmitter.tx_offset,
                'quality': transmitter.quality,
                'runtime': transmitter.runtime,
                'status': transmitter.status,
                'name': transmitter.name,
                'name_raw': transmitter.name_raw,
            }]
        devices.append(device_data)

    # Add offline devices if any
    # For now, skip

    discovered = []
    for disc in DiscoveredDevice.objects.all():
        discovered.append({
            'ip': disc.ip,
            'type': disc.device_type,
            'channels': disc.channels,
        })

    config = {}
    for conf in MicboardConfig.objects.all():
        config[conf.key] = conf.value

    groups = []
    for group in Group.objects.all():
        groups.append({
            'group': group.group_number,
            'title': group.title,
            'slots': group.slots,
            'hide_charts': group.hide_charts,
        })

    data = {
        'receivers': devices,
        'url': request.build_absolute_uri('/'),  # Placeholder
        'gif': [],  # Placeholder
        'jpg': [],  # Placeholder
        'mp4': [],  # Placeholder
        'config': config,
        'discovered': discovered,
        'groups': groups,
    }

    return JsonResponse(data)


@method_decorator(csrf_exempt, name='dispatch')
class ConfigHandler(View):
    """Handle config updates"""
    def post(self, request):
        try:
            data = json.loads(request.body)
            for key, value in data.items():
                MicboardConfig.objects.update_or_create(
                    key=key,
                    defaults={'value': str(value)}
                )
            return JsonResponse({'success': True})
        except Exception as e:
            logger.error(f"Config update error: {e}")
            return JsonResponse({'error': str(e)}, status=400)


@method_decorator(csrf_exempt, name='dispatch')
class GroupUpdateHandler(View):
    """Handle group updates"""
    def post(self, request):
        try:
            data = json.loads(request.body)
            group_num = data.get('group')
            if group_num is not None:
                Group.objects.update_or_create(
                    group_number=group_num,
                    defaults={
                        'title': data.get('title', ''),
                        'slots': data.get('slots', []),
                        'hide_charts': data.get('hide_charts', False),
                    }
                )
            return JsonResponse({'success': True})
        except Exception as e:
            logger.error(f"Group update error: {e}")
            return JsonResponse({'error': str(e)}, status=400)


def about(request):
    """About page"""
    return render(request, 'micboard/about.html')


@rate_limit_view(max_requests=5, window_seconds=60)  # Discovery is expensive
def api_discover(request):
    """Trigger device discovery via Shure System API"""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    
    client = ShureSystemAPIClient()
    discovered = client.discover_devices()
    
    # Save discovered devices
    for device_data in discovered:
        DiscoveredDevice.objects.update_or_create(
            ip=device_data.get('ip_address', ''),
            defaults={
                'device_type': client._map_device_type(device_data.get('type', 'unknown')),
                'channels': device_data.get('channel_count', 0),
            }
        )
    
    return JsonResponse({
        'success': True,
        'discovered_count': len(discovered),
        'devices': discovered
    })


@rate_limit_view(max_requests=10, window_seconds=60)  # Limit refresh requests
def api_refresh(request):
    """Force refresh device data from Shure System API"""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    
    try:
        client = ShureSystemAPIClient()
        data = client.poll_all_devices()
        
        # Clear cache to force fresh data
        cache.delete('micboard_device_data')
        
        return JsonResponse({
            'success': True,
            'device_count': len(data),
            'timestamp': str(timezone.now())
        })
    except Exception as e:
        logger.error(f"Error refreshing data: {e}")
        return JsonResponse({'error': str(e)}, status=500)