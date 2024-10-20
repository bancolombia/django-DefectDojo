# Generated by Django 4.1.13 on 2023-11-28 12:11

from django.db import migrations, models
import multiselectfield.db.fields


class Migration(migrations.Migration):
    dependencies = [
        ("dojo", "0191_alter_notifications_risk_acceptance_expiration"),
    ]

    operations = [
        migrations.AddField(
            model_name="alerts",
            name="color_icon",
            field=models.CharField(
                blank=True, default="#262626", max_length=10, null=True
            ),
        ),
        migrations.AddField(
            model_name="finding",
            name="acceptances_confirmed",
            field=models.IntegerField(
                default=0,
                help_text="number of confirmed acceptances for finding",
                null=True,
                verbose_name="Acceptances confirmed",
            ),
        ),
        migrations.AddField(
            model_name="finding",
            name="accepted_by",
            field=models.CharField(
                blank=True,
                default="",
                help_text="The person that accepts the risk, can be outside of DefectDojo.",
                max_length=200,
                null=True,
                verbose_name="Accepted By",
            ),
        ),
        migrations.AddField(
            model_name="finding",
            name="risk_status",
            field=models.CharField(
                choices=[
                    ("Risk Pending", "Risk Pending"),
                    ("Risk Rejected", "Risk Rejected"),
                    ("Risk Accepted", "Risk Accepted"),
                    ("Risk Active", "Risk Active"),
                ],
                default="Risk Active",
                help_text="Denotes the type of finding status, (pending, rejected).",
                max_length=20,
                null=True,
                verbose_name="Risk Status",
            ),
        ),
        migrations.AddField(
            model_name="notifications",
            name="risk_acceptance_request",
            field=multiselectfield.db.fields.MultiSelectField(
                blank=True,
                choices=[
                    ("slack", "slack"),
                    ("msteams", "msteams"),
                    ("mail", "mail"),
                    ("alert", "alert"),
                ],
                default="alert",
                help_text="Send notification to the contacts of the product type",
                max_length=24,
                verbose_name="Risk Acceptance Request",
            ),
        ),
        migrations.AddField(
            model_name="risk_acceptance",
            name="severity",
            field=models.CharField(
                blank=True,
                choices=[
                    ("Critial", "Critical"),
                    ("Hight", "Hight"),
                    ("Medium", "Medium"),
                    ("Low", "Low"),
                ],
                help_text="type of severity admitted",
                max_length=10,
                null=True,
            ),
        ),
    ]
