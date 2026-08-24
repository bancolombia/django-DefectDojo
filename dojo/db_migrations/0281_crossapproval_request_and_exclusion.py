import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("dojo", "0280_alter_answer_options_alter_choiceanswer_options_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="CrossApprovalRequest",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("type", models.CharField(default="x86", max_length=50)),
                ("status", models.CharField(choices=[("pending", "Pending"), ("approved", "Approved"), ("rejected", "Rejected")], default="pending", max_length=20)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("status_updated_at", models.DateTimeField(blank=True, null=True)),
                ("created_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="crossapproval_requests_created", to="dojo.dojo_user")),
                ("status_updated_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="crossapproval_requests_status_updated", to="dojo.dojo_user")),
            ],
            options={
                "ordering": ("-created_at",),
                "verbose_name": "Cross-approval request",
                "verbose_name_plural": "Cross-approval requests",
            },
        ),
        migrations.CreateModel(
            name="CrossApprovalExclusion",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("vulnerability_id", models.CharField(max_length=255)),
                ("cve_id", models.CharField(max_length=255)),
                ("where", models.CharField(max_length=255)),
                ("create_date", models.DateField()),
                ("expired_date", models.DateField()),
                ("priority", models.CharField(blank=True, max_length=50)),
                ("severity", models.CharField(blank=True, max_length=50)),
                ("hu", models.CharField(max_length=100)),
                ("reason", models.TextField()),
                ("image_names", models.JSONField(default=list)),
                ("request", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="exclusions", to="dojo.crossapprovalrequest")),
            ],
            options={"ordering": ("id",)},
        ),
    ]