from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('management', '0024_organization_enable_qr_attendance'),
    ]

    operations = [
        migrations.AddField(
            model_name='organization',
            name='feature_timesheet',
            field=models.BooleanField(default=False, verbose_name='Timesheet Management'),
        ),
    ]
