from typing import Any

from django import template

from micboard.services.hardware.wireless_unit_service import get_battery_percentage

register = template.Library()


@register.filter
def get_item(dictionary: Any, key: Any) -> Any:
    """Template filter to look up a key in a dictionary."""
    if not dictionary:
        return None
    return dictionary.get(key)


@register.filter
def wireless_battery_percentage(unit: Any) -> int | None:
    """Return a wireless unit's normalized battery percentage for templates."""
    if unit is None:
        return None
    return get_battery_percentage(unit)
