from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("dojo", "0283_crossapproval_owner_and_components"),
    ]

    operations = [
        migrations.RenameField(
            model_name="crossapprovalrequest",
            old_name="type",
            new_name="owner",
        ),
        migrations.RenameField(
            model_name="crossapprovalexclusion",
            old_name="image_names",
            new_name="component_values",
        ),
        migrations.AddField(
            model_name="crossapprovalexclusion",
            name="component_type",
            field=models.CharField(default="image", max_length=50),
        ),
    ]