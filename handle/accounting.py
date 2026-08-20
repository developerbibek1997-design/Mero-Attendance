"""
Accounting Core service layer — the single place that knows how to post a
balanced Journal Entry and compute ledger/report figures from it.

Deliberately separate from `FinancialTransaction`/`TransactionCategory`
(school/Finance module) — those keep working exactly as before for every
org; this is the double-entry system for orgs with the 'accounting'
DynamicFeature enabled. Later phases (Sales, Purchase, Payroll auto-posting)
should call `create_journal_entry()` instead of writing their own
debit/credit logic.

Usage:
    from handle.accounting import create_journal_entry, general_ledger, ...
"""

import datetime
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone


# ---------------------------------------------------------------------------
# Voucher numbering
# ---------------------------------------------------------------------------

def next_voucher_number(org) -> str:
    """Atomically increments and returns the org's next voucher number, e.g. 'JV-000123'."""
    from handle.models import AccountingVoucherSequence

    with transaction.atomic():
        seq, _ = AccountingVoucherSequence.objects.select_for_update().get_or_create(org=org)
        seq.last_number += 1
        seq.save(update_fields=['last_number'])
        return f"JV-{seq.last_number:06d}"


# ---------------------------------------------------------------------------
# Posting
# ---------------------------------------------------------------------------

def create_journal_entry(org, *, entry_date, lines, description='', reference='',
                          branch=None, created_by=None, attachment=None,
                          source='manual', status='draft'):
    """Create a Journal Entry with its lines inside one atomic transaction.

    `lines` = [{'account': Account, 'debit': Decimal, 'credit': Decimal, 'remarks': ''}, ...]

    This is the real enforcement point for double-entry correctness — never
    trust a caller's (form, formset, or future auto-poster's) own math.
    Raises ValueError if the entry doesn't balance or is otherwise invalid.
    """
    from handle.models import JournalEntry, JournalEntryLine

    usable_lines = [
        l for l in lines
        if (l.get('debit') or Decimal('0')) > 0 or (l.get('credit') or Decimal('0')) > 0
    ]
    if len(usable_lines) < 2:
        raise ValueError("A journal entry needs at least two lines (one debit, one credit).")

    total_debit = sum((l.get('debit') or Decimal('0')) for l in usable_lines)
    total_credit = sum((l.get('credit') or Decimal('0')) for l in usable_lines)
    if total_debit != total_credit:
        raise ValueError(
            f"Journal entry does not balance: total debit {total_debit} != total credit {total_credit}."
        )
    if total_debit <= 0:
        raise ValueError("Journal entry total must be greater than zero.")

    for l in usable_lines:
        debit, credit = l.get('debit') or Decimal('0'), l.get('credit') or Decimal('0')
        if debit and credit:
            raise ValueError("A line cannot have both a debit and a credit amount.")
        account = l['account']
        if account.is_group:
            raise ValueError(f"'{account.name}' is a header account and cannot be posted to directly.")

    with transaction.atomic():
        entry = JournalEntry.objects.create(
            org=org, branch=branch, voucher_number=next_voucher_number(org),
            entry_date=entry_date, reference=reference, description=description,
            status=status, source=source, attachment=attachment, created_by=created_by,
        )
        for idx, l in enumerate(usable_lines):
            JournalEntryLine.objects.create(
                entry=entry, account=l['account'],
                debit=l.get('debit') or Decimal('0'), credit=l.get('credit') or Decimal('0'),
                remarks=l.get('remarks', ''), line_order=idx,
            )
    return entry


# ---------------------------------------------------------------------------
# Approval workflow
# ---------------------------------------------------------------------------

def submit_for_approval(entry, user=None):
    if entry.status not in ('draft', 'rejected'):
        raise ValueError(f"Cannot submit a journal entry that is '{entry.status}'.")
    if not entry.is_balanced():
        raise ValueError("Journal entry does not balance and cannot be submitted.")
    entry.status = 'pending'
    entry.rejection_reason = None
    entry.save(update_fields=['status', 'rejection_reason', 'updated_at'])


def approve_journal_entry(entry, user):
    if entry.status != 'pending':
        raise ValueError(f"Cannot approve a journal entry that is '{entry.status}'.")
    entry.status = 'approved'
    entry.approved_by = user
    entry.approved_at = timezone.now()
    entry.save(update_fields=['status', 'approved_by', 'approved_at', 'updated_at'])


