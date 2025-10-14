from django.core.management.base import BaseCommand
from django.utils import timezone
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from micboard.shure_api_client import ShureSystemAPIClient
from micboard.models import Device, Transmitter
import time
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Poll Shure devices via System API and broadcast updates'

    def add_arguments(self, parser):
        parser.add_argument(
            '--interval',
            type=int,
            default=10,
            help='Polling interval in seconds (default: 10)'
        )
        parser.add_argument(
            '--no-broadcast',
            action='store_true',
            help='Disable WebSocket broadcasting'
        )

    def handle(self, *args, **options):
        interval = options['interval']
        broadcast = not options['no_broadcast']
        
        self.stdout.write(self.style.SUCCESS(
            f'Starting device polling via Shure System API (interval: {interval}s)'
        ))
        
        client = ShureSystemAPIClient()
        channel_layer = get_channel_layer() if broadcast else None

        while True:
            try:
                data = client.poll_all_devices()
                
                if data:
                    self.stdout.write(f"Polled {len(data)} devices")
                    updated_count = self.update_models(data)
                    
                    # Broadcast updates via WebSocket
                    if channel_layer:
                        async_to_sync(channel_layer.group_send)(
                            'micboard_updates',
                            {
                                'type': 'device_update',
                                'data': self.serialize_devices(data)
                            }
                        )
                    
                    self.stdout.write(self.style.SUCCESS(
                        f"Updated {updated_count} devices"
                    ))
                else:
                    self.stdout.write(self.style.WARNING("No device data received"))
                    
            except Exception as e:
                self.stderr.write(self.style.ERROR(f"Error polling devices: {e}"))
                logger.exception("Polling error")

            time.sleep(interval)

    def update_models(self, api_data):
        """Update Django models with API data"""
        updated_count = 0
        
        for device_id, device_data in api_data.items():
            try:
                # Get or create device
                device, created = Device.objects.update_or_create(
                    api_device_id=device_id,
                    defaults={
                        'ip': device_data.get('ip', ''),
                        'device_type': device_data.get('type', 'unknown'),
                        'name': device_data.get('name', ''),
                        'is_active': True,
                        'last_seen': timezone.now(),
                    }
                )
                
                # Update transmitter data for each channel
                for channel_info in device_data.get('channels', []):
                    channel_num = channel_info.get('channel', 0)
                    tx_data = channel_info.get('tx')
                    
                    if tx_data:
                        # Calculate slot number (you may need to adjust this logic)
                        slot = self.calculate_slot(device, channel_num)
                        
                        # Update device slot
                        device.channel = channel_num
                        device.slot = slot
                        device.save()
                        
                        Transmitter.objects.update_or_create(
                            device=device,
                            slot=slot,
                            defaults={
                                'battery': tx_data.get('battery', 255),
                                'audio_level': tx_data.get('audio_level', 0),
                                'rf_level': tx_data.get('rf_level', 0),
                                'frequency': tx_data.get('frequency', ''),
                                'antenna': tx_data.get('antenna', ''),
                                'tx_offset': tx_data.get('tx_offset', 255),
                                'quality': tx_data.get('quality', 255),
                                'runtime': tx_data.get('runtime', ''),
                                'status': tx_data.get('status', ''),
                                'name': tx_data.get('name', ''),
                                'name_raw': tx_data.get('name_raw', ''),
                            }
                        )
                
                updated_count += 1
                
            except Exception as e:
                logger.error(f"Error updating device {device_id}: {e}")
                continue
        
        return updated_count
    
    @staticmethod
    def calculate_slot(device, channel_num):
        """Calculate unique slot number for device/channel combination"""
        # Simple hash-based slot assignment
        # You may want to implement a more sophisticated slot management system
        base = hash(device.api_device_id) % 1000
        return base + channel_num
    
    def serialize_devices(self, api_data):
        """Serialize device data for WebSocket transmission"""
        serialized = []
        for device_id, device_data in api_data.items():
            serialized.append({
                'id': device_id,
                'ip': device_data.get('ip'),
                'type': device_data.get('type'),
                'name': device_data.get('name'),
                'channels': device_data.get('channels', []),
            })
        return serialized