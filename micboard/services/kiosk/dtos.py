"""Typed, template-safe DisplayWall snapshots."""

from __future__ import annotations

from micboard.services.shared.base_dto import PydanticBaseDTO

MAX_KIOSK_SECTIONS = 16
MAX_KIOSK_CHARGERS_PER_SECTION = 32
MAX_KIOSK_SLOTS_PER_CHARGER = 32
MAX_KIOSK_OCCUPIED_SLOTS_PER_CHARGER = MAX_KIOSK_SLOTS_PER_CHARGER
MAX_KIOSK_HEALTH_CHARGERS = MAX_KIOSK_SECTIONS * MAX_KIOSK_CHARGERS_PER_SECTION


class RFChannelSnapshot(PydanticBaseDTO):
    """RF channel state shown beside one performer."""

    frequency: float | None
    channel_number: int
    rf_signal_strength: int | None
    audio_level: int | None
    link_direction: str


class KioskPerformerSnapshot(PydanticBaseDTO):
    """Display-safe performer, unit, and assignment state."""

    performer_id: int
    performer_name: str
    performer_title: str
    performer_photo: str | None
    unit_id: int
    unit_type: str
    unit_battery: int | None
    unit_battery_percent: int | None
    unit_status: str
    unit_rf_level: int | None
    unit_audio_level: int | None
    channel: RFChannelSnapshot | None
    assignment_priority: str
    slot_number: int
    charger_id: int


class KioskChargerSnapshot(PydanticBaseDTO):
    """Charger identity within a DisplayWall section."""

    id: int
    name: str
    location_id: int


class KioskChargerGroupSnapshot(PydanticBaseDTO):
    """Performers currently docked in one charger."""

    charger: KioskChargerSnapshot
    performers: list[KioskPerformerSnapshot]
    occupied_slots_truncated: bool = False
    occupied_slot_limit: int = MAX_KIOSK_OCCUPIED_SLOTS_PER_CHARGER


class WallSectionSnapshot(PydanticBaseDTO):
    """One ordered section of a DisplayWall snapshot."""

    id: int
    name: str
    layout: str
    columns: int
    performers: list[KioskChargerGroupSnapshot]
    chargers_truncated: bool = False
    charger_limit: int = MAX_KIOSK_CHARGERS_PER_SECTION
    occupied_slots_truncated: bool = False
    occupied_slot_limit: int = MAX_KIOSK_OCCUPIED_SLOTS_PER_CHARGER


class DisplayWallMetadata(PydanticBaseDTO):
    """Display and refresh settings required by kiosk adapters."""

    id: int
    name: str
    kiosk_id: str
    display_width_px: int
    display_height_px: int
    orientation: str
    refresh_interval_seconds: int
    show_performer_photos: bool
    show_rf_levels: bool
    show_battery_levels: bool
    show_audio_levels: bool


class DisplayWallSnapshot(PydanticBaseDTO):
    """Complete bounded projection rendered by a kiosk."""

    wall: DisplayWallMetadata
    sections: list[WallSectionSnapshot]
    sections_truncated: bool = False
    section_limit: int = MAX_KIOSK_SECTIONS


class KioskSlotHealthSnapshot(PydanticBaseDTO):
    """Connection assessment for one bounded charger slot."""

    slot_id: int
    slot_number: int
    charger_id: int
    occupied: bool
    connected: bool = False
    is_valid: bool = False
    issues: list[str]


class KioskHealthChargerMetadata(PydanticBaseDTO):
    """Charger identity included in health responses."""

    id: int
    name: str
    status: str
    ip: str | None


class KioskChargerHealthSnapshot(PydanticBaseDTO):
    """Bounded charger heartbeat and slot-health projection."""

    charger: KioskHealthChargerMetadata
    health: str
    connected: bool
    last_heartbeat_seconds_ago: int | None
    occupied_slots: int
    connected_slots: int
    total_slots: int
    issue_count: int
    slots: list[KioskSlotHealthSnapshot]
    slots_truncated: bool = False
    slot_limit: int = MAX_KIOSK_SLOTS_PER_CHARGER


class DisplayWallHealthSnapshot(PydanticBaseDTO):
    """Complete bounded health projection for one visible display wall."""

    wall_id: int
    chargers: list[KioskChargerHealthSnapshot]
    sections_truncated: bool = False
    chargers_truncated: bool = False
    slots_truncated: bool = False
    section_limit: int = MAX_KIOSK_SECTIONS
    charger_limit: int = MAX_KIOSK_HEALTH_CHARGERS
    slot_limit: int = MAX_KIOSK_SLOTS_PER_CHARGER
