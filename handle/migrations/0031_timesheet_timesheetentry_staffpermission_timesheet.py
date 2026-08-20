import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('handle', '0030_attendancerecord_attendance_method_and_more'),
        ('management', '0025_organization_feature_timesheet'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # StaffPermission new fields
        migrations.AddField(
            model_name='staffpermission',
            name='can_view_timesheets',
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name='staffpermission',
            name='can_submit_timesheets',
            field=models.BooleanField(default=True),
        ),
        # Timesheet model
        migrations.CreateModel(
            name='Timesheet',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('period_start', models.DateField()),
                ('period_end', models.DateField()),
                ('title', models.CharField(blank=True, max_length=200)),
                ('status', models.CharField(
                    choices=[('draft', 'Draft'), ('submitted', 'Submitted'),
                             ('approved', 'Approved'), ('rejected', 'Rejected')],
                    default='draft', max_length=15,
                )),
                ('submitted_at', models.DateTimeField(blank=True, null=True)),
                ('approved_at', models.DateTimeField(blank=True, null=True)),
                ('admin_comment', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('approved_by', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='approved_timesheets',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('member', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='timesheets',
                    to='handle.member',
                )),
                ('org', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='timesheets',
                    to='management.organization',
                )),
            ],
            options={'ordering': ('-period_start', '-id')},
        ),
        # TimesheetEntry model
        migrations.CreateModel(
            name='TimesheetEntry',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date', models.DateField()),
                ('task', models.CharField(max_length=300)),
                ('hours', models.DecimalField(decimal_places=2, max_digits=5)),
                ('notes', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('timesheet', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='entries',
                    to='handle.timesheet',
                )),
            ],
            options={'ordering': ('date', 'task'),
                     'unique_together': {('timesheet', 'date', 'task')}},
        ),
    ]
