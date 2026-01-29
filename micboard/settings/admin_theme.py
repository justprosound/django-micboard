"""Unfold theme configuration for django-micboard.

To use this theme, install django-micboard[admin-theme] and update your settings.py:

INSTALLED_APPS = [
    'unfold',
    'django.contrib.admin',
    ...
    'micboard',
]

# Optional: customize unfold settings
UNFOLD = {
    "SITE_TITLE": "Micboard Admin",
    "SITE_HEADER": "Micboard",
    "SITE_SYMBOL": "mic",  # Font Awesome icon name
    "SHOW_HISTORY": True,
    "SHOW_VIEW_ON_SITE": True,
    "COLORS": {
        "primary": {
            "50": "250 250 250",
            "100": "244 244 245",
            "200": "228 228 231",
            "300": "212 212 216",
            "400": "161 161 170",
            "500": "113 113 122",
            "600": "82 82 91",
            "700": "63 63 70",
            "800": "39 39 42",
            "900": "24 24 27",
            "950": "9 9 11",
        },
    },
    "SIDEBAR": {
        "show_search": True,
        "show_all_applications": True,
        "navigation": [
            {
                "title": "Hardware",
                "separator": True,
                "items": [
                    {
                        "title": "Wireless Chassis",
                        "icon": "router",
                        "link": "/admin/micboard/wirelesschassis/",
                    },
                    {
                        "title": "Chargers",
                        "icon": "battery_charging_full",
                        "link": "/admin/micboard/charger/",
                    },
                ],
            },
            {
                "title": "Monitoring",
                "separator": True,
                "items": [
                    {
                        "title": "Performers",
                        "icon": "person",
                        "link": "/admin/micboard/performer/",
                    },
                    {
                        "title": "Alerts",
                        "icon": "warning",
                        "link": "/admin/micboard/alert/",
                    },
                ],
            },
        ],
    },
}
"""
