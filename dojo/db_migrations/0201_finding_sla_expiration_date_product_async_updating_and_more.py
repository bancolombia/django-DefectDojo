from django.db import migrations, models
import logging

logger = logging.getLogger(__name__)


class Migration(migrations.Migration):

    dependencies = [
        ('dojo', '0200_whitesource_to_mend'),
    ]

    operations = [
        migrations.AddField(
            model_name='finding',
            name='sla_expiration_date',
            field=models.DateField(blank=True, help_text="(readonly)The date SLA expires for this finding. Empty by default, causing a fallback to 'date'.", null=True, verbose_name='SLA Expiration Date'),
        ),
        migrations.AddField(
            model_name='product',
            name='async_updating',
            field=models.BooleanField(default=False, help_text='Findings under this Product or SLA configuration are asynchronously being updated'),
        ),
        migrations.AddField(
            model_name='sla_configuration',
            name='async_updating',
            field=models.BooleanField(default=False, help_text='Findings under this SLA configuration are asynchronously being updated'),
        ),
    ]
