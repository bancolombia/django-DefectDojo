from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("dojo", "0276_riskacceptanceengagement_path_and_more"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="hcparticipation",
            index=models.Index(
                fields=["recommendation", "-create_date"],
                name="dojo_hc_par_recomm_eefdf6_idx",
            ),
        ),
    ]
