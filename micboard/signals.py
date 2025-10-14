"""
Signals for the micboard app.
"""
from typing import Any

from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

# Updated imports
from .models import DeviceAssignment, Receiver


@receiver(post_save, sender=Receiver)  # Updated sender
def receiver_saved(
    sender: type[Receiver], instance: Receiver, created: bool, **kwargs: Any
) -> None:
    """Handle receiver save events"""
    if created:
        # Log receiver creation
        pass
    else:
        # Handle receiver updates
        pass


@receiver(post_delete, sender=Receiver)  # Updated sender
def receiver_deleted(sender: type[Receiver], instance: Receiver, **kwargs: Any) -> None:
    """Handle receiver deletion"""
    # Clean up related data


@receiver(post_save, sender=DeviceAssignment)
def assignment_saved(
    sender: type[DeviceAssignment], instance: DeviceAssignment, created: bool, **kwargs: Any
) -> None:
    """Handle device assignment changes"""
    if created:
        # Log assignment creation
        pass
    # Could trigger alert preference updates here
