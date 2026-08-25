import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("dojo", "0281_crossapproval_request_and_exclusion"),
    ]

    operations = [
        migrations.CreateModel(
            name="CrossApprovalRequestLog",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("previous_status", models.CharField(blank=True, max_length=20)),
                ("current_status", models.CharField(max_length=20)),
                ("changed_at", models.DateTimeField(auto_now_add=True)),
                ("changed_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="dojo.dojo_user")),
                ("request", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="logs", to="dojo.crossapprovalrequest")),
            ],
            options={"ordering": ("-changed_at",)},
        ),
        migrations.CreateModel(
            name="CrossApprovalDiscussion",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("content", models.TextField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("author", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="dojo.dojo_user")),
                ("request", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="discussions", to="dojo.crossapprovalrequest")),
            ],
            options={"ordering": ("created_at",)},
        ),
    ]