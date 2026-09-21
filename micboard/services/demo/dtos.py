"""Data transfer objects for the demonstration dataset seeder."""

from __future__ import annotations

from micboard.services.shared.base_dto import PydanticBaseDTO


class DemoSeedSummary(PydanticBaseDTO):
    """What a seeding run produced, so a caller can report it without re-querying."""

    units: int = 0
    telemetry_samples: int = 0
    read_only_user_created: bool = False
