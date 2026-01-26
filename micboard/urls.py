from django.urls import path

from micboard.views.assignments import (
    AssignmentListView,
    create_assignment,
    delete_assignment,
    update_assignment,
)
from micboard.views.charger_dashboard import ChargerDashboardView
from micboard.views.dashboard import about, index

urlpatterns = [
    # UI Views
    path("", index, name="index"),
    path("about/", about, name="about"),
    path("chargers/", ChargerDashboardView.as_view(), name="charger_dashboard"),
    # Assignment Management
    path("assignments/", AssignmentListView.as_view(), name="assignments"),
    path("assignments/create/", create_assignment, name="create_assignment"),
    path("assignments/<int:pk>/update/", update_assignment, name="update_assignment"),
    path("assignments/<int:pk>/delete/", delete_assignment, name="delete_assignment"),
]
