# Generated by Django 4.1.13 on 2024-07-03 00:27

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("dojo", "0219_sla_configuration_enforce_critical_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="transferfinding",
            name="expiration_date",
            field=models.DateTimeField(
                blank=True,
                default=None,
                help_text="When the Transfer-Finding expires, the findings will be reactivated (unless disabled below).",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="transferfinding",
            name="expiration_date_handled",
            field=models.DateTimeField(
                blank=True,
                default=None,
                help_text="(readonly) When the transfer-finding expiration was handled (manually or by the daily job).",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="transferfinding",
            name="expiration_date_warned",
            field=models.DateTimeField(
                blank=True,
                default=None,
                help_text="(readonly) Date at which notice about the transfer-finding expiration was sent.",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="transferfinding",
            name="reactivate_expired",
            field=models.BooleanField(
                default=True,
                help_text="Reactivate findings when transfer-finding expires?",
                verbose_name="Reactivate findings on expiration",
            ),
        ),
        migrations.AddField(
            model_name="transferfinding",
            name="restart_sla_expired",
            field=models.BooleanField(
                default=False,
                help_text="When enabled, the SLA for findings is restarted when the transfer-finding expires.",
                verbose_name="Restart SLA on expiration",
            ),
        ),
    ]
