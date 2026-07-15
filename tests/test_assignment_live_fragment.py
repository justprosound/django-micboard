"""Assignment full-page and count-free live-fragment query contracts."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

import pytest

from micboard.models.monitoring.performer import Performer
from micboard.models.monitoring.performer_assignment import PerformerAssignment
from micboard.services.core.performer_assignment import PerformerAssignmentService
from tests.factories.hardware import WirelessUnitFactory
from tests.factories.monitoring import MonitoringGroupFactory


@pytest.mark.django_db
def test_assignment_fragment_uses_one_bounded_select_and_full_page_keeps_metadata(
    client,
) -> None:
    """Live page slices avoid COUNT while the navigable page retains totals."""
    user = get_user_model().objects.create_superuser(username="assignment-fragment-admin")
    group = MonitoringGroupFactory()
    unit = WirelessUnitFactory()
    performers = Performer.objects.bulk_create(
        [Performer(name=f"Assignment Performer {index:03d}") for index in range(51)]
    )
    PerformerAssignment.objects.bulk_create(
        [
            PerformerAssignment(
                performer=performer,
                wireless_unit=unit,
                monitoring_group=group,
            )
            for performer in performers
        ]
    )
    client.force_login(user)

    page_response = client.get(reverse("micboard:assignments"))
    page = page_response.context["page_obj"]
    assert page.paginator.count == 51
    assert page.paginator.num_pages == 2
    assert page.has_next()

    with CaptureQueriesContext(connection) as query_context:
        fragment_response = client.get(reverse("micboard:assignment_rows"), {"page": 2})

    assignment_queries = [
        query["sql"]
        for query in query_context.captured_queries
        if PerformerAssignment._meta.db_table in query["sql"]
    ]
    assert fragment_response.status_code == 200
    assert len(fragment_response.context["assignments"]) == 1
    assert "Assignment Performer 050" in fragment_response.content.decode()
    assert "Assignment Performer 000" not in fragment_response.content.decode()
    assert len(assignment_queries) == 1
    assert "COUNT(" not in assignment_queries[0].upper()
    assert f"LIMIT {PerformerAssignmentService.PAGE_SIZE}" in assignment_queries[0].upper()
    assert f"OFFSET {PerformerAssignmentService.PAGE_SIZE}" in assignment_queries[0].upper()
