"""Base DTO class for all data transfer objects in the service layer.

All DTOs should inherit from this class to ensure consistent configuration.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class PydanticBaseDTO(BaseModel):
    """Base DTO with standard configuration for all service layer DTOs."""

    model_config = ConfigDict(
        # Use snake_case for field names (already default)
        # Validate assignment to prevent accidental modification after creation
        validate_assignment=True,
        # Use enum values instead of enum members
        use_enum_values=True,
        # Allow population by field name or alias
        populate_by_name=True,
        # Str strips whitespace
        str_strip_whitespace=True,
        # Validate default values
        validate_default=True,
        # Extra fields are forbidden
        extra="forbid",
        # Use immutable models (frozen) to prevent accidental modification
        # Note: Set to False if you need to modify DTO after creation
        frozen=False,
        # Arbitrary types allowed (for Django models, etc.)
        arbitrary_types_allowed=True,
    )
