from __future__ import annotations

from typing import Any

from micboard.utils.dependencies import HAS_DJANGO_FILTER


def _build_filter_classes() -> tuple[Any, Any]:
    if not HAS_DJANGO_FILTER:

        class UnavailableFilter:
            """Placeholder used only while the optional django-filter extra is absent."""

        return UnavailableFilter, UnavailableFilter

    import django_filters

    from micboard.models.hardware.wireless_chassis import WirelessChassis
    from micboard.models.hardware.wireless_unit import WirelessUnit

    class ChassisFilter(django_filters.FilterSet):
        """FilterSet for WirelessChassis (Receivers)."""

        class Meta:
            model = WirelessChassis
            fields = {
                "manufacturer__code": ["exact"],
                "model": ["icontains"],
                "is_online": ["exact"],
                "role": ["exact"],
                "location__building__name": ["exact"],
                "location__room__name": ["exact"],
            }

    class UnitFilter(django_filters.FilterSet):
        """FilterSet for WirelessUnits."""

        class Meta:
            model = WirelessUnit
            fields = {
                "device_type": ["exact"],
                "base_chassis__id": ["exact"],
            }

    return ChassisFilter, UnitFilter


WirelessChassisFilter, WirelessUnitFilter = _build_filter_classes()