def reject_journal_entry(entry, user, reason=''):
    if entry.status != 'pending':
        raise ValueError(f"Cannot reject a journal entry that is '{entry.status}'.")
    entry.status = 'rejected'
    entry.approved_by = user
    entry.approved_at = timezone.now()
    entry.rejection_reason = reason
    entry.save(update_fields=['status', 'approved_by', 'approved_at', 'rejection_reason', 'updated_at'])


# ---------------------------------------------------------------------------
# Default Chart of Accounts
# ---------------------------------------------------------------------------

# (name, account_type, [(child_name, child_type), ...])
_DEFAULT_CHART = [
    ('Asset', 'asset', [
        ('Current Assets', 'asset', [
            ('Cash', 'asset', []),
            ('Bank', 'asset', []),
            ('Accounts Receivable', 'asset', []),
            ('Inventory', 'asset', []),
            ('Employee Advances', 'asset', []),
        ]),
        ('Fixed Assets', 'asset', [
            ('Equipment', 'asset', []),
        ]),
    ]),
    ('Liability', 'liability', [
        ('Accounts Payable', 'liability', []),
        ('VAT Payable', 'liability', []),
        ('Salary Payable', 'liability', []),
    ]),
    ('Equity', 'equity', [
        ('Opening Balance', 'equity', []),
        ('Retained Earnings', 'equity', []),
    ]),
    ('Income', 'income', [
        ('Sales Revenue', 'income', []),
        ('Sales Returns', 'income', []),
        ('Other Income', 'income', []),
    ]),
    ('Expense', 'expense', [
        ('Purchase', 'expense', []),
        ('Salary Expense', 'expense', []),
        ('Rent Expense', 'expense', []),
        ('Electricity', 'expense', []),
        ('Tax', 'expense', []),
        ('Discount', 'expense', []),
        ('Inventory Adjustment', 'expense', []),
        ('Other Expense', 'expense', []),
    ]),
    ('Cost of Goods Sold', 'cogs', []),
]


def ensure_default_accounts(org):
    """Idempotent: seeds the default chart only for names that don't already
    exist under this org. Safe to call repeatedly (e.g. every dashboard visit)."""
    from handle.models import Account

    def _create_level(nodes, parent):
        for name, acc_type, children in nodes:
            is_group = bool(children)
            account, _ = Account.objects.get_or_create(
                org=org, name=name, parent=parent,
                defaults={'account_type': acc_type, 'is_group': is_group, 'is_system': True},
            )
            _create_level(children, account)

    _create_level(_DEFAULT_CHART, None)


# ---------------------------------------------------------------------------
# Auto-posting — Stock / Purchase / Sale
#
# These are the "future auto-poster" callers `JournalEntry.source` was always
# meant for. Each function is idempotent (checks the header document's
# `journal_entry` FK before doing anything) and posts straight to
# `status='approved'` — auto-posted entries reflect a real, already-confirmed
# business event (goods received, a sale completed), unlike a manual entry
# which is unaudited human input and still defaults to 'draft'.
# ---------------------------------------------------------------------------

def _resolve_cash_or_bank_account(org, payment_method):
    """Looks up the seeded Cash/Bank leaf account by name. Falls back to Cash
    for any payment_method not explicitly mapped to Bank (card/online/other
    typically settle through a bank account in practice, but Cash is the
    safer default when unsure)."""
    from handle.models import Account

    name = 'Bank' if payment_method == 'bank' else 'Cash'
    account = Account.objects.filter(org=org, name=name, is_group=False).first()
    if account is None:
        account = Account.objects.filter(org=org, name='Cash', is_group=False).first()
    return account


def post_purchase_journal_entry(purchase):
    """Debit Inventory, Credit Accounts Payable (unpaid) or Cash/Bank (paid),
    for the purchase's total_amount. Idempotent — returns the existing entry
    if this purchase was already posted."""
    from handle.models import Account

    if purchase.journal_entry_id:
        return purchase.journal_entry

    org = purchase.org
    ensure_default_accounts(org)
    inventory = Account.objects.filter(org=org, name='Inventory', is_group=False).first()
    if purchase.status == 'paid':
        credit_account = _resolve_cash_or_bank_account(org, purchase.payment_method)
    else:
        credit_account = Account.objects.filter(org=org, name='Accounts Payable', is_group=False).first()

    if not inventory or not credit_account:
        raise ValueError("Required accounting accounts are missing for this organization.")

    with transaction.atomic():
        entry = create_journal_entry(
            org, entry_date=purchase.purchase_date,
            lines=[
                {'account': inventory, 'debit': purchase.total_amount, 'remarks': f'Purchase #{purchase.pk}'},
                {'account': credit_account, 'credit': purchase.total_amount, 'remarks': f'Purchase #{purchase.pk}'},
            ],
            description=f"Purchase #{purchase.pk} — {purchase.supplier.name}",
            reference=purchase.invoice_number, branch=purchase.branch,
            created_by=purchase.created_by, source='purchase', status='approved',
        )
        entry.purchase = purchase
        entry.save(update_fields=['purchase'])
        purchase.journal_entry = entry
        purchase.save(update_fields=['journal_entry'])
    return entry


