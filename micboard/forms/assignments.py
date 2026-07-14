"""Input validation for performer assignment controllers."""

from django import forms

from micboard.models.monitoring.performer_assignment import PerformerAssignment


class AssignmentOptionsForm(forms.Form):
    """Validate editable assignment metadata and alert preferences."""

    priority = forms.ChoiceField(
        choices=PerformerAssignment.PRIORITY_CHOICES,
        required=False,
    )
    notes = forms.CharField(required=False, max_length=10_000)
    alert_on_battery_low = forms.BooleanField(required=False)
    alert_on_signal_loss = forms.BooleanField(required=False)
    alert_on_audio_low = forms.BooleanField(required=False)
    alert_on_hardware_offline = forms.BooleanField(required=False)


class CreateAssignmentForm(AssignmentOptionsForm):
    """Validate object identifiers required to create an assignment."""

    performer_id = forms.IntegerField(min_value=1)
    wireless_unit_id = forms.IntegerField(min_value=1)
    monitoring_group_id = forms.IntegerField(min_value=1)


class UpdateAssignmentForm(AssignmentOptionsForm):
    """Validate fields supported by the assignment update controller."""

    is_active = forms.BooleanField(required=False)
