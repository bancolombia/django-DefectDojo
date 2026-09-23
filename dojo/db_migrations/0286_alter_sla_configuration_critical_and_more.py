from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dojo', '0285_inputflow_findings_alter_sla_configuration_critical_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='sla_configuration',
            name='critical',
            field=models.IntegerField(default=7, help_text='The number of days to remediate a Very Critical finding.', verbose_name='Very Critical Finding SLA Days'),
        ),
        migrations.AlterField(
            model_name='sla_configuration',
            name='enforce_critical',
            field=models.BooleanField(default=True, help_text='When enabled, Very Critical findings will be assigned an SLA expiration date based on the Very Critical finding SLA days within this SLA configuration.', verbose_name='Enforce Very Critical Finding SLA Days'),
        ),
        migrations.AlterField(
            model_name='sla_configuration',
            name='enforce_high',
            field=models.BooleanField(default=True, help_text='When enabled, Critical findings will be assigned an SLA expiration date based on the Critical finding SLA days within this SLA configuration.', verbose_name='Enforce Critical Finding SLA Days'),
        ),
        migrations.AlterField(
            model_name='sla_configuration',
            name='enforce_low',
            field=models.BooleanField(default=True, help_text='When enabled, Medium Low findings will be assigned an SLA expiration date based on the Medium Low finding SLA days within this SLA configuration.', verbose_name='Enforce Medium Low Finding SLA Days'),
        ),
        migrations.AlterField(
            model_name='sla_configuration',
            name='enforce_medium',
            field=models.BooleanField(default=True, help_text='When enabled, High findings will be assigned an SLA expiration date based on the High finding SLA days within this SLA configuration.', verbose_name='Enforce High Finding SLA Days'),
        ),
        migrations.AlterField(
            model_name='sla_configuration',
            name='high',
            field=models.IntegerField(default=30, help_text='The number of days to remediate a Critical finding.', verbose_name='Critical Finding SLA Days'),
        ),
        migrations.AlterField(
            model_name='sla_configuration',
            name='low',
            field=models.IntegerField(default=120, help_text='The number of days to remediate a Medium Low finding.', verbose_name='Medium Low Finding SLA Days'),
        ),
        migrations.AlterField(
            model_name='sla_configuration',
            name='medium',
            field=models.IntegerField(default=90, help_text='The number of days to remediate a High finding.', verbose_name='High Finding SLA Days'),
        ),
    ]