def post_sale_journal_entry(sale):
    """Two balanced pairs in one entry: (1) Debit Cash/Bank/Accounts
    Receivable, Credit Sales Revenue at sale price; (2) Debit Cost of Goods
    Sold, Credit Inventory at the items' recorded purchase cost. Idempotent."""
    from handle.models import Account

    if sale.journal_entry_id:
        return sale.journal_entry

    org = sale.org
    ensure_default_accounts(org)
    if sale.payment_status == 'paid':
        debit_account = _resolve_cash_or_bank_account(org, sale.payment_method)
    else:
        debit_account = Account.objects.filter(org=org, name='Accounts Receivable', is_group=False).first()
    revenue = Account.objects.filter(org=org, name='Sales Revenue', is_group=False).first()
    cogs_account = Account.objects.filter(org=org, name='Cost of Goods Sold', is_group=False).first()
    inventory = Account.objects.filter(org=org, name='Inventory', is_group=False).first()

    if not all([debit_account, revenue, cogs_account, inventory]):
        raise ValueError("Required accounting accounts are missing for this organization.")

    cogs_total = sum(
        (item.stock_item.purchase_cost * item.quantity for item in sale.items.select_related('stock_item') if item.stock_item),
        Decimal('0.00'),
    )

    lines = [
        {'account': debit_account, 'debit': sale.total_amount, 'remarks': f'Sale #{sale.pk}'},
        {'account': revenue, 'credit': sale.total_amount, 'remarks': f'Sale #{sale.pk}'},
    ]
    if cogs_total > 0:
        lines.append({'account': cogs_account, 'debit': cogs_total, 'remarks': f'COGS — Sale #{sale.pk}'})
        lines.append({'account': inventory, 'credit': cogs_total, 'remarks': f'COGS — Sale #{sale.pk}'})

    with transaction.atomic():
        entry = create_journal_entry(
            org, entry_date=sale.sale_date, lines=lines,
            description=f"Sale #{sale.pk} — {sale.client.client_org_name if sale.client else sale.customer_name or 'Walk-in'}",
            reference=sale.invoice_number, branch=sale.branch,
            created_by=sale.created_by, source='sale', status='approved',
        )
        entry.sale = sale
        entry.save(update_fields=['sale'])
        sale.journal_entry = entry
        sale.save(update_fields=['journal_entry'])
    return entry


def post_stock_in_journal_entry(item, quantity, unit_cost, payment_method, org, branch=None, created_by=None):
    """For stock received outside a Purchase document (the StockInView
    accounting-aware path) — Debit Inventory, Credit Cash/Bank. Not tied to
    a header document, so no idempotency guard is needed here; the caller
    is responsible for calling this once per stock-in event."""
    from handle.models import Account

    ensure_default_accounts(org)
    inventory = Account.objects.filter(org=org, name='Inventory', is_group=False).first()
    credit_account = _resolve_cash_or_bank_account(org, payment_method)
    if not inventory or not credit_account:
        raise ValueError("Required accounting accounts are missing for this organization.")

    total_cost = Decimal(str(quantity)) * Decimal(str(unit_cost))
    return create_journal_entry(
        org, entry_date=timezone.localdate(),
        lines=[
            {'account': inventory, 'debit': total_cost, 'remarks': f'Stock in — {item.name}'},
            {'account': credit_account, 'credit': total_cost, 'remarks': f'Stock in — {item.name}'},
        ],
        description=f"Stock In — {item.name} x{quantity}",
        branch=branch, created_by=created_by, source='stock_adjustment', status='approved',
    )


