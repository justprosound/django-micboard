from django.contrib import admin

from .models import (
    Device, Transmitter, Group, DiscoveredDevice, MicboardConfig,
    Location, MonitoringGroup, DeviceAssignment, UserAlertPreference, Alert
)

@admin.register(Device)
class DeviceAdmin(admin.ModelAdmin):
    list_display = ['ip', 'device_type', 'channel', 'slot', 'name', 'is_active', 'last_seen']
    list_filter = ['device_type', 'is_active']
    search_fields = ['ip', 'name', 'api_device_id']
    readonly_fields = ['api_device_id', 'last_seen']
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related().prefetch_related('monitoring_groups', 'assignments')

@admin.register(Transmitter)
class TransmitterAdmin(admin.ModelAdmin):
    list_display = ['device', 'slot', 'battery', 'audio_level', 'frequency', 'status']
    list_filter = ['status']
    readonly_fields = ['updated_at']

@admin.register(Group)
class GroupAdmin(admin.ModelAdmin):
    list_display = ['group_number', 'title']

@admin.register(DiscoveredDevice)
class DiscoveredDeviceAdmin(admin.ModelAdmin):
    list_display = ['ip', 'device_type', 'channels', 'discovered_at']

@admin.register(MicboardConfig)
class MicboardConfigAdmin(admin.ModelAdmin):
    list_display = ['key', 'value']


@admin.register(Location)
class LocationAdmin(admin.ModelAdmin):
    list_display = ['name', 'building', 'room', 'floor', 'is_active']
    list_filter = ['is_active', 'building']
    search_fields = ['name', 'building', 'room', 'description']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(MonitoringGroup)
class MonitoringGroupAdmin(admin.ModelAdmin):
    list_display = ['name', 'location', 'is_active', 'user_count', 'device_count']
    list_filter = ['is_active', 'location']
    search_fields = ['name', 'description']
    filter_horizontal = ['users', 'devices']
    readonly_fields = ['created_at', 'updated_at']
    
    def user_count(self, obj):
        return obj.users.count()
    user_count.short_description = 'Users'
    
    def device_count(self, obj):
        return obj.devices.count()
    device_count.short_description = 'Devices'


@admin.register(DeviceAssignment)
class DeviceAssignmentAdmin(admin.ModelAdmin):
    list_display = ['user', 'device', 'location', 'priority', 'is_active', 'assigned_at']
    list_filter = ['is_active', 'priority', 'location', 'monitoring_group']
    search_fields = ['user__username', 'user__email', 'device__name', 'device__ip', 'notes']
    readonly_fields = ['assigned_at', 'assigned_by', 'updated_at']
    autocomplete_fields = ['user', 'device', 'location', 'monitoring_group']
    fieldsets = (
        ('Assignment', {
            'fields': ('user', 'device', 'location', 'monitoring_group', 'priority', 'is_active')
        }),
        ('Alert Preferences', {
            'fields': (
                'alert_on_battery_low',
                'alert_on_signal_loss',
                'alert_on_audio_low',
                'alert_on_device_offline',
            ),
            'classes': ('collapse',),
        }),
        ('Notes', {
            'fields': ('notes',),
        }),
        ('Metadata', {
            'fields': ('assigned_at', 'assigned_by', 'updated_at'),
            'classes': ('collapse',),
        }),
    )
    
    def save_model(self, request, obj, form, change):
        if not change:  # Only set assigned_by on creation
            obj.assigned_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(UserAlertPreference)
class UserAlertPreferenceAdmin(admin.ModelAdmin):
    list_display = ['user', 'notification_method', 'battery_low_threshold', 'quiet_hours_enabled']
    list_filter = ['notification_method', 'quiet_hours_enabled']
    search_fields = ['user__username', 'user__email']
    readonly_fields = ['created_at', 'updated_at']
    fieldsets = (
        ('User', {
            'fields': ('user',)
        }),
        ('Notification Settings', {
            'fields': ('notification_method', 'email_address', 'min_alert_interval'),
        }),
        ('Default Alert Types', {
            'fields': (
                'default_alert_battery_low',
                'default_alert_signal_loss',
                'default_alert_audio_low',
                'default_alert_device_offline',
            ),
        }),
        ('Battery Thresholds', {
            'fields': ('battery_low_threshold', 'battery_critical_threshold'),
        }),
        ('Quiet Hours', {
            'fields': ('quiet_hours_enabled', 'quiet_hours_start', 'quiet_hours_end'),
            'classes': ('collapse',),
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )


@admin.register(Alert)
class AlertAdmin(admin.ModelAdmin):
    list_display = ['device', 'user', 'alert_type', 'status', 'created_at', 'acknowledged_at']
    list_filter = ['alert_type', 'status', 'created_at']
    search_fields = ['device__name', 'device__ip', 'user__username', 'message']
    readonly_fields = ['created_at', 'sent_at', 'acknowledged_at', 'resolved_at', 'device_data']
    date_hierarchy = 'created_at'
    
    fieldsets = (
        ('Alert Information', {
            'fields': ('device', 'user', 'assignment', 'alert_type', 'status', 'message')
        }),
        ('Device Context', {
            'fields': ('device_data',),
            'classes': ('collapse',),
        }),
        ('Timestamps', {
            'fields': ('created_at', 'sent_at', 'acknowledged_at', 'resolved_at'),
        }),
    )
    
    def has_add_permission(self, request):
        # Alerts should be created programmatically, not manually
        return False