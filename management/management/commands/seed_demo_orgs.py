"""
Management command: seed_demo_orgs

Creates three self-contained demo organizations — "Office Demo", "School Demo"
and "College Demo" — populated with ~3 months of interconnected history so every
dashboard, report and chart in the app looks like a real, actively-used system.

Safety model (this DB also holds real production orgs):
  - CREATE-ONLY. The command never reads, updates or deletes a row belonging to
    any organization other than the three it owns by name.
  - Every object is reachable from one of those three Organization rows, so
    --reset can clean up by deleting just those orgs and letting FK cascade.
  - Deterministic: a fixed RNG seed means re-running produces the same data.
  - Everything runs inside one transaction per org, so a failure rolls back
    cleanly instead of leaving a half-populated org behind.

Usage:
    python manage.py seed_demo_orgs                 # create all three + blogs
    python manage.py seed_demo_orgs --only office   # one org (office|school|college|blog)
    python manage.py seed_demo_orgs --reset         # delete the 3 demo orgs, then recreate
    python manage.py seed_demo_orgs --reset --no-create   # delete only
"""

import random
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify

from management.models import (
    Organization, CustomUser, Schooladmin, LeaveType, LeaveReport, BlogPost,
)
from handle.models import (
    Branch, Classification, Section, Shift, ShiftWindow, member, Staff,
    AttendingClassification, AttendanceRecord, Device, Course, CourseAttendance,
    PaySlip, PayrollPolicy, PayrollAdjustment, AdvanceSalary,
    StockCategory, StockItem, StockMovement,
    TransactionCategory, FinancialTransaction,
    Subject, ExamTerm, ResultRecord, Bill, BillItem,
    Event, Complaint, ResignationRecord, StaffPermission,
    FieldVisit, LocationPing, Client, ClientFollowUp,
    Task, TaskInstance, Notice, NoticeRead, IDCardTemplate,
)

# ── The three orgs this command owns. Nothing outside this set is ever touched.
OFFICE = "Office Demo"
SCHOOL = "School Demo"
COLLEGE = "College Demo"
DEMO_ORG_NAMES = (OFFICE, SCHOOL, COLLEGE)

# Demo logins all share this password and an @demo.meroattendance.com domain, so
# they are trivially distinguishable from real accounts.
DEMO_PASSWORD = "demo12345"
DEMO_DOMAIN = "demo.meroattendance.com"

# device_id values start here to stay clear of anything production uses.
DEVICE_ID_BASE = 900000

MONTHS_OF_HISTORY = 3

MALE_NAMES = [
    "Bikash", "Sagar", "Nabin", "Dipesh", "Rajan", "Suraj", "Kamal", "Roshan",
    "Bijay", "Anil", "Prakash", "Santosh", "Milan", "Umesh", "Deepak", "Arjun",
    "Niraj", "Pramod", "Ramesh", "Sanjay",
]
FEMALE_NAMES = [
    "Sunita", "Anita", "Sabita", "Nirmala", "Sita", "Manju", "Puja", "Renuka",
    "Rekha", "Kabita", "Sarita", "Bimala", "Laxmi", "Radha", "Muna", "Shanti",
    "Gita", "Sushmita", "Bhawana", "Alisha",
]
SURNAMES = [
    "Sharma", "Thapa", "Poudel", "Karki", "Shrestha", "Adhikari", "Bhandari",
    "Maharjan", "Tamang", "Basnet", "Gurung", "Rai", "Khadka", "Bhatt",
    "Lamichhane", "Pandey", "Chand", "Oli", "Dangol", "Malla", "Subedi",
    "Acharya", "Neupane", "Regmi", "Koirala",
]

STUDENT_FIRST = [
    "Aarav", "Aayush", "Bibek", "Dikshya", "Isha", "Kabir", "Nisha", "Prabin",
    "Riya", "Saurav", "Sneha", "Utsav", "Ayush", "Samir", "Prerana", "Anisha",
    "Sujal", "Aashish", "Manish", "Sabin", "Pooja", "Sarita", "Kritika",
    "Bishal", "Ankit", "Sujata", "Nabina", "Rojina", "Prashant", "Sandesh",
]


# ═══════════════════════════════════════════════════════════════════════════
# helpers
# ═══════════════════════════════════════════════════════════════════════════

def aware(d, hour=9, minute=0):
    """Make a tz-aware datetime from a date. Attendance timestamps must be
    aware — USE_TZ is on and naive values raise a RuntimeWarning."""
    naive = datetime.combine(d, time(hour, minute))
    return timezone.make_aware(naive) if timezone.is_naive(naive) else naive


def working_days(start, end):
    """Sun–Fri working week (Nepal): Saturday is the weekly holiday."""
    days, cur = [], start
    while cur <= end:
        if cur.weekday() != 5:  # 5 = Saturday
            days.append(cur)
        cur += timedelta(days=1)
    return days


def month_spans(end_date, months):
    """[(first_day, last_day, 'Month YYYY'), …] oldest→newest, ending at end_date's month."""
    spans = []
    y, m = end_date.year, end_date.month
    for _ in range(months):
        first = date(y, m, 1)
        nxt = date(y + 1, 1, 1) if m == 12 else date(y, m + 1, 1)
        last = min(nxt - timedelta(days=1), end_date)
        spans.append((first, last, first.strftime("%B %Y")))
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    return list(reversed(spans))


class Ctx:
    """Per-org counters so the command can report what it actually made."""

    def __init__(self):
        self.counts = {}

    def bump(self, key, n=1):
        self.counts[key] = self.counts.get(key, 0) + n

    def summary(self):
        return ", ".join(f"{k}={v}" for k, v in sorted(self.counts.items()))