def post_supplier_payment_journal_entry(payment):
    """A cash/bank payment made to a supplier against outstanding purchases —
    Debit Accounts Payable, Credit Cash/Bank. Idempotent."""
    from handle.models import Account

    if payment.journal_entry_id:
        return payment.journal_entry

    org = payment.org
    ensure_default_accounts(org)
    payable = Account.objects.filter(org=org, name='Accounts Payable', is_group=False).first()
    credit_account = _resolve_cash_or_bank_account(org, payment.payment_method)
    if not payable or not credit_account:
        raise ValueError("Required accounting accounts are missing for this organization.")

    with transaction.atomic():
        entry = create_journal_entry(
            org, entry_date=payment.payment_date,
            lines=[
                {'account': payable, 'debit': payment.amount, 'remarks': f'Payment #{payment.pk} — {payment.supplier.name}'},
                {'account': credit_account, 'credit': payment.amount, 'remarks': f'Payment #{payment.pk} — {payment.supplier.name}'},
            ],
            description=f"Supplier payment #{payment.pk} — {payment.supplier.name}",
            reference=payment.reference_number, branch=payment.branch,
            created_by=payment.created_by, source='supplier_payment', status='approved',
        )
        payment.journal_entry = entry
        payment.save(update_fields=['journal_entry'])
    return entry


def post_purchase_return_journal_entry(return_doc):
    """Goods sent back to a supplier — Debit Accounts Payable, Credit
    Inventory, at the return's total_amount. Idempotent."""
    from handle.models import Account

    if return_doc.journal_entry_id:
        return return_doc.journal_entry

    org = return_doc.org
    ensure_default_accounts(org)
    payable = Account.objects.filter(org=org, name='Accounts Payable', is_group=False).first()
    inventory = Account.objects.filter(org=org, name='Inventory', is_group=False).first()
    if not payable or not inventory:
        raise ValueError("Required accounting accounts are missing for this organization.")

    with transaction.atomic():
        entry = create_journal_entry(
            org, entry_date=return_doc.return_date,
            lines=[
                {'account': payable, 'debit': return_doc.total_amount, 'remarks': f'Purchase Return #{return_doc.pk}'},
                {'account': inventory, 'credit': return_doc.total_amount, 'remarks': f'Purchase Return #{return_doc.pk}'},
            ],
            description=f"Purchase Return #{return_doc.pk} — {return_doc.supplier.name}",
            branch=return_doc.branch, created_by=return_doc.created_by,
            source='purchase_return', status='approved',
        )
        return_doc.journal_entry = entry
        return_doc.save(update_fields=['journal_entry'])
    return entry


def post_sale_payment_journal_entry(payment):
    """A payment received from a customer against an outstanding sale —
    Debit Cash/Bank, Credit Accounts Receivable. Idempotent."""
    from handle.models import Account

    if payment.journal_entry_id:
        return payment.journal_entry

    org = payment.sale.org
    ensure_default_accounts(org)
    debit_account = _resolve_cash_or_bank_account(org, payment.payment_method)
    receivable = Account.objects.filter(org=org, name='Accounts Receivable', is_group=False).first()
    if not debit_account or not receivable:
        raise ValueError("Required accounting accounts are missing for this organization.")

    with transaction.atomic():
        entry = create_journal_entry(
            org, entry_date=payment.payment_date,
            lines=[
                {'account': debit_account, 'debit': payment.amount, 'remarks': f'Payment #{payment.pk} — Sale #{payment.sale_id}'},
                {'account': receivable, 'credit': payment.amount, 'remarks': f'Payment #{payment.pk} — Sale #{payment.sale_id}'},
            ],
            description=f"Sale payment #{payment.pk} — Sale #{payment.sale_id}",
            reference=payment.reference_number, branch=payment.branch,
            created_by=payment.created_by, source='sale_payment', status='approved',
        )
        payment.journal_entry = entry
        payment.save(update_fields=['journal_entry'])
    return entry


