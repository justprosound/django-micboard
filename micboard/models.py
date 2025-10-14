from django.db import models
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType

User = get_user_model()


class Device(models.Model):
    """Represents a configured Shure device (receiver)"""
    DEVICE_TYPES = [
        ('uhfr', 'UHF-R'),
        ('qlxd', 'QLX-D'),
        ('ulxd', 'ULX-D'),
        ('axtd', 'Axient Digital'),
        ('p10t', 'P10T'),
        ('offline', 'Offline'),
    ]

    # Shure System API fields
    api_device_id = models.CharField(max_length=100, unique=True, null=True, blank=True)
    ip = models.CharField(max_length=15)
    device_type = models.CharField(max_length=10, choices=DEVICE_TYPES)
    channel = models.IntegerField()
    slot = models.IntegerField(unique=True)
    name = models.CharField(max_length=100, blank=True)
    is_active = models.BooleanField(default=True)
    last_seen = models.DateTimeField(null=True, blank=True)
    
    # Location assignment (will be added via migration)
    # location = models.ForeignKey('Location', on_delete=models.SET_NULL, null=True, blank=True, related_name='devices')

    def __str__(self):
        return f"{self.device_type} - {self.ip}:{self.channel} (Slot {self.slot})"
    
    def get_assigned_users(self):
        """Get all users assigned to this device"""
        return User.objects.filter(device_assignments__device=self, device_assignments__is_active=True)
    
    def get_monitoring_groups(self):
        """Get all monitoring groups for this device"""
        return self.monitoring_groups.filter(is_active=True)


class Transmitter(models.Model):
    """Represents transmitter data for a slot"""
    device = models.OneToOneField(Device, on_delete=models.CASCADE, related_name='transmitter')
    slot = models.IntegerField()  # Transmitter slot number
    battery = models.IntegerField(default=255)
    audio_level = models.IntegerField(default=0)
    rf_level = models.IntegerField(default=0)
    frequency = models.CharField(max_length=20, blank=True)
    antenna = models.CharField(max_length=10, blank=True)
    tx_offset = models.IntegerField(default=255)
    quality = models.IntegerField(default=255)
    runtime = models.CharField(max_length=20, blank=True)
    status = models.CharField(max_length=50, blank=True)
    name = models.CharField(max_length=100, blank=True)
    name_raw = models.CharField(max_length=100, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Transmitter for Slot {self.slot}"


class Group(models.Model):
    """Represents a group of slots"""
    group_number = models.IntegerField(unique=True)
    title = models.CharField(max_length=100)
    slots = models.JSONField()  # List of slot numbers
    hide_charts = models.BooleanField(default=False)

    def __str__(self):
        return f"Group {self.group_number}: {self.title}"


class DiscoveredDevice(models.Model):
    """Represents discovered devices on the network"""
    ip = models.CharField(max_length=15)
    device_type = models.CharField(max_length=10)
    channels = models.IntegerField()
    discovered_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.device_type} at {self.ip}"


class MicboardConfig(models.Model):
    """Global configuration settings"""
    key = models.CharField(max_length=100, unique=True)
    value = models.TextField()

    class Meta:
        verbose_name = "Micboard Configuration"
        verbose_name_plural = "Micboard Configurations"

    def __str__(self):
        return f"{self.key}: {self.value}"


class Location(models.Model):
    """
    Represents a physical location (building/room).
    Can be linked to your existing location model using GenericForeignKey
    or you can add a ForeignKey to your specific model.
    """
    # Option 1: Generic foreign key to any location model
    content_type = models.ForeignKey(
        ContentType, 
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        help_text="Link to your external location model (e.g., Building, Room)"
    )
    object_id = models.PositiveIntegerField(null=True, blank=True)
    external_location = GenericForeignKey('content_type', 'object_id')
    
    # Option 2: Simple location fields (if you don't have an external model)
    building = models.CharField(max_length=100, blank=True)
    room = models.CharField(max_length=100, blank=True)
    floor = models.CharField(max_length=50, blank=True)
    
    # Common fields
    name = models.CharField(max_length=200, help_text="Display name for this location")
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Location"
        verbose_name_plural = "Locations"
        ordering = ['building', 'room']

    def __str__(self):
        if self.building and self.room:
            return f"{self.building} - {self.room}"
        return self.name


