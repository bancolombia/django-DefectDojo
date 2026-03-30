import uuid
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dojo', '0274_riskacceptanceengagement_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='HCParticipation',
            fields=[
                ('uuid', models.UUIDField(default=uuid.uuid4, primary_key=True, serialize=False)),
                ('recommendation', models.CharField(
                    choices=[
                        ('postulated', 'Postulated to HC'),
                        ('already_in_hc', 'Already in Hacking Continuous'),
                        ('not_eligible', 'Not eligible')
                    ],
                    help_text='System recommendation based on business rules',
                    max_length=20
                )),
                ('business_criticality', models.CharField(
                    blank=True,
                    help_text='Business criticality at evaluation time',
                    max_length=20,
                    null=True
                )),
                ('was_in_hacking_continuous', models.BooleanField(
                    default=False,
                    help_text='Whether product was already in HC at evaluation time'
                )),
                ('security_posture_data', models.JSONField(
                    blank=True,
                    default=dict,
                    help_text='Security posture snapshot at evaluation time'
                )),
                ('reason', models.TextField(
                    blank=True,
                    help_text='System-generated reason for the recommendation'
                )),
                ('status', models.CharField(
                    choices=[
                        ('Pending', 'Pending'),
                        ('Reviewed', 'Reviewed'),
                        ('Approved', 'Approved'),
                        ('Rejected', 'Rejected'),
                        ('Cancelled', 'Cancelled')
                    ],
                    default='Pending',
                    help_text='Current status in approval workflow',
                    max_length=12
                )),
                ('final_status', models.CharField(
                    blank=True,
                    choices=[('Approved', 'Approved'), ('Rejected', 'Rejected')],
                    help_text='Final decision after review',
                    max_length=12,
                    null=True
                )),
                ('create_date', models.DateTimeField(auto_now_add=True)),
                ('last_status_update', models.DateTimeField(auto_now=True)),
                ('status_updated_at', models.DateTimeField(blank=True, null=True)),
                ('reviewed_at', models.DateTimeField(blank=True, null=True)),
                ('approved_at', models.DateTimeField(blank=True, null=True)),
                ('batch_id', models.UUIDField(
                    blank=True,
                    db_index=True,
                    help_text='Groups evaluations from same batch execution',
                    null=True
                )),
                ('notification_sent', models.BooleanField(default=False)),
                ('approved_by', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='hc_approvals',
                    to='dojo.dojo_user'
                )),
                ('created_by', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='hc_created',
                    to='dojo.dojo_user'
                )),
                ('product', models.ForeignKey(
                    help_text='Product being evaluated for HC participation',
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='hc_participations',
                    to='dojo.product'
                )),
                ('rejected_by', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='hc_rejections',
                    to='dojo.dojo_user'
                )),
                ('reviewed_by', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='hc_reviews',
                    to='dojo.dojo_user'
                )),
                ('status_updated_by', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='hc_status_updates',
                    to='dojo.dojo_user'
                )),
            ],
            options={
                'verbose_name': 'HC Participation Request',
                'verbose_name_plural': 'HC Participation Requests',
                'db_table': 'dojo_hc_participation',
                'ordering': ['-create_date'],
            },
        ),
        migrations.CreateModel(
            name='HCParticipationLog',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('previous_status', models.CharField(
                    blank=True,
                    choices=[
                        ('Pending', 'Pending'),
                        ('Reviewed', 'Reviewed'),
                        ('Approved', 'Approved'),
                        ('Rejected', 'Rejected'),
                        ('Cancelled', 'Cancelled')
                    ],
                    max_length=12
                )),
                ('current_status', models.CharField(
                    choices=[
                        ('Pending', 'Pending'),
                        ('Reviewed', 'Reviewed'),
                        ('Approved', 'Approved'),
                        ('Rejected', 'Rejected'),
                        ('Cancelled', 'Cancelled')
                    ],
                    max_length=12
                )),
                ('changed_at', models.DateTimeField(auto_now_add=True)),
                ('notes', models.TextField(blank=True)),
                ('changed_by', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    to='dojo.dojo_user'
                )),
                ('hc_participation', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='logs',
                    to='dojo.hcparticipation'
                )),
            ],
            options={
                'db_table': 'dojo_hc_participation_log',
                'ordering': ['-changed_at'],
            },
        ),
        migrations.CreateModel(
            name='HCParticipationDiscussion',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('content', models.TextField()),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('author', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    to='dojo.dojo_user'
                )),
                ('hc_participation', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='discussions',
                    to='dojo.hcparticipation'
                )),
            ],
            options={
                'db_table': 'dojo_hc_participation_discussion',
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='hcparticipation',
            index=models.Index(fields=['product', '-create_date'], name='dojo_hc_par_product_559704_idx'),
        ),
        migrations.AddIndex(
            model_name='hcparticipation',
            index=models.Index(fields=['status'], name='dojo_hc_par_status_7986f7_idx'),
        ),
        migrations.AddIndex(
            model_name='hcparticipation',
            index=models.Index(fields=['recommendation'], name='dojo_hc_par_recomme_0c0ca0_idx'),
        ),
    ]
