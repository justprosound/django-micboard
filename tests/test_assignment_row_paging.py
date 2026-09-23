"""Deterministic paging for the live assignment refresh."""

from __future__ import annotations

import pytest

from micboard.services.core.performer_assignment import PerformerAssignmentService

pytestmark = pytest.mark.django_db


def test_assignment_row_paging_breaks_ties_on_primary_key() -> None:
    """Rows are sliced per page, so the ordering must be total or rows repeat or vanish.

    `performer` and `wireless_unit` order by their own non-unique Meta ordering
    (`Performer.name`; `WirelessUnit.base_chassis__name, slot`), so `unique_together` on the
    assignment does not make the effective ordering total on its own.
    """
    from django.contrib.auth.models import User

    user = User.objects.create_superuser(username="pager", password="x")
    query = str(PerformerAssignmentService.get_visible_assignment_rows(user=user, page=1).query)

    assert query.rstrip().endswith('"id" ASC') or '"id"' in query.split("ORDER BY")[-1]