class MonitoringGroup(models.Model):
    """
    Represents a group of users who monitor specific devices together.
    Useful for organizing teams (e.g., "Theater Tech Team", "Conference Room A Staff")
    """
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    location = models.ForeignKey(
        Location, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='monitoring_groups'
    )
    users = models.ManyToManyField(
        User,
        related_name='monitoring_groups',
        blank=True,
        help_text="Users who are part of this monitoring group"
    )
    devices = models.ManyToManyField(
        Device,
        related_name='monitoring_groups',
        blank=True,
        help_text="Devices assigned to this monitoring group"
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Monitoring Group"
        verbose_name_plural = "Monitoring Groups"
        ordering = ['name']

    def __str__(self):
        return self.name


class DeviceAssignment(models.Model):
    """
    Individual device/channel assignments to users.
    Allows fine-grained control over who monitors what.
    """
    PRIORITY_CHOICES = [
        ('low', 'Low'),
        ('normal', 'Normal'),
        ('high', 'High'),
        ('critical', 'Critical'),
    ]

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='device_assignments'
    )
    device = models.ForeignKey(
        Device,
        on_delete=models.CASCADE,
        related_name='assignments'
    )
    location = models.ForeignKey(
        Location,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='device_assignments',
        help_text="Physical location of this device"
    )
    monitoring_group = models.ForeignKey(
        MonitoringGroup,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='device_assignments',
        help_text="Optional monitoring group this assignment belongs to"
    )
    
    # Assignment metadata
    priority = models.CharField(
        max_length=10,
        choices=PRIORITY_CHOICES,
        default='normal',
        help_text="Priority level for this assignment"
    )
    notes = models.TextField(
        blank=True,
        help_text="Notes about this assignment (e.g., 'Lead vocalist mic')"
    )
    is_active = models.BooleanField(default=True)
    
    # Alert preferences for this specific assignment
    alert_on_battery_low = models.BooleanField(
        default=True,
        help_text="Alert when battery is low"
    )
    alert_on_signal_loss = models.BooleanField(
        default=True,
        help_text="Alert when RF signal is lost"
    )
    alert_on_audio_low = models.BooleanField(
        default=False,
        help_text="Alert when audio level is too low"
    )
    alert_on_device_offline = models.BooleanField(
        default=True,
        help_text="Alert when device goes offline"
    )
    
    # Timestamps
    assigned_at = models.DateTimeField(auto_now_add=True)
    assigned_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assignments_created',
        help_text="User who created this assignment"
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Device Assignment"
        verbose_name_plural = "Device Assignments"
        ordering = ['-priority', 'device']
        unique_together = [['user', 'device']]  # One assignment per user per device

    def __str__(self):
        return f"{self.user.username} -> {self.device} ({self.priority})"


class UserAlertPreference(models.Model):
    """
    Global alert preferences per user.
    Device-specific preferences override these defaults.
    """
    NOTIFICATION_METHODS = [
        ('email', 'Email'),
        ('websocket', 'WebSocket (Real-time)'),
        ('both', 'Email + WebSocket'),
    ]

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='alert_preferences'
    )
    
    # Notification delivery
    notification_method = models.CharField(
        max_length=20,
        choices=NOTIFICATION_METHODS,
        default='both'
    )
    email_address = models.EmailField(
        blank=True,
        help_text="Override user's default email for alerts"
    )
    
    # Global alert settings (defaults)
    default_alert_battery_low = models.BooleanField(default=True)
    default_alert_signal_loss = models.BooleanField(default=True)
    default_alert_audio_low = models.BooleanField(default=False)
    default_alert_device_offline = models.BooleanField(default=True)
    
    # Battery thresholds
    battery_low_threshold = models.IntegerField(
        default=20,
        help_text="Alert when battery percentage drops below this value"
    )
    battery_critical_threshold = models.IntegerField(
        default=10,
        help_text="Critical alert threshold"
    )
    
    # Quiet hours
    quiet_hours_enabled = models.BooleanField(
        default=False,
        help_text="Enable quiet hours (no alerts during specified times)"
    )
    quiet_hours_start = models.TimeField(
        null=True,
        blank=True,
        help_text="Start of quiet hours (e.g., 22:00)"
    )
    quiet_hours_end = models.TimeField(
        null=True,
        blank=True,
        help_text="End of quiet hours (e.g., 08:00)"
    )
    
    # Alert rate limiting
    min_alert_interval = models.IntegerField(
        default=5,
        help_text="Minimum minutes between alerts for the same device"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "User Alert Preference"
        verbose_name_plural = "User Alert Preferences"

    def __str__(self):
        return f"Alert preferences for {self.user.username}"


class Alert(models.Model):
    """
    Stores alert history for auditing and tracking.
    """
    ALERT_TYPES = [
        ('battery_low', 'Battery Low'),
        ('battery_critical', 'Battery Critical'),
        ('signal_loss', 'Signal Loss'),
        ('audio_low', 'Audio Low'),
        ('device_offline', 'Device Offline'),
        ('device_online', 'Device Online'),
    ]
    
    ALERT_STATUS = [
        ('pending', 'Pending'),
        ('sent', 'Sent'),
        ('acknowledged', 'Acknowledged'),
        ('resolved', 'Resolved'),
        ('failed', 'Failed'),
    ]

    device = models.ForeignKey(
        Device,
        on_delete=models.CASCADE,
        related_name='alerts'
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='alerts'
    )
    assignment = models.ForeignKey(
        DeviceAssignment,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='alerts'
    )
    
    alert_type = models.CharField(max_length=20, choices=ALERT_TYPES)
    status = models.CharField(max_length=20, choices=ALERT_STATUS, default='pending')
    message = models.TextField()
    
    # Alert context data
    device_data = models.JSONField(
        null=True,
        blank=True,
        help_text="Snapshot of device state when alert was triggered"
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Alert"
        verbose_name_plural = "Alerts"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['device', 'alert_type', 'status']),
            models.Index(fields=['user', 'status', '-created_at']),
        ]

    def __str__(self):
        return f"{self.alert_type} - {self.device} ({self.status})"