"""Property-based testing for core DTOs using Hypothesis.

These tests generate edge cases automatically to verify validation logic
across the domain layer.
"""

import pytest
from hypothesis import given
from hypothesis import strategies as st
from pydantic import ValidationError

from micboard.services.settings.dtos import SettingWriteTarget


@pytest.mark.unit
class TestSettingWriteTargetProperties:
    """Verify scope validation rules for setting targets."""

    @given(
        org_id=st.integers(min_value=1) | st.none(),
        site_id=st.integers(min_value=1) | st.none(),
        mfg_id=st.integers(min_value=1) | st.none(),
    )
    def test_global_scope_rejects_identifiers(
        self, org_id: int | None, site_id: int | None, mfg_id: int | None
    ) -> None:
        """Global scope must not receive any specific identifiers."""
        if org_id is None and site_id is None and mfg_id is None:
            target = SettingWriteTarget(scope="global")
            assert target.scope == "global"
        else:
            with pytest.raises(ValidationError):
                SettingWriteTarget(
                    scope="global",
                    organization_id=org_id,
                    site_id=site_id,
                    manufacturer_id=mfg_id,
                )

    @given(
        org_id=st.integers(min_value=1) | st.none(),
        site_id=st.integers(min_value=1) | st.none(),
        mfg_id=st.integers(min_value=1) | st.none(),
    )
    def test_organization_scope_requires_exact_match(
        self, org_id: int | None, site_id: int | None, mfg_id: int | None
    ) -> None:
        """Organization scope requires org_id and rejects others."""
        if org_id is not None and site_id is None and mfg_id is None:
            target = SettingWriteTarget(scope="organization", organization_id=org_id)
            assert target.organization_id == org_id
        else:
            with pytest.raises(ValidationError):
                SettingWriteTarget(
                    scope="organization",
                    organization_id=org_id,
                    site_id=site_id,
                    manufacturer_id=mfg_id,
                )
