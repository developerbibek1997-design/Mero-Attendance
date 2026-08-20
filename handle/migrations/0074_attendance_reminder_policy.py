import handle.models
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('handle', '0073_staff_commercial_permissions'),
        ('management', '0033_featureprice_organization_commercial_fields'),
    ]

    operations = [
        migrations.CreateModel(
            name='AttendanceReminderPolicy',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('enabled', models.BooleanField(default=True)),
                ('checkin_enabled', models.BooleanField(default=True)),
                ('checkout_enabled', models.BooleanField(default=True)),
                ('checkin_offsets', models.JSONField(default=handle.models.default_checkin_reminder_offsets)),
                ('checkout_offsets', models.JSONField(default=handle.models.default_checkout_reminder_offsets)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('org', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='attendance_reminder_policy', to='management.organization')),
            ],
            options={
                'verbose_name_plural': 'attendance reminder policies',
            },
        ),
    ]
