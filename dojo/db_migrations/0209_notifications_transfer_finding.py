# Generated by Django 4.1.13 on 2024-03-07 19:36

from django.db import migrations
import multiselectfield.db.fields


class Migration(migrations.Migration):
    dependencies = [
        ("dojo", "0208_alter_transferfindingfinding_engagement_related_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="notifications",
            name="transfer_finding",
            field=multiselectfield.db.fields.MultiSelectField(
                blank=True,
                choices=[
                    ("slack", "slack"),
                    ("msteams", "msteams"),
                    ("mail", "mail"),
                    ("alert", "alert"),
                ],
                default="alert",
                help_text="Send notification to the contacts of the producto",
                max_length=24,
                verbose_name="Transfer Finding",
            ),
        ),
    ]
