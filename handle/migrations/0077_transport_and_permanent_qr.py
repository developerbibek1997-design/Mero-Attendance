from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('management', '0033_featureprice_organization_commercial_fields'),
        ('handle', '0076_complaint_messages_and_statuses'),
    ]

    operations = [
        migrations.CreateModel(
            name='BusLocationPing',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('latitude', models.FloatField()),
                ('longitude', models.FloatField()),
                ('accuracy_meters', models.FloatField(blank=True, null=True)),
                ('recorded_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={'ordering': ('-recorded_at',)},
        ),
        migrations.CreateModel(
            name='BusTrackingSession',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('status', models.CharField(choices=[('active', 'Active'), ('stopped', 'Stopped')], default='active', max_length=10)),
                ('started_at', models.DateTimeField(auto_now_add=True)),
                ('stopped_at', models.DateTimeField(blank=True, null=True)),
                ('last_ping_at', models.DateTimeField(blank=True, null=True)),
                ('last_latitude', models.FloatField(blank=True, null=True)),
                ('last_longitude', models.FloatField(blank=True, null=True)),
                ('last_accuracy_meters', models.FloatField(blank=True, null=True)),
            ],
            options={'ordering': ('-started_at',)},
        ),
        migrations.CreateModel(
            name='SchoolBus',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=120)),
                ('registration_number', models.CharField(max_length=50)),
                ('route_name', models.CharField(blank=True, max_length=180)),
                ('capacity', models.PositiveIntegerField(default=1)),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={'ordering': ('name', 'registration_number')},
        ),
        migrations.CreateModel(
            name='StudentBusAssignment',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('stop_name', models.CharField(blank=True, max_length=180)),
                ('stop_latitude', models.FloatField(blank=True, null=True)),
                ('stop_longitude', models.FloatField(blank=True, null=True)),
                ('status', models.CharField(choices=[('active', 'Active'), ('inactive', 'Inactive')], default='active', max_length=10)),
                ('assigned_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={'ordering': ('student__name',)},
        ),
        migrations.AddField(
            model_name='qrattendancesession',
            name='latitude',
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='qrattendancesession',
            name='location_name',
            field=models.CharField(blank=True, max_length=200),
        ),
        migrations.AddField(
            model_name='qrattendancesession',
            name='longitude',
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='qrattendancesession',
            name='radius_meters',
            field=models.PositiveIntegerField(default=100),
        ),
        migrations.AddField(
            model_name='qrattendancesession',
            name='session_type',
            field=models.CharField(
                choices=[
                    ('dynamic', 'Time-limited Dynamic QR'),
                    ('permanent', 'Permanent Geofenced QR'),
                ],
                db_index=True,
                default='dynamic',
                max_length=12,
            ),
        ),
        migrations.AlterField(
            model_name='member',
            name='member_type',
            field=models.CharField(
                choices=[
                    ('student', 'Student'),
                    ('employee', 'Employee'),
                    ('staff', 'Staff'),
                    ('intern', 'Intern'),
                    ('trainee', 'Trainee'),
                    ('teacher', 'Teacher'),
                    ('driver', 'Driver'),
                    ('worker', 'Worker'),
                    ('member', 'Organization Member'),
                ],
                default='member',
                max_length=30,
            ),
        ),
        migrations.AlterField(
            model_name='qrattendancescanlog',
            name='status',
            field=models.CharField(
                choices=[
                    ('success', 'Success'),
                    ('expired', 'Expired'),
                    ('duplicate', 'Duplicate'),
                    ('invalid_org', 'Invalid Org'),
                    ('inactive_member', 'Inactive Member'),
                    ('session_closed', 'Session Closed'),
                    ('outside_geofence', 'Outside Geofence'),
                    ('location_required', 'Location Required'),
                    ('error', 'Error'),
                ],
                default='success',
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name='qrattendancesession',
            name='date',
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='qrattendancesession',
            name='expires_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='studentbusassignment',
            name='bus',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='student_assignments', to='handle.schoolbus'),
        ),
        migrations.AddField(
            model_name='studentbusassignment',
            name='org',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='student_bus_assignments', to='management.organization'),
        ),
        migrations.AddField(
            model_name='studentbusassignment',
            name='student',
            field=models.ForeignKey(limit_choices_to={'member_type__in': ('student', 'trainee')}, on_delete=django.db.models.deletion.CASCADE, related_name='bus_assignments', to='handle.member'),
        ),
        migrations.AddField(
            model_name='schoolbus',
            name='branch',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='school_buses', to='handle.branch'),
        ),
        migrations.AddField(
            model_name='schoolbus',
            name='driver',
            field=models.ForeignKey(blank=True, limit_choices_to={'member_type': 'driver'}, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='assigned_buses', to='handle.member'),
        ),
        migrations.AddField(
            model_name='schoolbus',
            name='org',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='school_buses', to='management.organization'),
        ),
        migrations.AddField(
            model_name='bustrackingsession',
            name='bus',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='tracking_sessions', to='handle.schoolbus'),
        ),
        migrations.AddField(
            model_name='bustrackingsession',
            name='driver',
            field=models.ForeignKey(limit_choices_to={'member_type': 'driver'}, on_delete=django.db.models.deletion.CASCADE, related_name='bus_tracking_sessions', to='handle.member'),
        ),
        migrations.AddField(
            model_name='bustrackingsession',
            name='org',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='bus_tracking_sessions', to='management.organization'),
        ),
        migrations.AddField(
            model_name='buslocationping',
            name='bus',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='location_pings', to='handle.schoolbus'),
        ),
        migrations.AddField(
            model_name='buslocationping',
            name='driver',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='bus_location_pings', to='handle.member'),
        ),
        migrations.AddField(
            model_name='buslocationping',
            name='org',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='bus_location_pings', to='management.organization'),
        ),
        migrations.AddField(
            model_name='buslocationping',
            name='session',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='pings', to='handle.bustrackingsession'),
        ),
        migrations.AddConstraint(
            model_name='studentbusassignment',
            constraint=models.UniqueConstraint(condition=models.Q(('status', 'active')), fields=('student',), name='one_active_bus_per_student'),
        ),
        migrations.AddConstraint(
            model_name='schoolbus',
            constraint=models.UniqueConstraint(fields=('org', 'registration_number'), name='unique_bus_registration_per_org'),
        ),
        migrations.AddConstraint(
            model_name='bustrackingsession',
            constraint=models.UniqueConstraint(condition=models.Q(('status', 'active')), fields=('bus',), name='one_active_tracking_session_per_bus'),
        ),
        migrations.AddIndex(
            model_name='buslocationping',
            index=models.Index(fields=['bus', 'recorded_at'], name='handle_busl_bus_id_f70cc9_idx'),
        ),
        migrations.AddIndex(
            model_name='buslocationping',
            index=models.Index(fields=['driver', 'recorded_at'], name='handle_busl_driver__f25ccf_idx'),
        ),
    ]
