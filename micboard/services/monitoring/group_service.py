"""Service for MonitoringGroup business logic."""


def get_active_users(group):
    """Return all active users in the group."""
    return group.users.filter(is_active=True)


def get_active_channels(group):
    """Return all active RF channels in the group."""
    return group.channels.filter(enabled=True)