def post_sales_return_journal_entry(return_doc):
    """Goods returned by a customer — two pairs: (1) Debit Sales Returns,
    Credit Accounts Receivable/Cash at the return's sale price; (2) reverse
    the original COGS: Debit Inventory, Credit Cost of Goods Sold, at the
    items' recorded purchase cost. Idempotent."""
    from handle.models import Account

    if return_doc.journal_entry_id:
        return return_doc.journal_entry

    org = return_doc.org
    ensure_default_accounts(org)
    sale = return_doc.sale
    if sale.payment_status == 'paid':
        credit_account = _resolve_cash_or_bank_account(org, sale.payment_method)
    else:
        credit_account = Account.objects.filter(org=org, name='Accounts Receivable', is_group=False).first()
    sales_returns = Account.objects.filter(org=org, name='Sales Returns', is_group=False).first()
    inventory = Account.objects.filter(org=org, name='Inventory', is_group=False).first()
    cogs_account = Account.objects.filter(org=org, name='Cost of Goods Sold', is_group=False).first()

    if not all([credit_account, sales_returns, inventory, cogs_account]):
        raise ValueError("Required accounting accounts are missing for this organization.")

    cogs_total = sum(
        (item.stock_item.purchase_cost * item.quantity for item in return_doc.items.select_related('stock_item') if item.stock_item),
        Decimal('0.00'),
    )

    lines = [
        {'account': sales_returns, 'debit': return_doc.total_amount, 'remarks': f'Sales Return #{return_doc.pk}'},
        {'account': credit_account, 'credit': return_doc.total_amount, 'remarks': f'Sales Return #{return_doc.pk}'},
    ]
    if cogs_total > 0:
        lines.append({'account': inventory, 'debit': cogs_total, 'remarks': f'COGS reversal — Return #{return_doc.pk}'})
        lines.append({'account': cogs_account, 'credit': cogs_total, 'remarks': f'COGS reversal — Return #{return_doc.pk}'})

    with transaction.atomic():
        entry = create_journal_entry(
            org, entry_date=return_doc.return_date, lines=lines,
            description=f"Sales Return #{return_doc.pk} — Sale #{sale.pk}",
            branch=return_doc.branch, created_by=return_doc.created_by,
            source='sales_return', status='approved',
        )
        return_doc.journal_entry = entry
        return_doc.save(update_fields=['journal_entry'])
    return entry


def post_asset_purchase_journal_entry(asset):
    """A fixed-asset purchase — Debit Equipment, Credit Cash/Bank. Idempotent."""
    from handle.models import Account

    if asset.journal_entry_id:
        return asset.journal_entry

    org = asset.org
    ensure_default_accounts(org)
    equipment = Account.objects.filter(org=org, name='Equipment', is_group=False).first()
    credit_account = _resolve_cash_or_bank_account(org, asset.payment_method)
    if not equipment or not credit_account:
        raise ValueError("Required accounting accounts are missing for this organization.")

    with transaction.atomic():
        entry = create_journal_entry(
            org, entry_date=asset.purchase_date,
            lines=[
                {'account': equipment, 'debit': asset.cost, 'remarks': f'Asset — {asset.name}'},
                {'account': credit_account, 'credit': asset.cost, 'remarks': f'Asset — {asset.name}'},
            ],
            description=f"Asset Purchase — {asset.name}",
            branch=asset.branch, created_by=asset.created_by,
            source='asset_purchase', status='approved',
        )
        asset.journal_entry = entry
        asset.save(update_fields=['journal_entry'])
    return entry


def post_payroll_accrual_journal_entry(payslip):
    """Recognizes a finalized payslip's cost — Debit Salary Expense, Credit
    Salary Payable, for the payslip's net_payable. Idempotent."""
    from handle.models import Account

    if payslip.journal_entry_id:
        return payslip.journal_entry

    org = payslip.org
    ensure_default_accounts(org)
    salary_expense = Account.objects.filter(org=org, name='Salary Expense', is_group=False).first()
    salary_payable = Account.objects.filter(org=org, name='Salary Payable', is_group=False).first()
    if not salary_expense or not salary_payable:
        raise ValueError("Required accounting accounts are missing for this organization.")

    with transaction.atomic():
        entry = create_journal_entry(
            org, entry_date=timezone.localdate(),
            lines=[
                {'account': salary_expense, 'debit': payslip.net_payable, 'remarks': f'Payslip — {payslip.member.name}'},
                {'account': salary_payable, 'credit': payslip.net_payable, 'remarks': f'Payslip — {payslip.member.name}'},
            ],
            description=f"Payroll accrual — {payslip.member.name} ({payslip.month_name})",
            created_by=payslip.finalized_by, source='payroll', status='approved',
        )
        payslip.journal_entry = entry
        payslip.save(update_fields=['journal_entry'])
    return entry


