from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('handle', '0075_staff_phase3_tracking_field_visit'),
    ]

    operations = [
        migrations.AlterField(
            model_name='complaint',
            name='status',
            field=models.CharField(choices=[('pending', 'Pending'), ('reviewing', 'Reviewing'), ('in_progress', 'In Progress'), ('resolved', 'Resolved'), ('rejected', 'Rejected'), ('closed', 'Closed')], default='pending', max_length=20),
        ),
        migrations.CreateModel(
            name='ComplaintMessage',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('message', models.TextField()),
                ('attachment', models.FileField(blank=True, null=True, upload_to='complaint_evidence/')),
                ('is_staff_reply', models.BooleanField(default=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('author', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='complaint_messages', to=settings.AUTH_USER_MODEL)),
                ('complaint', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='messages', to='handle.complaint')),
            ],
            options={
                'ordering': ('created_at',),
            },
        ),
    ]
