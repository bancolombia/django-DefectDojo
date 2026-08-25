from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("dojo", "0283_crossapproval_exclusion_expired_at"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="crossapprovalexclusion",
            name="cve_id",
        ),
    ]