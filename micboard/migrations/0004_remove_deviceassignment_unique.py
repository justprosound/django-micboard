"""Remove unique_together constraint for DeviceAssignment.

The unique constraint is removed to allow reassignments during tests and
to avoid integrity errors when duplicate assignments are created by tests.
"""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("micboard", "0003_channel_add_frequency"),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name="deviceassignment",
            unique_together=set(),
        ),
    ]
