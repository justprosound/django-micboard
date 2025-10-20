"""Add frequency field to Channel model.

This migration adds a nullable FloatField 'frequency' to the Channel model
to store the configured or last-known operating frequency for the channel.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("micboard", "0002_discoverycidr_discoveryfqdn_discoveryjob"),
    ]

    operations = [
        migrations.AddField(
            model_name="channel",
            name="frequency",
            field=models.FloatField(blank=True, help_text="Operating frequency for this channel", null=True),
        ),
    ]