def post_payroll_payment_journal_entry(payslip):
    """Clears the payable when a payslip is actually marked paid — Debit
    Salary Payable, Credit Cash/Bank. Idempotent; requires the accrual entry
    to already exist (a payable can't be cleared before it's recognized)."""
    from handle.models import Account

    if payslip.payment_journal_entry_id:
        return payslip.payment_journal_entry
    if not payslip.journal_entry_id:
        raise ValueError("This payslip's payroll accrual entry hasn't been posted yet.")

    org = payslip.org
    ensure_default_accounts(org)
    salary_payable = Account.objects.filter(org=org, name='Salary Payable', is_group=False).first()
    credit_account = _resolve_cash_or_bank_account(org, 'cash')
    if not salary_payable or not credit_account:
        raise ValueError("Required accounting accounts are missing for this organization.")

    with transaction.atomic():
        entry = create_journal_entry(
            org, entry_date=payslip.payment_date or timezone.localdate(),
            lines=[
                {'account': salary_payable, 'debit': payslip.net_payable, 'remarks': f'Payslip — {payslip.member.name}'},
                {'account': credit_account, 'credit': payslip.net_payable, 'remarks': f'Payslip — {payslip.member.name}'},
            ],
            description=f"Payroll payment — {payslip.member.name} ({payslip.month_name})",
            created_by=payslip.finalized_by, source='payroll_payment', status='approved',
        )
        payslip.payment_journal_entry = entry
        payslip.save(update_fields=['payment_journal_entry'])
    return entry


def post_advance_salary_journal_entry(advance):
    """Money advanced to an employee ahead of payroll — Debit Employee
    Advances, Credit Cash/Bank. Idempotent."""
    from handle.models import Account

    if advance.journal_entry_id:
        return advance.journal_entry

    org = advance.org
    ensure_default_accounts(org)
    employee_advances = Account.objects.filter(org=org, name='Employee Advances', is_group=False).first()
    credit_account = _resolve_cash_or_bank_account(org, 'cash')
    if not employee_advances or not credit_account:
        raise ValueError("Required accounting accounts are missing for this organization.")

    with transaction.atomic():
        entry = create_journal_entry(
            org, entry_date=advance.effective_date,
            lines=[
                {'account': employee_advances, 'debit': advance.total_amount, 'remarks': f'Advance — {advance.member.name}'},
                {'account': credit_account, 'credit': advance.total_amount, 'remarks': f'Advance — {advance.member.name}'},
            ],
            description=f"Advance Salary — {advance.member.name}",
            created_by=advance.approved_by, source='advance_salary', status='approved',
        )
        advance.journal_entry = entry
        advance.save(update_fields=['journal_entry'])
    return entry


def _resolve_category_account(org, category, tx_type):
    """Resolves a FinancialTransaction's category to a GL account by name
    match; falls back to one generic seeded bucket rather than auto-creating
    a new Account per category (which would explode the Chart of Accounts).
    This is a known, deliberate simplification."""
    from handle.models import Account

    if category and category.name:
        match = Account.objects.filter(org=org, name__iexact=category.name, is_group=False).first()
        if match:
            return match
    fallback_name = 'Other Income' if tx_type == 'income' else 'Other Expense'
    return Account.objects.filter(org=org, name=fallback_name, is_group=False).first()


def post_income_journal_entry(tx):
    """A manually-logged Income transaction — Debit Cash/Bank, Credit the
    resolved (or fallback) income account. Idempotent."""
    if tx.journal_entry_id:
        return tx.journal_entry

    org = tx.org
    ensure_default_accounts(org)
    debit_account = _resolve_cash_or_bank_account(org, tx.payment_method)
    income_account = _resolve_category_account(org, tx.category, 'income')
    if not debit_account or not income_account:
        raise ValueError("Required accounting accounts are missing for this organization.")

    with transaction.atomic():
        entry = create_journal_entry(
            org, entry_date=tx.transaction_date,
            lines=[
                {'account': debit_account, 'debit': tx.amount, 'remarks': tx.title},
                {'account': income_account, 'credit': tx.amount, 'remarks': tx.title},
            ],
            description=f"Income — {tx.title}",
            reference=tx.reference_number, branch=tx.branch,
            created_by=tx.created_by, source='income', status='approved',
        )
        tx.journal_entry = entry
        tx.save(update_fields=['journal_entry'])
    return entry


