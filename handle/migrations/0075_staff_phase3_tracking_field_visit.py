from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('handle', '0074_attendance_reminder_policy'),
    ]

    operations = [
        migrations.CreateModel(
            name='LiveTrackingSession',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('status', models.CharField(choices=[('active', 'Active'), ('stopped', 'Stopped')], default='active', max_length=12)),
                ('started_at', models.DateTimeField(auto_now_add=True)),
                ('stopped_at', models.DateTimeField(blank=True, null=True)),
                ('break_started_at', models.DateTimeField(blank=True, null=True)),
                ('last_ping_at', models.DateTimeField(blank=True, null=True)),
                ('last_latitude', models.FloatField(blank=True, null=True)),
                ('last_longitude', models.FloatField(blank=True, null=True)),
                ('member', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='live_tracking_sessions', to='handle.member')),
                ('org', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='live_tracking_sessions', to='management.organization')),
                ('started_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='started_live_tracking_sessions', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ('-started_at',),
            },
        ),
        migrations.AddIndex(
            model_name='livetrackingsession',
            index=models.Index(fields=['org', 'member', 'status'], name='handle_live_org_id_a959bf_idx'),
        ),
        migrations.AddField(
            model_name='locationping',
            name='battery_percentage',
            field=models.PositiveSmallIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='locationping',
            name='ping_type',
            field=models.CharField(choices=[('regular', 'Regular'), ('break_start', 'Break start'), ('break_end', 'Break end'), ('checkpoint', 'Checkpoint')], default='regular', max_length=20),
        ),
        migrations.AddField(
            model_name='locationping',
            name='session',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='pings', to='handle.livetrackingsession'),
        ),
        migrations.AddField(
            model_name='fieldvisit',
            name='destination',
            field=models.CharField(blank=True, max_length=300),
        ),
        migrations.AddField(
            model_name='fieldvisit',
            name='end_latitude',
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='fieldvisit',
            name='end_longitude',
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='fieldvisit',
            name='ended_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='fieldvisit',
            name='purpose',
            field=models.CharField(blank=True, max_length=300),
        ),
        migrations.AddField(
            model_name='fieldvisit',
            name='scheduled_for',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='fieldvisit',
            name='started_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='fieldvisit',
            name='visit_state',
            field=models.CharField(choices=[('not_started', 'Not Started'), ('in_progress', 'In Progress'), ('completed', 'Completed'), ('cancelled', 'Cancelled')], default='completed', max_length=20),
        ),
    ]
