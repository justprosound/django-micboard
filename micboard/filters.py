from __future__ import annotations

from micboard.utils.dependencies import HAS_DJANGO_FILTER

HAS_DJANGO_FILTERS = HAS_DJANGO_FILTER

if HAS_DJANGO_FILTER:
    import django_filters

    from micboard.models import WirelessChassis, WirelessUnit

    class WirelessChassisFilter(django_filters.FilterSet):
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

    class WirelessUnitFilter(django_filters.FilterSet):
        """FilterSet for WirelessUnits."""

        class Meta:
            model = WirelessUnit
            fields = {
                "device_type": ["exact"],
                "base_chassis__id": ["exact"],
            }
else:

    class WirelessChassisFilter:
        pass

    class WirelessUnitFilter:
        pass