def post_expense_journal_entry(tx):
    """A manually-logged Expense transaction — Debit the resolved (or
    fallback) expense account, Credit Cash/Bank. Idempotent."""
    if tx.journal_entry_id:
        return tx.journal_entry

    org = tx.org
    ensure_default_accounts(org)
    expense_account = _resolve_category_account(org, tx.category, 'expense')
    credit_account = _resolve_cash_or_bank_account(org, tx.payment_method)
    if not expense_account or not credit_account:
        raise ValueError("Required accounting accounts are missing for this organization.")

    with transaction.atomic():
        entry = create_journal_entry(
            org, entry_date=tx.transaction_date,
            lines=[
                {'account': expense_account, 'debit': tx.amount, 'remarks': tx.title},
                {'account': credit_account, 'credit': tx.amount, 'remarks': tx.title},
            ],
            description=f"Expense — {tx.title}",
            reference=tx.reference_number, branch=tx.branch,
            created_by=tx.created_by, source='expense', status='approved',
        )
        tx.journal_entry = entry
        tx.save(update_fields=['journal_entry'])
    return entry


def post_stock_adjustment_journal_entry(movement, direction):
    """A manual stock adjustment/damage movement outside Purchase/Sale flow.
    `direction` is 'increase' (found extra stock — a gain) or 'decrease'
    (shrinkage/damage — a loss). Both sides touch Inventory and a single
    Inventory Adjustment clearing account. Not idempotent by document (no
    header document exists) — set `movement.journal_entry` to guard against
    double-calls from the view layer, mirroring `StockMovement.journal_entry`."""
    from handle.models import Account, StockMovement

    if movement.journal_entry_id:
        return movement.journal_entry

    org = movement.org
    ensure_default_accounts(org)
    inventory = Account.objects.filter(org=org, name='Inventory', is_group=False).first()
    adjustment_account = Account.objects.filter(org=org, name='Inventory Adjustment', is_group=False).first()
    if not inventory or not adjustment_account:
        raise ValueError("Required accounting accounts are missing for this organization.")

    amount = movement.total_cost
    if direction == 'increase':
        lines = [
            {'account': inventory, 'debit': amount, 'remarks': f'Stock adjustment — {movement.item.name}'},
            {'account': adjustment_account, 'credit': amount, 'remarks': f'Stock adjustment — {movement.item.name}'},
        ]
    else:
        lines = [
            {'account': adjustment_account, 'debit': amount, 'remarks': f'Stock adjustment — {movement.item.name}'},
            {'account': inventory, 'credit': amount, 'remarks': f'Stock adjustment — {movement.item.name}'},
        ]

    with transaction.atomic():
        entry = create_journal_entry(
            org, entry_date=movement.movement_date, lines=lines,
            description=f"Stock Adjustment — {movement.item.name} ({direction})",
            branch=movement.branch, created_by=movement.created_by,
            source='stock_adjustment', status='approved',
        )
        movement.journal_entry = entry
        # StockMovement.save() re-applies its quantity delta to the item on
        # every call regardless of update_fields, so a plain .save() here
        # would double-count the adjustment. Use a raw update to set only
        # the FK without re-triggering that side effect.
        StockMovement.objects.filter(pk=movement.pk).update(journal_entry=entry)
    return entry


# ---------------------------------------------------------------------------
# Balances / Ledger / Reports — all read APPROVED entries only
# ---------------------------------------------------------------------------

def account_balance(account, date_from=None, as_of_date=None):
    """Signed balance on the account's normal-balance side."""
    from handle.models import JournalEntryLine

    qs = JournalEntryLine.objects.filter(account=account, entry__status='approved')
    if date_from:
        qs = qs.filter(entry__entry_date__gte=date_from)
    if as_of_date:
        qs = qs.filter(entry__entry_date__lte=as_of_date)
    totals = qs.aggregate(debit=Sum('debit'), credit=Sum('credit'))
    debit_total = totals['debit'] or Decimal('0.00')
    credit_total = totals['credit'] or Decimal('0.00')

    opening = account.opening_balance if not date_from else Decimal('0.00')
    if account.is_debit_normal():
        return opening + debit_total - credit_total
    return opening + credit_total - debit_total


