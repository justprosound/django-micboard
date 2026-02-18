"""Service for performer assignment alert preferences."""


def get_alert_preferences(assignment) -> dict[str, bool]:
    """Get alert preferences for a performer assignment instance."""
    return {
        "battery_low": assignment.alert_on_battery_low,
        "signal_loss": assignment.alert_on_signal_loss,
        "audio_low": assignment.alert_on_audio_low,
        "hardware_offline": assignment.alert_on_hardware_offline,
    }
