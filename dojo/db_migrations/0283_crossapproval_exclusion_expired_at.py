from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("dojo", "0282_crossapproval_logs_and_discussions"),
    ]

    operations = [
        migrations.AddField(
            model_name="crossapprovalexclusion",
            name="expired_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]