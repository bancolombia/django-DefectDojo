# Generated by Django 4.1.13 on 2024-03-07 19:45

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("dojo", "0209_notifications_transfer_finding"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="notifications",
            name="transfer_finding",
        ),
    ]