class Command(BaseCommand):
    help = "Create/refresh the Office, School and College demo organizations."

    def add_arguments(self, parser):
        parser.add_argument("--only", choices=["office", "school", "college", "blog"],
                            help="Seed just one target.")
        parser.add_argument("--reset", action="store_true",
                            help="Delete the three demo orgs (and demo blog posts) first.")
        parser.add_argument("--no-create", action="store_true",
                            help="With --reset, delete only — don't recreate.")

    # ── entry point ─────────────────────────────────────────────────────────
    def handle(self, *args, **opts):
        self.rng = random.Random(20260725)
        only = opts.get("only")

        if opts.get("reset"):
            self._reset()
            if opts.get("no_create"):
                self.stdout.write(self.style.SUCCESS("Reset complete; nothing recreated."))
                return

        if only in (None, "office"):
            self._run("Office Demo", self.seed_office)
        if only in (None, "school"):
            self._run("School Demo", self.seed_school)
        if only in (None, "college"):
            self._run("College Demo", self.seed_college)
        if only in (None, "blog"):
            self._run("Blog posts", self.seed_blogs)

        self.stdout.write(self.style.SUCCESS("\nDemo seeding finished."))

    def _run(self, label, fn):
        # Seeding is create-only, so a second run over an existing demo org
        # would collide on unique keys. Refuse up front with a useful message
        # instead of surfacing a raw IntegrityError from deep in the builder.
        if label in DEMO_ORG_NAMES and Organization.objects.filter(name=label).exists():
            self.stdout.write(self.style.WARNING(
                f"\n▶ {label} already exists — skipping. "
                f"Use --reset to rebuild it from scratch."))
            return
        self.stdout.write(self.style.MIGRATE_HEADING(f"\n▶ {label}"))
        ctx = Ctx()
        with transaction.atomic():
            fn(ctx)
        self.stdout.write(self.style.SUCCESS(f"  ✓ {ctx.summary()}"))

    def _reset(self):
        """Delete ONLY the three demo orgs and their demo users/blogs. Every
        query here is filtered by the demo names/domain — no other org can match."""
        self.stdout.write(self.style.WARNING("Resetting demo orgs…"))
        qs = Organization.objects.filter(name__in=DEMO_ORG_NAMES)
        names = list(qs.values_list("name", flat=True))
        deleted, _ = qs.delete()
        # Demo logins are <local>@<orgslug>.demo.meroattendance.com — match on the
        # domain suffix only. (Matching "@" + DEMO_DOMAIN would never hit, since
        # the org slug sits between the @ and the demo domain.)
        users = CustomUser.objects.filter(email__endswith=DEMO_DOMAIN).delete()
        BlogPost.objects.filter(slug__startswith="ma-").delete()
        self.stdout.write(f"  removed {names or 'nothing'} ({deleted} rows incl. cascade)")

    # ── shared builders ─────────────────────────────────────────────────────
    def _org(self, name, category, features, member_limit=200):
        """Create the org + its schooladmin login. Uses get_or_create so a
        partial previous run is repaired rather than duplicated."""
        org, _ = Organization.objects.get_or_create(name=name, defaults={
            "category": category,
            "expire_on": timezone.now() + timedelta(days=365),
            "serial_key": f"DEMO-{slugify(name).upper()}",
            "new_serial_key": f"DEMO-{slugify(name).upper()}",
            "member_limit": member_limit,
            "address": "Kathmandu, Nepal",
        })
        org.member_limit = member_limit
        org.activate = True
        org.nepali_date = False
        # Turn on every feature this demo needs, and mirror it into the
        # superadmin allowlist so has_feature() actually returns True.
        allowed = set(org.allowed_features or [])
        for key, field in features.items():
            setattr(org, field, True)
            allowed.add(key)
        org.allowed_features = sorted(allowed)
        org.save()

        slug = slugify(name).replace("-", "")
        email = f"admin@{slug}.{DEMO_DOMAIN}"
        user, created = CustomUser.objects.get_or_create(
            username=email, defaults={"email": email, "user_type": "2",
                                      "first_name": name, "last_name": "Admin"})
        if created:
            user.set_password(DEMO_PASSWORD)
            user.user_type = "2"
            user.save()
        Schooladmin.objects.get_or_create(admin=user, org=org, defaults={"number": 9800000000})
        return org, user

    def _person_name(self, gender, i):
        first = (MALE_NAMES if gender == "Male" else FEMALE_NAMES)[i % 20]
        return f"{first} {SURNAMES[(i * 7) % len(SURNAMES)]}"

    def _make_member(self, org, idx, *, name, member_type, gender, classification=None,
                     branch=None, section=None, salary=0, designation="", shift=None,
                     with_login=False, staff_perms=None, roll=None):
        slug = slugify(org.name).replace("-", "")
        email = f"{slugify(name).replace('-', '.')}.{idx}@{slug}.{DEMO_DOMAIN}"
        m = member.objects.create(
            org=org, name=name, member_type=member_type, gender=gender,
            classification=classification, branch=branch, section=section,
            device_id=DEVICE_ID_BASE + org.id * 1000 + idx,
            email=email, phone=9800000000 + org.id * 1000 + idx,
            address="Kathmandu", status="active",
            salary_type="monthly", salary_amount=Decimal(salary),
            designation=designation, roll_number=roll,
            blood_group=self.rng.choice(["A+", "B+", "O+", "AB+", "A-", "O-"]),
            date_of_birth=date(1990 + (idx % 18), 1 + (idx % 12), 1 + (idx % 28)),
            id_card_valid_until=date(timezone.now().year + 2, 12, 31),
            tax_percentage=Decimal("1.00"),
            make_staff=with_login,
        )
        if shift:
            m.shifts.add(shift)
        if with_login:
            user, created = CustomUser.objects.get_or_create(
                username=email, defaults={"email": email, "user_type": "3",
                                          "first_name": name.split()[0],
                                          "last_name": name.split()[-1]})
            if created:
                user.set_password(DEMO_PASSWORD)
                user.user_type = "3"
                user.save()
            Staff.objects.get_or_create(member=m, defaults={
                "admin": user, "org": org, "number": m.phone})
            perms, _ = StaffPermission.objects.get_or_create(member=m, org=org)
            for flag in (staff_perms or []):
                setattr(perms, flag, True)
            perms.save()
        return m

    def _attendance(self, ctx, org, members, start, end, methods, absent_rate=0.06,
                    late_rate=0.18, half_day_members=()):
        """Bulk-create in/out scans across the window. Realistic enough that
        payroll, late-penalty and analytics all have something to chew on."""
        rows = []
        for m in members:
            for d in working_days(start, end):
                if self.rng.random() < absent_rate:
                    continue
                late = self.rng.random() < late_rate
                in_h, in_m = (9, self.rng.randint(16, 55)) if late else (8, self.rng.randint(35, 59))
                if late and self.rng.random() < 0.3:
                    in_h, in_m = 10, self.rng.randint(0, 20)
                method = self.rng.choice(methods)
                rows.append(AttendanceRecord(
                    mem=m, org=org, scanned_time=aware(d, in_h, in_m),
                    attendance_method=method))
                short = m.id in half_day_members and self.rng.random() < 0.25
                out_h = self.rng.choice([13, 14]) if short else self.rng.choice([17, 17, 18, 19])
                rows.append(AttendanceRecord(
                    mem=m, org=org, scanned_time=aware(d, out_h, self.rng.randint(0, 55)),
                    attendance_method=method))
        AttendanceRecord.objects.bulk_create(rows, batch_size=2000)
        ctx.bump("attendance", len(rows))

    def _leave_setup(self, org):
        types = []
        for nm, alloc, paid in [("Annual Leave", 12, True), ("Sick Leave", 10, True),
                                ("Casual Leave", 6, True), ("Unpaid Leave", 0, False)]:
            lt, _ = LeaveType.objects.get_or_create(
                org=org, name=nm, defaults={"annual_allocation": alloc, "is_paid": paid})
            types.append(lt)
        return types

    def _leaves(self, ctx, org, members, leave_types, start, end, per_member=2):
        reasons = ["Family function", "Medical checkup", "Personal work", "Travel",
                   "Fever and rest advised", "Wedding in family", "Home maintenance"]
        n = 0
        for m in members:
            for _ in range(self.rng.randint(0, per_member)):
                lt = self.rng.choice(leave_types)
                s = start + timedelta(days=self.rng.randint(0, max(1, (end - start).days - 3)))
                e = s + timedelta(days=self.rng.randint(0, 2))
                roll = self.rng.random()
                approved, rejected = (True, False) if roll < 0.7 else ((False, True) if roll < 0.85 else (False, False))
                LeaveReport.objects.create(
                    member=m, org=org, leave_type=lt, gap_start=s, gap_end=e,
                    reason=self.rng.choice(reasons), approved=approved,
                    rejected=rejected, seen=approved or rejected)
                n += 1
        ctx.bump("leaves", n)

    def _payroll(self, ctx, org, members, spans):
        """Payslips per member per month, with the same component breakdown the
        real payroll service produces so the payslip pages render fully."""
        PayrollPolicy.objects.get_or_create(org=org)
        n = 0
        for m in members:
            if not m.salary_amount:
                continue
            for i, (first, last, label) in enumerate(spans):
                gross = Decimal(m.salary_amount)
                present = len(working_days(first, last))
                allowance = (gross * Decimal("0.10")).quantize(Decimal("0.01"))
                bonus = (gross * Decimal("0.05")).quantize(Decimal("0.01")) if i == len(spans) - 1 else Decimal("0.00")
                pf = (gross * Decimal("0.10")).quantize(Decimal("0.01"))
                tax = (gross * Decimal("0.01")).quantize(Decimal("0.01"))
                ot_hours = Decimal(self.rng.choice([0, 0, 2, 4, 6]))
                ot_amount = (gross / Decimal(30) / Decimal(8) * ot_hours * Decimal("1.5")).quantize(Decimal("0.01"))
                net = (gross + allowance + bonus + ot_amount - pf - tax).quantize(Decimal("0.01"))
                status = "paid" if i < len(spans) - 1 else self.rng.choice(["draft", "finalized"])
                PaySlip.objects.create(
                    member=m, org=org, from_date=first, to_date=last, month_name=label,
                    total_days=(last - first).days + 1, present_days=present,
                    paid_leaves=self.rng.randint(0, 2), holidays=4,
                    unpaid_absences=self.rng.randint(0, 2),
                    salary_type="monthly", gross_salary=gross,
                    allowance_total=allowance, bonus_total=bonus,
                    tax_deduction=tax, pf_employee=pf, pf_employer=pf,
                    overtime_hours=ot_hours, overtime_amount=ot_amount,
                    overtime_rate_multiplier=Decimal("1.50"),
                    net_payable=net, status=status,
                    payment_date=last + timedelta(days=3) if status == "paid" else None,
                )
                n += 1
        ctx.bump("payslips", n)

    def _adjustments(self, ctx, org, members, today):
        n = 0
        for m in self.rng.sample(members, min(len(members), 10)):
            for kind, title, amt in [
                ("allowance", "Travel Allowance", 2500),
                ("bonus", "Festival Bonus", 8000),
                ("deduction", "Late Arrival Deduction", 750),
            ]:
                if self.rng.random() < 0.6:
                    PayrollAdjustment.objects.create(
                        org=org, member=m, adjustment_type=kind, title=title,
                        amount=Decimal(amt), effective_date=today - timedelta(days=self.rng.randint(5, 80)),
                        status="active", notes="Demo record")
                    n += 1
        ctx.bump("payroll_adjustments", n)

        adv = 0
        for m in self.rng.sample(members, min(len(members), 4)):
            total = Decimal(self.rng.choice([20000, 30000, 40000]))
            inst = 4
            AdvanceSalary.objects.create(
                org=org, member=m, total_amount=total, num_installments=inst,
                installment_amount=(total / inst).quantize(Decimal("0.01")),
                paid_installments=self.rng.randint(0, 2), remaining_balance=total,
                purpose="Medical / family expense", status="active",
                effective_date=today - timedelta(days=self.rng.randint(20, 70)))
            adv += 1
        ctx.bump("advances", adv)

    def _finance(self, ctx, org, user, today, income_titles, expense_titles):
        cats = {}
        for nm in income_titles:
            cats[nm] = TransactionCategory.objects.create(org=org, name=nm, transaction_type="income")
        for nm in expense_titles:
            cats[nm] = TransactionCategory.objects.create(org=org, name=nm, transaction_type="expense")
        ctx.bump("finance_categories", len(cats))

        n = 0
        for days_ago in range(0, MONTHS_OF_HISTORY * 30, 3):
            d = today - timedelta(days=days_ago)
            for titles, ttype, lo, hi in ((income_titles, "income", 15000, 120000),
                                          (expense_titles, "expense", 3000, 60000)):
                title = self.rng.choice(titles)
                FinancialTransaction.objects.create(
                    org=org, category=cats[title], transaction_type=ttype,
                    title=f"{title} — {d.strftime('%b %d')}",
                    amount=Decimal(self.rng.randrange(lo, hi, 500)),
                    transaction_date=d,
                    payment_method=self.rng.choice(["cash", "bank", "online", "card"]),
                    reference_number=f"TXN-{d.strftime('%y%m%d')}-{self.rng.randint(100, 999)}",
                    created_by=user)
                n += 1
        ctx.bump("transactions", n)

    def _stock(self, ctx, org, user, today):
        catalogue = [
            ("Stationery", ["Pen (box)", "A4 Paper Ream", "Whiteboard Marker", "Stapler", "File Folder"]),
            ("IT Equipment", ["USB Drive 32GB", "Wireless Mouse", "Keyboard", "Headset", "HDMI Cable"]),
            ("Cleaning", ["Hand Sanitizer 5L", "Floor Mop", "Dustbin", "Tissue Roll", "Detergent"]),
            ("Furniture", ["Office Chair", "Work Desk", "Bookshelf", "Filing Cabinet", "Notice Board"]),
        ]
        items, ncat = [], 0
        for cname, prods in catalogue:
            cat = StockCategory.objects.create(org=org, name=cname, description=f"{cname} inventory")
            ncat += 1
            for p in prods:
                it = StockItem.objects.create(
                    org=org, category=cat, name=p,
                    sku=f"{cname[:3].upper()}-{slugify(p)[:8].upper()}",
                    unit=self.rng.choice(["pcs", "box", "set"]),
                    quantity=Decimal(self.rng.randint(20, 200)),
                    low_stock_threshold=Decimal(10),
                    supplier=self.rng.choice(["Nepal Traders", "Everest Supplies", "Himalaya Store"]),
                    purchase_cost=Decimal(self.rng.randrange(150, 8000, 50)),
                    purchase_date=today - timedelta(days=self.rng.randint(30, 120)),
                    status="active")
                items.append(it)
        ctx.bump("stock_categories", ncat)
        ctx.bump("stock_items", len(items))

        n = 0
        for it in items:
            for _ in range(self.rng.randint(2, 5)):
                mtype = self.rng.choices(["in", "out", "out", "damage", "adjustment"], k=1)[0]
                StockMovement.objects.create(
                    org=org, item=it, movement_type=mtype,
                    quantity=Decimal(self.rng.randint(1, 15)),
                    unit_cost=it.purchase_cost,
                    movement_date=today - timedelta(days=self.rng.randint(1, MONTHS_OF_HISTORY * 30)),
                    note=f"Demo {mtype} movement", created_by=user)
                n += 1
        ctx.bump("stock_movements", n)

    def _tasks(self, ctx, org, user, members, today):
        titles = ["Submit monthly report", "Update staff records", "Conduct attendance audit",
                  "Prepare training material", "Review leave applications",
                  "Update inventory records", "Follow up with clients",
                  "Draft policy document", "Reconcile petty cash", "Plan team meeting"]
        ntask = ninst = 0
        for t in titles:
            task = Task.objects.create(
                org=org, title=t, description=f"{t} — recurring demo task.",
                priority=self.rng.choice(["low", "medium", "high", "urgent"]),
                task_type=self.rng.choice(["one_time", "weekly", "monthly"]),
                start_date=today - timedelta(days=self.rng.randint(20, 70)),
                due_date=today + timedelta(days=self.rng.randint(-10, 14)),
                due_time=time(17, 0), created_by=user, is_active=True,
                requires_approval=self.rng.random() < 0.4)
            assignees = self.rng.sample(members, min(len(members), self.rng.randint(1, 3)))
            task.assigned_to.set(assignees)
            ntask += 1
            for m in assignees:
                for off in (0, 7, 14):
                    due = task.due_date - timedelta(days=off)
                    status = self.rng.choices(
                        ["completed", "completed", "pending", "in_progress", "overdue"], k=1)[0]
                    TaskInstance.objects.create(
                        task=task, assigned_member=m, due_date=due, due_time=time(17, 0),
                        status=status,
                        completion_note="Done and verified." if status == "completed" else "",
                        completed_at=aware(due, 16, 30) if status == "completed" else None,
                        approval_status=("approved" if status == "completed" else "pending_approval")
                        if task.requires_approval else "not_required")
                    ninst += 1
        ctx.bump("tasks", ntask)
        ctx.bump("task_instances", ninst)

    def _complaints(self, ctx, org, members, today):
        kinds = ["Equipment Issue", "Salary Discrepancy", "Scheduling Conflict",
                 "Facility Maintenance", "Leave Request Denial"]
        n = 0
        for m in self.rng.sample(members, min(len(members), 8)):
            k = self.rng.choice(kinds)
            status = self.rng.choice(["pending", "reviewing", "resolved", "resolved"])
            Complaint.objects.create(
                org=org, filed_by=m, complaint_type=k, subject=f"{k} reported by {m.name}",
                description=f"Demo complaint regarding {k.lower()}. Please review and advise.",
                priority=self.rng.choice(["low", "medium", "high"]), status=status,
                admin_remarks="Resolved after review." if status == "resolved" else "",
                resolution_date=today - timedelta(days=self.rng.randint(1, 20)) if status == "resolved" else None)
            n += 1
        ctx.bump("complaints", n)

    def _events(self, ctx, org, today, titles):
        n = 0
        for t in titles:
            s = today + timedelta(days=self.rng.randint(-60, 40))
            Event.objects.create(
                org=org, title=t, event_type=self.rng.choice(
                    ["sports", "seminar", "meeting", "program", "holiday", "other"]),
                start_date=s, end_date=s + timedelta(days=self.rng.randint(0, 2)),
                location="Main Hall", description=f"{t} — demo event.",
                status="completed" if s < today else "upcoming")
            n += 1
        ctx.bump("events", n)

    def _notices(self, ctx, org, user, today, items):
        n = 0
        for title, body, priority, audience in items:
            Notice.objects.create(
                org=org, title=title, body=body, priority=priority, audience=audience,
                publish_at=aware(today - timedelta(days=self.rng.randint(0, 25)), 9, 0),
                created_by=user, send_email=False)
            n += 1
        # one scheduled + one expired so all three states are represented
        Notice.objects.create(
            org=org, title="Upcoming policy briefing",
            body="A briefing on the revised attendance policy will be held next week.",
            priority="normal", audience="org",
            publish_at=aware(today + timedelta(days=5), 10, 0), created_by=user)
        Notice.objects.create(
            org=org, title="Archived: last quarter results",
            body="Last quarter's summary has been archived.",
            priority="low", audience="org",
            publish_at=aware(today - timedelta(days=60), 9, 0),
            expires_at=aware(today - timedelta(days=10), 9, 0), created_by=user)
        ctx.bump("notices", n + 2)

    def _idcard_template(self, org, design="modern_corporate_vertical"):
        IDCardTemplate.objects.get_or_create(
            org=org, name=design,
            defaults={"is_default": True, "primary_color": "#1e293b",
                      "secondary_color": "#6366f1"})

    # ═══════════════════════════════════════════════════════════════════════
    # OFFICE DEMO — 20 employees, full HR/payroll/CRM/ops stack
    # ═══════════════════════════════════════════════════════════════════════
    def seed_office(self, ctx):
        today = timezone.localdate()
        start = today - timedelta(days=MONTHS_OF_HISTORY * 30)
        spans = month_spans(today, MONTHS_OF_HISTORY)

        org, user = self._org(OFFICE, "office", {
            "payroll": "feature_payroll", "leave": "feature_leave", "hrms": "feature_hrms",
            "tasks": "feature_tasks", "finance": "feature_finance", "stock": "feature_stock",
            "billing": "feature_billing", "complaints": "feature_complaints",
            "events": "feature_events", "branches": "feature_branches",
            "timesheet": "feature_timesheet", "id_cards": "feature_id_cards",
            "field_visits": "feature_field_visits", "clients": "feature_clients",
            "notices": "feature_notices", "bulk_export": "feature_bulk_export",
            "member_mgmt": "feature_member_mgmt", "notifications": "feature_notifications",
            "biometric": "rfid_based", "gps": "location_based", "qr": "qr_based",
            "manual": "manual_attendance", "wifi": "mutifeature_enable",
            "face_attendance": "feature_face_attendance",
            "qr_attendance": "enable_qr_attendance",
        }, member_limit=60)
        ctx.bump("org")

        branches = [Branch.objects.create(org=org, name=n, code=c, address=a,
                                          phone="01-555" + c, status="active")
                    for n, c, a in [("Head Office", "HO", "Kathmandu"),
                                    ("Lalitpur Branch", "LAL", "Lalitpur"),
                                    ("Pokhara Branch", "PKR", "Pokhara")]]
        ctx.bump("branches", len(branches))

        depts = [Classification.objects.create(org=org, name=n, branch=branches[i % 3], status="active")
                 for i, n in enumerate(["Administration", "Finance", "Human Resources",
                                        "Information Technology", "Operations", "Marketing"])]
        ctx.bump("departments", len(depts))

        shifts = []
        for nm, (sh, sm), (eh, em) in [("General Shift", (9, 0), (17, 0)),
                                       ("Morning Shift", (6, 0), (14, 0)),
                                       ("Evening Shift", (14, 0), (22, 0))]:
            s = Shift.objects.create(org=org, name=nm, is_active=True)
            ShiftWindow.objects.create(shift=s, order=1, start_time=time(sh, sm), end_time=time(eh, em))
            shifts.append(s)
        ctx.bump("shifts", len(shifts))

        for i, b in enumerate(branches):
            Device.objects.create(org=org, name=f"{b.name} Biometric", ip_address=f"192.168.1.{10+i}", port_no=4370)
        ctx.bump("devices", len(branches))

        titles = ["Manager", "Senior Officer", "Officer", "Executive", "Assistant",
                  "Team Lead", "Analyst", "Coordinator"]
        employees = []
        for i in range(20):
            gender = "Male" if i % 2 == 0 else "Female"
            dept = depts[i % len(depts)]
            employees.append(self._make_member(
                org, i + 1, name=self._person_name(gender, i), member_type="employee",
                gender=gender, classification=dept, branch=dept.branch,
                salary=self.rng.randrange(28000, 95000, 1000),
                designation=titles[i % len(titles)], shift=shifts[i % len(shifts)],
                with_login=(i < 6),
                staff_perms=["can_view_notices", "can_view_attendance", "can_request_leave",
                             "can_view_own_payslip", "can_view_tasks", "can_send_location",
                             "can_view_clients", "can_view_timesheets"]))
        ctx.bump("employees", len(employees))
        for e in employees[:6]:
            e.live_tracking_enabled = True
            e.save(update_fields=["live_tracking_enabled"])

        self._attendance(ctx, org, employees, start, today,
                         ["biometric", "biometric", "gps", "qr", "wifi", "manual", "facial"],
                         half_day_members={e.id for e in employees[:4]})
        self._leaves(ctx, org, employees, self._leave_setup(org), start, today)
        self._payroll(ctx, org, employees, spans)
        self._adjustments(ctx, org, employees, today)
        self._finance(ctx, org, user, today,
                      ["Service Revenue", "Consulting Fees", "Product Sales", "Maintenance Contract"],
                      ["Salaries", "Office Rent", "Utilities", "IT Equipment", "Marketing", "Travel"])
        self._stock(ctx, org, user, today)
        self._tasks(ctx, org, user, employees, today)
        self._complaints(ctx, org, employees, today)
        self._events(ctx, org, today, ["Quarterly Town Hall", "Team Building Outing",
                                       "Excel Skills Workshop", "Annual Picnic",
                                       "Safety & Health Training", "Dashain Celebration"])
        self._idcard_template(org, "modern_corporate_vertical")

        # ── CRM: clients + follow-ups ──────────────────────────────────────
        client_names = ["Everest Trading House", "Himalaya Softworks", "Annapurna Retail",
                        "Bagmati Logistics", "Sagarmatha Foods", "Kathmandu Print House",
                        "Lumbini Textiles", "Gandaki Motors"]
        clients = []
        for i, cn in enumerate(client_names):
            c = Client.objects.create(
                org=org, client_number=f"CL-{1000+i}", client_org_name=cn,
                contact_person=self._person_name("Male" if i % 2 else "Female", i + 3),
                phone=f"98510{i:05d}", email=f"contact@{slugify(cn)}.com.np",
                address="Kathmandu", industry=self.rng.choice(["Retail", "IT", "Logistics", "Manufacturing"]),
                status=self.rng.choice(["active", "active", "prospect", "inactive"]),
                billing_cycle=self.rng.choice(["monthly", "quarterly", "yearly"]),
                billing_amount=Decimal(self.rng.randrange(15000, 150000, 5000)),
                contract_start=today - timedelta(days=self.rng.randint(60, 300)),
                contract_end=today + timedelta(days=self.rng.randint(60, 300)),
                next_billing_date=today + timedelta(days=self.rng.randint(3, 30)),
                monthly_target=Decimal(50000), yearly_target=Decimal(600000),
                created_by=user, is_active=True)
            clients.append(c)
        ctx.bump("clients", len(clients))

        # ── Field visits + GPS trail ───────────────────────────────────────
        nfv = nping = nfu = 0
        field_staff = employees[:6]
        for m in field_staff:
            for day_off in range(0, MONTHS_OF_HISTORY * 30, 4):
                d = today - timedelta(days=day_off)
                if d.weekday() == 5:
                    continue
                cl = self.rng.choice(clients)
                lat = 27.7172 + self.rng.uniform(-0.05, 0.05)
                lng = 85.3240 + self.rng.uniform(-0.05, 0.05)
                fv = FieldVisit.objects.create(
                    org=org, member=m, latitude=lat, longitude=lng,
                    area_name=self.rng.choice(["Thamel", "Baneshwor", "Patan", "Balaju", "Kalanki"]),
                    accuracy_meters=self.rng.randint(4, 25), client=cl,
                    visited_at=aware(d, self.rng.randint(10, 16), self.rng.randint(0, 59)),
                    status=self.rng.choice(["approved", "approved", "pending"]))
                nfv += 1
                # a short GPS trail around each visit
                for step in range(4):
                    LocationPing.objects.create(
                        member=m, org=org,
                        latitude=lat + self.rng.uniform(-0.004, 0.004),
                        longitude=lng + self.rng.uniform(-0.004, 0.004),
                        accuracy_meters=self.rng.randint(4, 30),
                        tracked_at=aware(d, 10 + step, self.rng.randint(0, 59)))
                    nping += 1
                if self.rng.random() < 0.5:
                    ClientFollowUp.objects.create(
                        client=cl, org=org, visited_by=m,
                        feedback=self.rng.choice([
                            "Client satisfied with current service.",
                            "Requested a revised quotation.",
                            "Renewal discussion scheduled.",
                            "Raised a minor support issue; logged for follow-up."]),
                        follow_up_date=d,
                        next_follow_up_date=d + timedelta(days=self.rng.randint(7, 30)),
                        field_visit=fv, created_by=user)
                    nfu += 1
        ctx.bump("field_visits", nfv)
        ctx.bump("location_pings", nping)
        ctx.bump("client_followups", nfu)

        # ── Resignations ───────────────────────────────────────────────────
        nres = 0
        for m in employees[-3:]:
            rd = today - timedelta(days=self.rng.randint(10, 60))
            ResignationRecord.objects.create(
                org=org, member=m, resignation_date=rd, notice_period_days=30,
                last_working_day=rd + timedelta(days=30),
                reason=self.rng.choice(["Better opportunity", "Relocating", "Higher studies"]),
                status=self.rng.choice(["pending", "approved", "completed"]),
                clearance_status=self.rng.random() < 0.5,
                final_settlement_status=self.rng.random() < 0.4)
            nres += 1
        ctx.bump("resignations", nres)

        # ── Corporate billing to clients ───────────────────────────────────
        nbill = 0
        for i, m in enumerate(employees[:8]):
            issue = today - timedelta(days=self.rng.randint(5, 70))
            total = Decimal(self.rng.randrange(5000, 40000, 500))
            paid_roll = self.rng.random()
            paid = total if paid_roll < 0.5 else (total / 2 if paid_roll < 0.75 else Decimal("0"))
            status = "Paid" if paid == total else ("Partial" if paid > 0 else "Unpaid")
            b = Bill.objects.create(
                org=org, member=m, invoice_number=f"OD-INV-{2000+i}",
                issue_date=issue, due_date=issue + timedelta(days=15),
                billing_type="custom", base_amount=total, total_amount=total,
                amount_paid=paid, status=status, generated_by=user,
                remarks="Demo corporate invoice", is_sent=True, sent_at=aware(issue, 10))
            BillItem.objects.create(bill=b, description="Professional services",
                                    fee_type="misc", amount=total)
            nbill += 1
        ctx.bump("bills", nbill)

        self._notices(ctx, org, user, today, [
            ("Office closed on Friday", "The office will remain closed this Friday for the national holiday. Planned work should be completed by Thursday.", "high", "org"),
            ("New attendance policy in effect", "From this month, check-in after 9:15 AM is recorded as late. Three late marks in a month trigger a half-day deduction.", "urgent", "org"),
            ("Quarterly town hall — all staff", "Join the quarterly town hall in the main hall at 3 PM. Department heads will present Q results.", "normal", "org"),
            ("IT maintenance window", "Email and the staff portal will be briefly unavailable on Sunday between 1 AM and 4 AM.", "low", "org"),
            ("Field staff: submit visit reports", "Please make sure all client visit reports for this month are submitted by the 28th.", "high", "staff_only"),
        ])

    # ═══════════════════════════════════════════════════════════════════════
    # SCHOOL DEMO — 50 students, teachers, classes/sections/subjects, results
    # ═══════════════════════════════════════════════════════════════════════
    def seed_school(self, ctx):
        today = timezone.localdate()
        start = today - timedelta(days=MONTHS_OF_HISTORY * 30)
        spans = month_spans(today, MONTHS_OF_HISTORY)

        org, user = self._org(SCHOOL, "school", {
            "payroll": "feature_payroll", "leave": "feature_leave", "hrms": "feature_hrms",
            "results": "feature_results", "billing": "feature_billing",
            "student_mgmt": "feature_student_mgmt", "courses": "feature_courses",
            "finance": "feature_finance", "complaints": "feature_complaints",
            "events": "feature_events", "stock": "feature_stock",
            "id_cards": "feature_id_cards", "notices": "feature_notices",
            "branches": "feature_branches", "member_mgmt": "feature_member_mgmt",
            "study_gap": "feature_study_gap", "tasks": "feature_tasks",
            "biometric": "rfid_based", "qr": "qr_based", "manual": "manual_attendance",
            "gps": "location_based", "face_attendance": "feature_face_attendance",
        }, member_limit=120)
        ctx.bump("org")

        branch = Branch.objects.create(org=org, name="Main Campus", code="MC",
                                       address="Kathmandu", status="active")
        ctx.bump("branches")

        # Classes 6–10, two sections each
        classes, sections = [], {}
        for grade in range(6, 11):
            c = Classification.objects.create(org=org, name=f"Class {grade}",
                                              branch=branch, status="active")
            classes.append(c)
            sections[c.id] = [
                Section.objects.create(org=org, branch=branch, classification=c,
                                       name=s, code=f"{grade}{s}", status="active")
                for s in ("A", "B")]
        ctx.bump("classes", len(classes))
        ctx.bump("sections", sum(len(v) for v in sections.values()))

        shift = Shift.objects.create(org=org, name="School Hours", is_active=True)
        ShiftWindow.objects.create(shift=shift, order=1, start_time=time(9, 30), end_time=time(15, 30))
        ctx.bump("shifts")

        # ── Staff: principal, accountant, receptionist, 10 teachers ────────
        staff = []
        leadership = [("Principal", "Principal", 95000), ("Accountant", "Accountant", 55000),
                      ("Receptionist", "Receptionist", 32000)]
        for i, (role, desig, sal) in enumerate(leadership):
            gender = "Male" if i == 0 else "Female"
            staff.append(self._make_member(
                org, 900 + i, name=self._person_name(gender, i + 4), member_type="staff",
                gender=gender, classification=classes[0], branch=branch, salary=sal,
                designation=desig, shift=shift, with_login=True,
                staff_perms=["can_view_notices", "can_view_members", "can_view_attendance",
                             "can_request_leave", "can_view_own_payslip",
                             "can_publish_results", "can_view_result_report"]))
        teachers = []
        for i in range(10):
            gender = "Male" if i % 2 else "Female"
            t = self._make_member(
                org, 800 + i, name=self._person_name(gender, i + 9), member_type="teacher",
                gender=gender, classification=classes[i % len(classes)], branch=branch,
                salary=self.rng.randrange(32000, 62000, 1000), designation="Teacher",
                shift=shift, with_login=(i < 4),
                staff_perms=["can_view_notices", "can_view_attendance", "can_add_attendance",
                             "can_request_leave", "can_view_own_payslip",
                             "can_view_result_report", "can_view_members"])
            teachers.append(t)
            staff.append(t)
        ctx.bump("staff", len(staff))

        # teachers own their classes so the staff dashboard shows assignments
        for i, t in enumerate(teachers):
            if getattr(t, "staff", None):
                AttendingClassification.objects.get_or_create(
                    staff=t.staff.admin, classification=classes[i % len(classes)])

        # ── 50 students spread across classes/sections ─────────────────────
        students = []
        for i in range(50):
            cls = classes[i % len(classes)]
            sec = sections[cls.id][i % 2]
            gender = "Male" if i % 2 == 0 else "Female"
            first = STUDENT_FIRST[i % len(STUDENT_FIRST)]
            name = f"{first} {SURNAMES[(i * 5) % len(SURNAMES)]}"
            s = self._make_member(
                org, i + 1, name=name, member_type="student", gender=gender,
                classification=cls, branch=branch, section=sec, salary=0,
                designation="Student", shift=shift,
                with_login=(i < 5),
                staff_perms=["can_view_notices", "can_view_attendance", "can_request_leave"],
                roll=f"{cls.name.split()[-1]}{sec.name}-{i+1:03d}")
            # guardian contacts drive the parent-facing bill/result emails
            s.guardian_name = f"{SURNAMES[(i * 5) % len(SURNAMES)]} (Guardian)"
            s.guardian_email = f"guardian{i+1}@{slugify(org.name).replace('-','')}.{DEMO_DOMAIN}"
            s.guardian_phone = 9840000000 + i
            s.save(update_fields=["guardian_name", "guardian_email", "guardian_phone"])
            students.append(s)
        ctx.bump("students", len(students))

        # ── Subjects per class ─────────────────────────────────────────────
        subject_defs = [("English", "ENG"), ("Mathematics", "MATH"), ("Science", "SCI"),
                        ("Social Studies", "SOC"), ("Computer", "CMP"), ("Nepali", "NEP")]
        subjects = {}
        nsub = 0
        for ci, cls in enumerate(classes):
            subjects[cls.id] = []
            for si, (sn, sc) in enumerate(subject_defs):
                sub = Subject.objects.create(
                    org=org, classification=cls, name=sn, code=f"{sc}-{cls.name.split()[-1]}",
                    teacher=teachers[(ci + si) % len(teachers)].staff.admin
                    if getattr(teachers[(ci + si) % len(teachers)], "staff", None) else None,
                    credit_hour=Decimal("4.00"), full_marks=Decimal(100), pass_marks=Decimal(40),
                    monthly_fee=Decimal(self.rng.randrange(300, 900, 50)), status="active")
                subjects[cls.id].append(sub)
                nsub += 1
        ctx.bump("subjects", nsub)

        everyone = students + staff
        self._attendance(ctx, org, everyone, start, today,
                         ["biometric", "qr", "manual", "facial", "biometric"],
                         absent_rate=0.08, late_rate=0.15)
        self._leaves(ctx, org, everyone, self._leave_setup(org), start, today, per_member=1)
        self._payroll(ctx, org, staff, spans)
        self._adjustments(ctx, org, staff, today)
        self._finance(ctx, org, user, today,
                      ["Tuition Fees", "Admission Fees", "Examination Fees", "Transport Fees"],
                      ["Salaries", "Utilities", "Lab Supplies", "Maintenance", "Library Books"])
        self._stock(ctx, org, user, today)
        self._tasks(ctx, org, user, staff, today)
        self._complaints(ctx, org, students[:8], today)
        self._events(ctx, org, today, ["Annual Sports Day", "Science Exhibition",
                                       "Parents' Day", "Inter-house Quiz",
                                       "Saraswati Puja", "Annual Function"])
        self._idcard_template(org, "school_style_vertical")

        # ── Exams + results ────────────────────────────────────────────────
        nexam = nres = 0
        for label, offset, published in [("First Terminal Exam", 70, True),
                                         ("Mid Terminal Exam", 35, True),
                                         ("Third Terminal Exam", -12, False)]:
            for cls in classes:
                ex = ExamTerm.objects.create(
                    org=org, classification=cls, name=f"{label} — {cls.name}",
                    academic_year=str(today.year),
                    start_date=today - timedelta(days=offset),
                    end_date=today - timedelta(days=offset - 5),
                    status="published" if published else "marks_entry",
                    is_published=published)
                nexam += 1
                if not published:
                    continue
                for st in [s for s in students if s.classification_id == cls.id]:
                    for sub in subjects[cls.id]:
                        marks = Decimal(self.rng.randint(33, 98))
                        ResultRecord.objects.create(
                            student=st, exam=ex, subject=sub, obtained_marks=marks,
                            grade=("A+" if marks >= 90 else "A" if marks >= 80 else
                                   "B+" if marks >= 70 else "B" if marks >= 60 else
                                   "C" if marks >= 40 else "D"),
                            is_absent=False, created_by=user)
                        nres += 1
        ctx.bump("exams", nexam)
        ctx.bump("results", nres)

        # ── Fee bills + payments ───────────────────────────────────────────
        nbill = 0
        for i, st in enumerate(students):
            for j, (first, last, label) in enumerate(spans):
                base = Decimal(self.rng.randrange(2500, 6500, 250))
                discount = Decimal(500) if i % 9 == 0 else Decimal(0)
                total = base - discount
                roll = self.rng.random()
                paid = total if roll < 0.62 else (total / 2 if roll < 0.82 else Decimal("0"))
                status = "Paid" if paid == total else ("Partial" if paid > 0 else "Unpaid")
                b = Bill.objects.create(
                    org=org, member=st, classification=st.classification, section=st.section,
                    invoice_number=f"SD-{first.strftime('%y%m')}-{i+1:04d}",
                    issue_date=first, due_date=first + timedelta(days=15),
                    billing_month=first.month, billing_year=first.year,
                    billing_type="monthly_fee", base_amount=base,
                    discount_amount=discount, total_amount=total, amount_paid=paid,
                    status=status, generated_by=user, is_sent=True,
                    sent_at=aware(first, 10), sent_method="email",
                    remarks=f"{label} monthly fee")
                for sub in subjects[st.classification_id][:3]:
                    BillItem.objects.create(bill=b, subject=sub, description=f"{sub.name} fee",
                                            fee_type="monthly",
                                            amount=(base / 3).quantize(Decimal("0.01")))
                nbill += 1
        ctx.bump("bills", nbill)

        self._notices(ctx, org, user, today, [
            ("Parents' Day this Saturday", "All guardians are invited to Parents' Day this Saturday from 10 AM. Class teachers will share progress reports.", "high", "org"),
            ("Third terminal exam routine published", "The routine for the third terminal examination is now on the notice board and the student portal.", "urgent", "students_only"),
            ("Winter uniform from next week", "Students must wear the winter uniform starting Monday next week.", "normal", "students_only"),
            ("Staff meeting — Friday 4 PM", "All teaching staff are required to attend the monthly review meeting on Friday at 4 PM.", "high", "staff_only"),
            ("Library books due", "Please return all borrowed library books before the terminal examination begins.", "low", "org"),
        ])

    # ═══════════════════════════════════════════════════════════════════════
    # COLLEGE DEMO — course/semester based attendance, internal + final marks
    # ═══════════════════════════════════════════════════════════════════════
    def seed_college(self, ctx):
        today = timezone.localdate()
        start = today - timedelta(days=MONTHS_OF_HISTORY * 30)
        spans = month_spans(today, MONTHS_OF_HISTORY)

        org, user = self._org(COLLEGE, "college", {
            "payroll": "feature_payroll", "leave": "feature_leave", "hrms": "feature_hrms",
            "results": "feature_results", "billing": "feature_billing",
            "student_mgmt": "feature_student_mgmt", "courses": "feature_courses",
            "finance": "feature_finance", "complaints": "feature_complaints",
            "events": "feature_events", "id_cards": "feature_id_cards",
            "notices": "feature_notices", "branches": "feature_branches",
            "member_mgmt": "feature_member_mgmt", "study_gap": "feature_study_gap",
            "timesheet": "feature_timesheet", "stock": "feature_stock",
            "tasks": "feature_tasks",
            "biometric": "rfid_based", "qr": "qr_based", "manual": "manual_attendance",
            "gps": "location_based", "qr_attendance": "enable_qr_attendance",
        }, member_limit=120)
        # Course-based attendance is what distinguishes this org.
        org.course_based_attendance = True
        org.save(update_fields=["course_based_attendance"])
        ctx.bump("org")

        branch = Branch.objects.create(org=org, name="City Campus", code="CC",
                                       address="Kathmandu", status="active")
        ctx.bump("branches")

        # No Semester model exists in this schema — semesters are modelled as
        # Classification rows, which is what the course/result pages already read.
        programmes = [("BCA", 4), ("BBA", 4), ("BSc CSIT", 3)]
        semesters, sections = [], {}
        for prog, nsem in programmes:
            for s in range(1, nsem + 1):
                c = Classification.objects.create(
                    org=org, name=f"{prog} — Semester {s}", branch=branch, status="active")
                semesters.append(c)
                sections[c.id] = [Section.objects.create(
                    org=org, branch=branch, classification=c, name="A",
                    code=f"{slugify(prog).upper()}{s}A", status="active")]
        ctx.bump("semesters", len(semesters))

        shift = Shift.objects.create(org=org, name="Day Programme", is_active=True)
        ShiftWindow.objects.create(shift=shift, order=1, start_time=time(6, 30), end_time=time(11, 30))
        ctx.bump("shifts")

        # ── Faculty ────────────────────────────────────────────────────────
        faculty = []
        for i in range(8):
            gender = "Male" if i % 2 else "Female"
            faculty.append(self._make_member(
                org, 700 + i, name=self._person_name(gender, i + 2), member_type="teacher",
                gender=gender, classification=semesters[i % len(semesters)], branch=branch,
                salary=self.rng.randrange(45000, 90000, 1000), designation="Lecturer",
                shift=shift, with_login=(i < 3),
                staff_perms=["can_view_notices", "can_view_attendance", "can_add_attendance",
                             "can_view_courses", "can_manage_courses", "can_request_leave",
                             "can_view_own_payslip", "can_view_result_report"]))
        ctx.bump("faculty", len(faculty))

        # ── Courses (with teacher + semester links) ────────────────────────
        course_defs = {
            "BCA": ["Programming in C", "Digital Logic", "Database Management",
                    "Web Technology", "Operating Systems", "Software Engineering"],
            "BBA": ["Principles of Management", "Business Statistics", "Microeconomics",
                    "Financial Accounting", "Marketing Fundamentals", "Business Law"],
            "BSc CSIT": ["Data Structures", "Computer Networks", "Discrete Mathematics",
                         "Artificial Intelligence", "Computer Graphics", "Cryptography"],
        }
        courses = []
        for sem in semesters:
            prog = sem.name.split(" — ")[0]
            pool = course_defs[prog]
            for k in range(3):
                cname = pool[(semesters.index(sem) + k) % len(pool)]
                teacher = faculty[(semesters.index(sem) + k) % len(faculty)]
                c = Course.objects.create(
                    org=org, branch=branch, name=cname,
                    code=f"{slugify(prog).upper()[:3]}{semesters.index(sem)+1}{k+1}",
                    description=f"{cname} for {sem.name}.",
                    credit_hour=Decimal("3.00"), status="active",
                    teacher=teacher.staff.admin if getattr(teacher, "staff", None) else None)
                c.classifications.add(sem)
                c.sections.add(*sections[sem.id])
                courses.append(c)
        ctx.bump("courses", len(courses))

        # ── Students enrolled into their semester's courses ────────────────
        students = []
        for i in range(45):
            sem = semesters[i % len(semesters)]
            gender = "Male" if i % 2 == 0 else "Female"
            name = f"{STUDENT_FIRST[(i + 7) % len(STUDENT_FIRST)]} {SURNAMES[(i * 3) % len(SURNAMES)]}"
            st = self._make_member(
                org, i + 1, name=name, member_type="student", gender=gender,
                classification=sem, branch=branch, section=sections[sem.id][0], salary=0,
                designation="Student", shift=shift, with_login=(i < 5),
                staff_perms=["can_view_notices", "can_view_attendance", "can_request_leave"],
                roll=f"{slugify(sem.name).upper()[:6]}-{i+1:03d}")
            st.guardian_name = f"{SURNAMES[(i * 3) % len(SURNAMES)]} (Guardian)"
            st.guardian_email = f"guardian{i+1}@collegedemo.{DEMO_DOMAIN}"
            st.guardian_phone = 9841000000 + i
            st.save(update_fields=["guardian_name", "guardian_email", "guardian_phone"])
            st.courses.set([c for c in courses if sem in c.classifications.all()])
            students.append(st)
        ctx.bump("students", len(students))

        everyone = students + faculty
        self._attendance(ctx, org, everyone, start, today,
                         ["qr", "biometric", "manual", "gps"], absent_rate=0.10, late_rate=0.2)
        self._leaves(ctx, org, everyone, self._leave_setup(org), start, today, per_member=1)
        self._payroll(ctx, org, faculty, spans)
        self._adjustments(ctx, org, faculty, today)
        self._finance(ctx, org, user, today,
                      ["Semester Fees", "Admission Fees", "Exam Fees", "Lab Fees"],
                      ["Salaries", "Utilities", "Lab Equipment", "Library", "Maintenance"])
        self._tasks(ctx, org, user, faculty, today)
        self._complaints(ctx, org, students[:6], today)
        self._events(ctx, org, today, ["Freshers' Welcome", "Tech Fest", "Industry Seminar",
                                       "Sports Week", "Project Exhibition"])
        self._idcard_template(org, "student_landscape")

        # ── Course-wise class attendance (the "timetable" record) ──────────
        nca = 0
        topics = ["Introduction & syllabus", "Chapter 1 walkthrough", "Problem solving session",
                  "Lab practical", "Revision & quiz", "Case study discussion",
                  "Assignment review", "Guest lecture"]
        for c in courses:
            for d in working_days(start, today)[::5]:
                CourseAttendance.objects.create(
                    org=org, course=c, staff=c.teacher, branch=branch,
                    classification=c.classifications.first(),
                    section=c.sections.first(), attendance_date=d,
                    topic_taught=self.rng.choice(topics))
                nca += 1
        ctx.bump("course_attendance", nca)

        # ── Internal assessment + final results ────────────────────────────
        nexam = nres = 0
        for label, offset, published, full in [("Internal Assessment I", 60, True, 20),
                                               ("Internal Assessment II", 25, True, 20),
                                               ("Semester Final", -8, False, 80)]:
            for sem in semesters:
                sem_courses = [c for c in courses if sem in c.classifications.all()]
                if not sem_courses:
                    continue
                ex = ExamTerm.objects.create(
                    org=org, classification=sem, name=f"{label} — {sem.name}",
                    academic_year=str(today.year),
                    start_date=today - timedelta(days=offset),
                    end_date=today - timedelta(days=offset - 4),
                    status="published" if published else "marks_entry",
                    is_published=published)
                nexam += 1
                if not published:
                    continue
                # ResultRecord points at Subject, so mirror each course as a Subject row
                for c in sem_courses:
                    sub, _ = Subject.objects.get_or_create(
                        org=org, classification=sem, section=None, name=c.name,
                        defaults={"code": c.code, "credit_hour": c.credit_hour,
                                  "full_marks": Decimal(full), "pass_marks": Decimal(full) * Decimal("0.4"),
                                  "teacher": c.teacher, "status": "active"})
                    for st in [s for s in students if s.classification_id == sem.id]:
                        marks = Decimal(self.rng.randint(int(full * 0.4), full))
                        pct = float(marks) / full * 100
                        ResultRecord.objects.create(
                            student=st, exam=ex, subject=sub, obtained_marks=marks,
                            grade=("A" if pct >= 80 else "B+" if pct >= 70 else
                                   "B" if pct >= 60 else "C" if pct >= 50 else "D"),
                            is_absent=False, created_by=user)
                        nres += 1
        ctx.bump("exams", nexam)
        ctx.bump("results", nres)

        # ── Semester fee bills ─────────────────────────────────────────────
        nbill = 0
        for i, st in enumerate(students):
            total = Decimal(self.rng.randrange(35000, 65000, 1000))
            roll = self.rng.random()
            paid = total if roll < 0.55 else (total / 2 if roll < 0.8 else Decimal("0"))
            status = "Paid" if paid == total else ("Partial" if paid > 0 else "Unpaid")
            issue = today - timedelta(days=self.rng.randint(20, 80))
            b = Bill.objects.create(
                org=org, member=st, classification=st.classification, section=st.section,
                invoice_number=f"CD-{issue.strftime('%y%m')}-{i+1:04d}",
                issue_date=issue, due_date=issue + timedelta(days=30),
                billing_type="course_wise", base_amount=total, total_amount=total,
                amount_paid=paid, status=status, generated_by=user, is_sent=True,
                sent_at=aware(issue, 11), sent_method="email",
                remarks=f"{st.classification.name} semester fee")
            for c in list(st.courses.all())[:3]:
                BillItem.objects.create(bill=b, description=f"{c.name} course fee",
                                        fee_type="course",
                                        amount=(total / 3).quantize(Decimal("0.01")))
            nbill += 1
        ctx.bump("bills", nbill)

        self._notices(ctx, org, user, today, [
            ("Semester final routine published", "The semester final examination routine is now available on the student portal. Check your programme and semester carefully.", "urgent", "students_only"),
            ("Attendance below 75% — warning", "Students with attendance below 75% will not be permitted to sit the semester final. Check your attendance report.", "high", "students_only"),
            ("Tech Fest registrations open", "Registrations for the annual Tech Fest are open until the end of this month.", "normal", "org"),
            ("Faculty: submit internal marks", "All lecturers must submit internal assessment marks before the end of the week.", "high", "staff_only"),
            ("Library timings extended", "The library will remain open until 8 PM during the examination period.", "low", "org"),
        ])

    # ═══════════════════════════════════════════════════════════════════════
    # BLOG — 20 SEO posts using the existing BlogPost model
    # ═══════════════════════════════════════════════════════════════════════
    BLOG_TOPICS = [
        ("Attendance Management Software in Nepal: A Complete 2026 Guide", "attendance-management",
         "attendance management software nepal, attendance system, employee attendance tracking",
         "Attendance Management",
         "How modern attendance management replaces registers and spreadsheets, and what to look for when choosing a system in Nepal."),
        ("Payroll Software for Nepali Businesses: PF, SSF and TDS Explained", "payroll",
         "payroll software nepal, pf ssf calculation, tds payroll nepal, salary management",
         "Payroll",
         "A practical walkthrough of running compliant payroll in Nepal — provident fund, social security fund and tax deducted at source."),
        ("What Is an HRMS and Does Your Organisation Actually Need One?", "hrms",
         "hrms nepal, human resource management system, hr software",
         "HRMS",
         "HRMS covers hiring to exit. Here is what each module does and how to tell whether you are ready for one."),
        ("Face Attendance: How Facial Recognition Attendance Works", "face-attendance",
         "face attendance, facial recognition attendance, contactless attendance",
         "Face Attendance",
         "Facial recognition turns any tablet into a contactless attendance terminal. Here is how the technology works and where it fits."),
        ("QR Code Attendance: Fast, Cheap and Surprisingly Secure", "qr-attendance",
         "qr code attendance, qr attendance system, dynamic qr attendance",
         "QR Attendance",
         "Dynamic QR codes make attendance quick to roll out without hardware. We cover setup, security and best practice."),
        ("GPS Attendance and Geo-Fencing for Field Teams", "gps-attendance",
         "gps attendance, geofence attendance, field staff tracking nepal",
         "GPS Attendance",
         "Location-based attendance lets field staff check in from site. Geo-fencing keeps it honest."),
        ("Leave Management: Policies, Balances and Approval Workflows", "leave-management",
         "leave management system, leave policy nepal, online leave application",
         "Leave Management",
         "From annual allocation to approval chains — how to design a leave policy your team will actually follow."),
        ("School Attendance Systems: Cutting Roll Call to Seconds", "school-attendance",
         "school attendance system nepal, student attendance software",
         "School Attendance",
         "Automated roll call frees teaching time and gives parents same-day visibility of absences."),
        ("College Attendance: Managing Course and Semester-Wise Records", "college-attendance",
         "college attendance system, course wise attendance, semester attendance",
         "College Attendance",
         "Colleges need attendance per course, not per day. Here is how course-based tracking works."),
        ("Shift Management: Handling Split, Rotating and Night Shifts", "shift-management",
         "shift management software, roster management, split shift attendance",
         "Shift Management",
         "Split shifts and rotating rosters break naive attendance systems. Here is how to model them properly."),
        ("Client Management (CRM) for Service Businesses in Nepal", "client-management",
         "client management software nepal, crm nepal, client follow up",
         "Client Management",
         "Track clients, contracts, billing cycles and follow-ups so nothing slips between visits."),
        ("Finance Tracking: Income, Expense and Cash-Flow Visibility", "finance",
         "finance management software nepal, income expense tracking, cash flow",
         "Finance",
         "A simple income/expense ledger, categorised properly, answers most questions a manager asks."),
        ("Stock and Inventory Management Without the Spreadsheet Chaos", "stock",
         "stock management software nepal, inventory management, stock movement",
         "Stock",
         "Track items, movements and low-stock thresholds so you reorder before you run out."),
        ("Task Management: Assigning, Tracking and Approving Work", "task-management",
         "task management software, staff task tracking, recurring tasks",
         "Task Management",
         "Recurring tasks, proof of completion and approval workflows turn intentions into accountability."),
        ("Field Visit Tracking: Proof of Visit Without Micromanaging", "field-visit",
         "field visit tracking, field staff app, visit report software",
         "Field Visit",
         "Field visit logs with GPS and photos give you proof of visit while respecting your team's autonomy."),
        ("ID Card Generation: Printing Professional Cards In-House", "id-cards",
         "id card software nepal, student id card, employee id card printing",
         "ID Cards",
         "Design once, print for everyone — with QR codes, barcodes and CR80 print-ready sizing."),
        ("Appointment Scheduling for Schools, Clinics and Offices", "appointment",
         "appointment scheduling software nepal, booking system",
         "Appointment",
         "Let people book a slot instead of queueing. Here is what a good scheduling flow looks like."),
        ("Form Builder: Collecting Structured Data Without a Developer", "form-builder",
         "online form builder, custom forms, data collection software",
         "Form Builder",
         "Build admission forms, surveys and requests yourself, and get clean structured data back."),
        ("Reports and Analytics: The Numbers Worth Watching Weekly", "reports",
         "attendance reports, hr analytics, payroll reports nepal",
         "Reports",
         "Which handful of reports actually change decisions — and which ones are just noise."),
        ("Why Mero Attendance: One Platform for Attendance, HR and Payroll", "why-mero-attendance",
         "mero attendance, attendance software nepal, hrms payroll nepal",
         "Why Mero Attendance",
         "Attendance, payroll, leave, school management and CRM in one system built for Nepali organisations."),
    ]

    def seed_blogs(self, ctx):
        author = CustomUser.objects.filter(user_type="1").first() or CustomUser.objects.first()
        slugs = [f"ma-{s}" for _, s, _, _, _ in self.BLOG_TOPICS]
        # Internal links: each post links to the next two, so crawlers (and
        # readers) always have somewhere to go.
        n = 0
        for i, (title, slug, keywords, category, excerpt) in enumerate(self.BLOG_TOPICS):
            full_slug = f"ma-{slug}"
            nxt = [(self.BLOG_TOPICS[(i + k) % len(self.BLOG_TOPICS)][0],
                    slugs[(i + k) % len(self.BLOG_TOPICS)]) for k in (1, 2)]
            links = "".join(
                f'<li><a href="/blog/{s}/">{t}</a></li>' for t, s in nxt)
            content = f"""
<h2>Introduction</h2>
<p>{excerpt} This guide is written for organisations in Nepal that are moving
off paper registers and spreadsheets, and want to understand what changes when
the process becomes digital.</p>

<h2>Why it matters</h2>
<p>Manual processes fail quietly. A register gets filled in at the end of the
week from memory; a spreadsheet formula silently breaks; a leave balance is
argued over because nobody has the authoritative number. The cost is rarely a
single dramatic failure — it is a slow accumulation of small disputes and
wasted administrative hours.</p>

<h2>Key features to look for</h2>
<ul>
  <li><strong>Accurate capture at source</strong> — biometric, QR, GPS, WiFi or
      facial recognition, whichever fits how your people actually work.</li>
  <li><strong>Policy that lives in the system</strong> — grace periods, shift
      windows and leave allocations encoded once, applied consistently.</li>
  <li><strong>Reports people trust</strong> — same numbers on the dashboard, in
      the export and on the payslip.</li>
  <li><strong>Nepali calendar support</strong> — Bikram Sambat dates throughout,
      not bolted on at the end.</li>
</ul>

<h2>How {category.lower()} works in Mero Attendance</h2>
<p>Mero Attendance treats {category.lower()} as one part of a single connected
system rather than a standalone tool. Records captured here flow directly into
payroll, reports and dashboards, so the same figure appears everywhere and there
is no reconciliation step at month end.</p>

<h2>Getting started</h2>
<ol>
  <li>Set up your organisation, branches and departments.</li>
  <li>Import your people from a spreadsheet.</li>
  <li>Choose the capture methods that suit each group.</li>
  <li>Configure policy — shifts, grace periods, leave types.</li>
  <li>Run one month in parallel with your old process, then switch.</li>
</ol>

<h2>Frequently asked questions</h2>
<h3>Does this work without an internet connection?</h3>
<p>Attendance devices queue records locally and sync when connectivity returns,
so a brief outage does not lose data.</p>

<h3>Can we use the Nepali (Bikram Sambat) calendar?</h3>
<p>Yes. BS dates are supported across attendance, payroll, leave and reports,
and can be toggled per organisation.</p>

<h3>How long does setup take?</h3>
<p>A small office is typically running the same day. Schools and colleges with
classes, sections and subjects usually take two to three days including data
import.</p>

<h3>Is our data private?</h3>
<p>Each organisation's data is isolated. Staff only ever see what their assigned
permissions allow.</p>

<h2>Related reading</h2>
<ul>{links}</ul>
""".strip()

            BlogPost.objects.update_or_create(
                slug=full_slug,
                defaults={
                    "title": title,
                    "excerpt": excerpt,
                    "content": content,
                    "category": category,
                    "author": author,
                    "published": True,
                    "meta_description": excerpt[:160],
                    "meta_keywords": keywords,
                })
            n += 1
        ctx.bump("blog_posts", n)