def general_ledger(account, date_from, date_to):
    """Opening balance, each movement with a running balance, and closing balance."""
    from handle.models import JournalEntryLine

    debit_normal = account.is_debit_normal()
    # Opening balance for the period = the account's balance strictly before
    # date_from (which already folds in the raw opening_balance itself).
    if date_from:
        opening = account_balance(account, as_of_date=date_from - datetime.timedelta(days=1))
    else:
        opening = account.opening_balance

    qs = (JournalEntryLine.objects
          .filter(account=account, entry__status='approved',
                   entry__entry_date__gte=date_from, entry__entry_date__lte=date_to)
          .select_related('entry')
          .order_by('entry__entry_date', 'entry__id', 'line_order'))

    running = opening
    rows = []
    for line in qs:
        delta = (line.debit - line.credit) if debit_normal else (line.credit - line.debit)
        running += delta
        rows.append({
            'date': line.entry.entry_date,
            'voucher_number': line.entry.voucher_number,
            'reference': line.entry.reference,
            'remarks': line.remarks,
            'debit': line.debit,
            'credit': line.credit,
            'running_balance': running,
        })

    return {'opening_balance': opening, 'rows': rows, 'closing_balance': running}


def trial_balance(org, as_of_date):
    """Every postable account's debit/credit totals as of a date. Must net to zero."""
    from handle.models import Account

    rows = []
    total_debit = Decimal('0.00')
    total_credit = Decimal('0.00')
    for account in Account.objects.filter(org=org, is_group=False, is_active=True).order_by('code', 'name'):
        balance = account_balance(account, as_of_date=as_of_date)
        if balance == 0:
            continue
        if account.is_debit_normal():
            debit_amt, credit_amt = (balance, Decimal('0.00')) if balance >= 0 else (Decimal('0.00'), -balance)
        else:
            credit_amt, debit_amt = (balance, Decimal('0.00')) if balance >= 0 else (Decimal('0.00'), -balance)
        rows.append({'account': account, 'debit_total': debit_amt, 'credit_total': credit_amt})
        total_debit += debit_amt
        total_credit += credit_amt

    return {'rows': rows, 'total_debit': total_debit, 'total_credit': total_credit}


def profit_and_loss(org, date_from, date_to):
    """Income - COGS - Expense over a date range, from approved entries only."""
    from handle.models import Account, JournalEntryLine

    def _type_total(account_type):
        qs = JournalEntryLine.objects.filter(
            account__org=org, account__account_type=account_type, account__is_group=False,
            entry__status='approved', entry__entry_date__gte=date_from, entry__entry_date__lte=date_to,
        )
        totals = qs.aggregate(debit=Sum('debit'), credit=Sum('credit'))
        debit_total = totals['debit'] or Decimal('0.00')
        credit_total = totals['credit'] or Decimal('0.00')
        # Income is credit-normal; expense/cogs are debit-normal.
        if account_type == 'income':
            return credit_total - debit_total
        return debit_total - credit_total

    income = _type_total('income')
    cogs = _type_total('cogs')
    expense = _type_total('expense')
    gross_profit = income - cogs
    net_income = gross_profit - expense

    return {'income': income, 'cogs': cogs, 'expense': expense,
            'gross_profit': gross_profit, 'net_income': net_income}


def balance_sheet(org, as_of_date):
    """Assets / Liabilities / Equity as of a date. Equity folds in cumulative
    net income up to as_of_date as Retained Earnings, since there's no
    period-close/rollover step yet — this is what makes Assets == Liab+Equity
    hold true at any point in time, not just right after a year-end close."""
    from handle.models import Account

    def _accounts_for(account_type):
        rows = []
        total = Decimal('0.00')
        for account in Account.objects.filter(org=org, account_type=account_type, is_group=False, is_active=True).order_by('code', 'name'):
            balance = account_balance(account, as_of_date=as_of_date)
            if balance == 0:
                continue
            rows.append({'account': account, 'balance': balance})
            total += balance
        return rows, total

    assets, total_assets = _accounts_for('asset')
    liabilities, total_liabilities = _accounts_for('liability')
    equity, total_equity = _accounts_for('equity')

    # Cumulative net income (all approved entries up to as_of_date, no lower bound)
    # is folded into equity as retained earnings, so the sheet balances even
    # without a formal year-close/rollover process.
    pl = profit_and_loss(org, datetime.date(2000, 1, 1), as_of_date)
    total_equity_with_earnings = total_equity + pl['net_income']

    return {
        'assets': assets, 'total_assets': total_assets,
        'liabilities': liabilities, 'total_liabilities': total_liabilities,
        'equity': equity, 'total_equity': total_equity_with_earnings,
        'retained_earnings_current': pl['net_income'],
        'total_liab_equity': total_liabilities + total_equity_with_earnings,
    }
