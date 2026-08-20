from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('handle', '0072_notification_recipient_constraint'),
    ]

    operations = [
        migrations.AddField(
            model_name='staffpermission',
            name='can_view_purchases',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='staffpermission',
            name='can_manage_purchases',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='staffpermission',
            name='can_view_sales',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='staffpermission',
            name='can_manage_sales',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='staffpermission',
            name='can_manage_purchase_returns',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='staffpermission',
            name='can_manage_sales_returns',
            field=models.BooleanField(default=False),
        ),
    ]
