from decimal import Decimal

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


def normalize_client_statuses(apps, schema_editor):
    Client = apps.get_model('handle', 'Client')
    CustomerBill = apps.get_model('handle', 'CustomerBill')
    Client.objects.filter(status='prospect').update(status='inquiry')
    Client.objects.filter(status__in=('active', 'inactive', 'churned')).update(status='customer')
    # Existing "paid" CRM invoices predate payment rows. Preserve their
    # settled meaning by treating the stored invoice total as the paid total.
    CustomerBill.objects.filter(status='paid').update(paid_amount=models.F('amount'))

    # The former schema allowed duplicate invoice numbers. Preserve every row
    # and make only the later duplicate references unambiguous before adding
    # the organisation-level uniqueness constraint.
    seen = set()
    for bill in CustomerBill.objects.order_by('org_id', 'id').iterator():
        key = (bill.org_id, bill.invoice_number)
        if key in seen:
            original = bill.invoice_number
            suffix = f"-{bill.pk}"
            bill.invoice_number = f"{original[:max(1, 50 - len(suffix))]}{suffix}"
            bill.save(update_fields=['invoice_number'])
        seen.add((bill.org_id, bill.invoice_number))


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('handle', '0066_subjectattendancerecord'),
    ]

    operations = [
        migrations.AddField(
            model_name='client',
            name='branch',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='clients', to='handle.branch'),
        ),
        migrations.AddField(
            model_name='client',
            name='priority',
            field=models.CharField(choices=[('high', 'High'), ('medium', 'Medium'), ('low', 'Low')], default='medium', max_length=10),
        ),
        migrations.AlterField(
            model_name='client',
            name='status',
            field=models.CharField(choices=[('inquiry', 'Inquiry'), ('customer', 'Customer')], default='inquiry', max_length=20),
        ),
        migrations.AddIndex(
            model_name='client',
            index=models.Index(fields=['org', 'branch', 'status'], name='client_org_branch_status_idx'),
        ),
        migrations.AddIndex(
            model_name='client',
            index=models.Index(fields=['org', 'priority'], name='client_org_priority_idx'),
        ),
        migrations.AddField(
            model_name='customerbill',
            name='branch',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='customer_bills', to='handle.branch'),
        ),
        migrations.AddField(
            model_name='customerbill',
            name='paid_amount',
            field=models.DecimalField(decimal_places=2, default=Decimal('0.00'), max_digits=12),
        ),
        migrations.RunPython(normalize_client_statuses, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='customerbill',
            name='status',
            field=models.CharField(choices=[('draft', 'Draft'), ('unpaid', 'Unpaid'), ('partial', 'Partially Paid'), ('paid', 'Paid'), ('overdue', 'Overdue'), ('cancelled', 'Cancelled'), ('sent', 'Sent (Legacy)')], default='draft', max_length=20),
        ),
        migrations.AddConstraint(
            model_name='customerbill',
            constraint=models.UniqueConstraint(fields=('org', 'invoice_number'), name='unique_customer_invoice_per_org'),
        ),
        migrations.AddIndex(
            model_name='customerbill',
            index=models.Index(fields=['org', 'branch', 'status'], name='custbill_org_branch_status_idx'),
        ),
        migrations.AddIndex(
            model_name='customerbill',
            index=models.Index(fields=['org', 'client', 'due_date'], name='custbill_client_due_idx'),
        ),
        migrations.CreateModel(
            name='CustomerBillPayment',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('amount', models.DecimalField(decimal_places=2, max_digits=12)),
                ('payment_date', models.DateField(default=django.utils.timezone.localdate)),
                ('payment_method', models.CharField(choices=[('cash', 'Cash'), ('bank', 'Bank'), ('card', 'Card'), ('online', 'Online'), ('other', 'Other')], default='cash', max_length=20)),
                ('payment_reference', models.CharField(blank=True, max_length=120)),
                ('note', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('bill', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='payments', to='handle.customerbill')),
                ('branch', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='customer_bill_payments', to='handle.branch')),
                ('client', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='bill_payments', to='handle.client')),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='customer_bill_payments_created', to=settings.AUTH_USER_MODEL)),
                ('income_transaction', models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='customer_bill_payment', to='handle.financialtransaction')),
                ('org', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='customer_bill_payments', to='management.organization')),
            ],
            options={'ordering': ('-payment_date', '-id')},
        ),
        migrations.AddIndex(
            model_name='customerbillpayment',
            index=models.Index(fields=['org', 'branch', 'payment_date'], name='custpay_org_branch_date_idx'),
        ),
        migrations.AddIndex(
            model_name='customerbillpayment',
            index=models.Index(fields=['org', 'client'], name='custpay_org_client_idx'),
        ),
    ]
