"""
Management command: seed_demo_data
Creates realistic demo data for org id 8 so the app feels already used.

Demo data is identified by:
  - CustomUser.email starting with "demo.staff"
  - Org-level records (transactions, events, stock, tasks, etc.) with title/name prefixed "[DEMO]"

Safety guarantees:
  - Real production data is NEVER deleted by default.
  - Only demo data is removed when --reset-demo is passed.
  - All creation is wrapped in transaction.atomic().
  - Missing optional models are skipped gracefully with a warning.
"""

import calendar
import random
from datetime import date, datetime, timedelta, time

from django.contrib.auth.hashers import make_password
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.timezone import make_aware, is_aware

ORG_ID = 8
DEMO_EMAIL_PREFIX = "demo.staff"
DEMO_STUDENT_EMAIL_PREFIX = "demo.student"
DEMO_MARKER = "[DEMO]"

NEPALI_NAMES = [
    ("Bikash", "Sharma", "Male"),
    ("Sagar", "Thapa", "Male"),
    ("Nabin", "Poudel", "Male"),
    ("Dipesh", "Karki", "Male"),
    ("Rajan", "Shrestha", "Male"),
    ("Suraj", "Adhikari", "Male"),
    ("Kamal", "Bhandari", "Male"),
    ("Roshan", "Maharjan", "Male"),
    ("Bijay", "Tamang", "Male"),
    ("Anil", "Basnet", "Male"),
    ("Sunita", "Gurung", "Female"),
    ("Anita", "Rai", "Female"),
    ("Sabita", "Khadka", "Female"),
    ("Nirmala", "Bhatt", "Female"),
    ("Sita", "Lamichhane", "Female"),
    ("Manju", "Pandey", "Female"),
    ("Puja", "Chand", "Female"),
    ("Renuka", "Oli", "Female"),
    ("Rekha", "Dangol", "Female"),
    ("Kabita", "Malla", "Female"),
]

DEPARTMENTS = [
    "Administration",
    "Finance",
    "Human Resources",
    "Information Technology",
    "Operations",
    "Teaching Staff",
    "Marketing",
    "Support Services",
]

SCHOOL_CLASSES = [
    "Class 8",
    "Class 9",
    "Class 10",
]

STUDENT_NAMES = [
    ("Aarav", "Khadka", "Male"),
    ("Aayush", "Shrestha", "Male"),
    ("Bibek", "Rai", "Male"),
    ("Dikshya", "Gurung", "Female"),
    ("Isha", "Thapa", "Female"),
    ("Kabir", "Basnet", "Male"),
    ("Nisha", "Adhikari", "Female"),
    ("Prabin", "Karki", "Male"),
    ("Riya", "Maharjan", "Female"),
    ("Saurav", "Tamang", "Male"),
    ("Sneha", "Poudel", "Female"),
    ("Utsav", "Pandey", "Male"),
]

SCHOOL_SUBJECTS = [
    ("English", "ENG", 900),
    ("Mathematics", "MATH", 1200),
    ("Science", "SCI", 1100),
    ("Social Studies", "SOC", 800),
    ("Computer", "CMP", 1000),
]

SALARY_RANGES = {
    "Administration": (35000, 55000),
    "Finance": (40000, 65000),
    "Human Resources": (35000, 50000),
    "Information Technology": (45000, 80000),
    "Operations": (30000, 45000),
    "Teaching Staff": (35000, 60000),
    "Marketing": (35000, 55000),
    "Support Services": (25000, 40000),
}

NEPALI_HOLIDAYS = [
    "New Year (Naya Barsha)",
    "Dashain",
    "Tihar",
    "Chhath",
    "Holi",
    "Shivaratri",
    "Buddha Jayanti",
    "Republic Day",
    "Constitution Day",
    "Indra Jatra",
]

INCOME_CATEGORIES = [
    "Tuition Fees",
    "Admission Fees",
    "Examination Fees",
    "Library Fees",
    "Sports Fees",
    "Donation",
    "Grant",
    "Other Income",
]

EXPENSE_CATEGORIES = [
    "Salaries",
    "Utilities",
    "Office Supplies",
    "Maintenance",
    "Transportation",
    "Food & Catering",
    "IT Equipment",
    "Printing",
    "Marketing",
    "Miscellaneous",
]

STOCK_CATEGORIES = [
    ("Stationery", ["Pen", "Notebook", "Whiteboard Marker", "Stapler", "Tape"]),
    ("IT Equipment", ["USB Drive", "Mouse", "Keyboard", "Headset", "Webcam"]),
    ("Cleaning", ["Soap", "Mop", "Dustbin", "Sanitizer", "Tissue"]),
    ("Sports", ["Football", "Volleyball", "Badminton Racket", "Carrom Board", "Chess Set"]),
    ("Furniture", ["Chair", "Desk", "Bookshelf", "Filing Cabinet", "Notice Board"]),
]

EVENT_TITLES = [
    f"{DEMO_MARKER} Annual Sports Day",
    f"{DEMO_MARKER} Staff Meeting - Q1 Review",
    f"{DEMO_MARKER} Training Workshop on MS Excel",
    f"{DEMO_MARKER} Team Building Outing",
    f"{DEMO_MARKER} Mid-Year Performance Review",
    f"{DEMO_MARKER} Independence Day Celebration",
    f"{DEMO_MARKER} Safety & Health Training",
    f"{DEMO_MARKER} New Staff Orientation",
    f"{DEMO_MARKER} Annual Picnic",
    f"{DEMO_MARKER} IT Skills Workshop",
    f"{DEMO_MARKER} Staff Appreciation Day",
    f"{DEMO_MARKER} Dashain Celebration",
]

EVENT_TYPES = ["sports", "seminar", "meeting", "program", "holiday", "other"]

COMPLAINT_TYPES = [
    "Workplace Harassment",
    "Equipment Issue",
    "Salary Discrepancy",
    "Leave Request Denial",
    "Scheduling Conflict",
]

TASK_TITLES = [
    f"{DEMO_MARKER} Submit Monthly Report",
    f"{DEMO_MARKER} Update Staff Records",
    f"{DEMO_MARKER} Conduct Attendance Audit",
    f"{DEMO_MARKER} Prepare Training Materials",
    f"{DEMO_MARKER} Review Leave Applications",
    f"{DEMO_MARKER} Update Inventory Records",
    f"{DEMO_MARKER} Send Payslips to Staff",
    f"{DEMO_MARKER} Organize Staff Files",
    f"{DEMO_MARKER} Schedule Performance Review",
    f"{DEMO_MARKER} Draft HR Policy Document",
]


def working_days_in_range(start_date, end_date):
    """Yield each Monday–Friday between start_date and end_date (inclusive)."""
    current = start_date
    while current <= end_date:
        if current.weekday() < 5:
            yield current
        current += timedelta(days=1)


def random_time_near(base_hour, base_minute, spread_minutes=20):
    """Return a time object near base_hour:base_minute ± spread_minutes."""
    delta = random.randint(-spread_minutes, spread_minutes)
    total_minutes = base_hour * 60 + base_minute + delta
    total_minutes = max(0, min(23 * 60 + 59, total_minutes))
    return time(total_minutes // 60, total_minutes % 60)


class Command(BaseCommand):
    help = "Seed realistic demo data for org id 8 (Mero Attendance demo)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset-demo",
            action="store_true",
            default=False,
            help="DELETE all previously seeded demo data before re-seeding.",
        )
        parser.add_argument("--staff", type=int, default=20, help="Number of demo staff to create (default 20)")
        parser.add_argument("--attendance", type=int, default=500, help="Minimum attendance records to target (default 500)")
        parser.add_argument("--months", type=int, default=6, help="Number of months of historical data (default 6)")

    def handle(self, *args, **options):
        reset = options["reset_demo"]
        num_staff = min(options["staff"], len(NEPALI_NAMES))
        months = options["months"]

        self.stdout.write(self.style.MIGRATE_HEADING("=== Mero Attendance Demo Seeder ==="))

        # Load models safely
        try:
            from management.models import (
                CustomUser, Organization, Schooladmin,
                LeaveType, LeaveReport, Occasion,
            )
            from handle.models import (
                member, Staff, Classification, Section, Subject, ExamTerm,
                ResultRecord, Bill, BillItem, BillSendLog, ResultSendLog,
                AttendanceRecord, PaySlip, PayrollAdjustment,
                StockCategory, StockItem, StockMovement,
                FinancialTransaction, TransactionCategory,
                Event, Task, TaskInstance, Complaint,
            )
        except ImportError as e:
            self.stderr.write(self.style.ERROR(f"Import error: {e}"))
            return

        # Get org
        try:
            org = Organization.objects.get(id=ORG_ID)
        except Organization.DoesNotExist:
            self.stderr.write(self.style.ERROR(f"Organization id={ORG_ID} does not exist. Aborting."))
            return

        self.stdout.write(f"Target org: {org.name} (id={org.id})")

        if reset:
            self._reset_demo_data(
                org, CustomUser, member, Staff, Classification,
                LeaveType, LeaveReport, Occasion,
                PaySlip, PayrollAdjustment,
                StockCategory, StockItem, StockMovement,
                FinancialTransaction, TransactionCategory,
                Event, Task, TaskInstance, Complaint,
                Bill, BillSendLog, ResultSendLog, ExamTerm,
            )

        with transaction.atomic():
            end_date = date.today()
            start_date = end_date - timedelta(days=months * 30)

            # ── 1. Classifications (departments) ────────────────────────────
            self.stdout.write("Creating departments...")
            classifications = []
            for dept_name in DEPARTMENTS:
                clf, _ = Classification.objects.get_or_create(
                    org=org,
                    name=f"{DEMO_MARKER} {dept_name}",
                    defaults={"status": "active"},
                )
                classifications.append(clf)
            self.stdout.write(self.style.SUCCESS(f"  {len(classifications)} departments ready"))

            school_classes = []
            for class_name in SCHOOL_CLASSES:
                clf, _ = Classification.objects.get_or_create(
                    org=org,
                    name=f"{DEMO_MARKER} {class_name}",
                    defaults={"status": "active"},
                )
                school_classes.append(clf)
            sections_by_class = {}
            for clf in school_classes:
                sections_by_class[clf.id] = []
                for sec_name in ("A", "B"):
                    sec, _ = Section.objects.get_or_create(
                        org=org,
                        classification=clf,
                        name=sec_name,
                        defaults={"code": sec_name, "status": "active"},
                    )
                    sections_by_class[clf.id].append(sec)
            self.stdout.write(self.style.SUCCESS(f"  {len(school_classes)} school classes and sections ready"))

            # Course / Subject setup with fees for course-wise billing and results.
            self.stdout.write("Creating Course / Subject setup...")
            subjects = []
            for clf in school_classes:
                for subj_name, code_prefix, monthly_fee in SCHOOL_SUBJECTS:
                    subj, _ = Subject.objects.get_or_create(
                        org=org,
                        classification=clf,
                        section=None,
                        name=f"{DEMO_MARKER} {subj_name}",
                        defaults={
                            "code": f"{code_prefix}-{clf.id}",
                            "full_marks": 100,
                            "pass_marks": 40,
                            "monthly_fee": monthly_fee,
                            "one_time_fee": 0,
                            "status": "active",
                        },
                    )
                    subjects.append(subj)
            self.stdout.write(self.style.SUCCESS(f"  {len(subjects)} Course / Subject records ready"))

            # ── 2. Staff members ─────────────────────────────────────────────
            self.stdout.write(f"Creating {num_staff} demo staff members...")
            members = []
            admin_user = CustomUser.objects.filter(schooladmin__org=org).first()

            for i in range(num_staff):
                first, last, gender = NEPALI_NAMES[i]
                email = f"{DEMO_EMAIL_PREFIX}{i+1:02d}@demo.meroattendance.com"
                dept = DEPARTMENTS[i % len(DEPARTMENTS)]
                clf = classifications[i % len(classifications)]
                sal_min, sal_max = SALARY_RANGES[dept]
                salary = random.randint(sal_min // 1000, sal_max // 1000) * 1000

                # CustomUser
                user, created = CustomUser.objects.get_or_create(
                    email=email,
                    defaults={
                        "username": email,
                        "first_name": first,
                        "last_name": last,
                        "password": make_password("Demo@1234"),
                        "user_type": "3",
                        "is_active": True,
                    },
                )
                if not created:
                    pass  # already exists, reuse

                # member record
                mem_obj, _ = member.objects.get_or_create(
                    org=org,
                    email=email,
                    defaults={
                        "name": f"{first} {last}",
                        "gender": gender,
                        "classification": clf,
                        "member_type": "employee",
                        "status": "active",
                        "salary_type": "monthly",
                        "salary_amount": salary,
                        "tax_percentage": 1.00,
                        "staff_type": "permanent",
                        "make_staff": True,
                        "address": f"Kathmandu, Nepal",
                        "phone": random.randint(9800000000, 9899999999),
                        "date_of_birth": date(random.randint(1980, 1998), random.randint(1, 12), random.randint(1, 28)),
                        "shift_start_time": time(9, 0),
                        "shift_end_time": time(17, 0),
                        "privilege": 1,
                    },
                )

                # Staff record (links CustomUser ↔ member)
                Staff.objects.get_or_create(
                    admin=user,
                    defaults={"org": org, "member": mem_obj},
                )

                members.append(mem_obj)

            self.stdout.write(self.style.SUCCESS(f"  {len(members)} staff members ready"))

            # ── 2b. Student members with billing setup ─────────────────────
            self.stdout.write("Creating demo students with billing setup...")
            students = []
            billing_cycle = ["monthly_fee", "course_wise", "custom", "scholarship"]
            for i, (first, last, gender) in enumerate(STUDENT_NAMES):
                email = f"{DEMO_STUDENT_EMAIL_PREFIX}{i+1:02d}@demo.meroattendance.com"
                clf = school_classes[i % len(school_classes)]
                section = sections_by_class[clf.id][i % len(sections_by_class[clf.id])]
                billing_type = billing_cycle[i % len(billing_cycle)]
                course_total = sum(int(s.monthly_fee or 0) for s in subjects if s.classification_id == clf.id and not s.section_id)
                monthly_fee = {
                    "monthly_fee": random.choice([3500, 4200, 5000]),
                    "course_wise": course_total,
                    "custom": random.choice([3000, 3750, 4500]),
                    "scholarship": 0,
                }[billing_type]
                discount_type = "percentage" if i % 5 == 0 else "fixed"
                discount_amount = 10 if discount_type == "percentage" else random.choice([0, 250, 500])
                scholarship_amount = 0 if billing_type != "scholarship" else monthly_fee
                payable = max(
                    0,
                    monthly_fee - (monthly_fee * discount_amount / 100 if discount_type == "percentage" else discount_amount) - scholarship_amount,
                )
                stu, _ = member.objects.get_or_create(
                    org=org,
                    email=email,
                    defaults={
                        "name": f"{first} {last}",
                        "gender": gender,
                        "classification": clf,
                        "section": section,
                        "member_type": "student",
                        "status": "active",
                        "card": f"STU-{i+1:03d}",
                        "address": random.choice(["Kathmandu", "Lalitpur", "Bhaktapur"]),
                        "phone": random.randint(9800000000, 9899999999),
                        "guardian_name": f"{last} Guardian",
                        "guardian_phone": random.randint(9800000000, 9899999999),
                        "guardian_email": f"guardian{i+1:02d}@demo.meroattendance.com",
                        "admission_date": start_date,
                        "billing_type": billing_type,
                        "monthly_fee": monthly_fee,
                        "discount_type": discount_type,
                        "discount_amount": discount_amount,
                        "scholarship_amount": scholarship_amount,
                        "final_monthly_fee": payable,
                        "billing_start_date": start_date,
                        "due_day": 15,
                        "shift_start_time": time(9, 0),
                        "shift_end_time": time(15, 30),
                        "privilege": 1,
                    },
                )
                students.append(stu)
            self.stdout.write(self.style.SUCCESS(f"  {len(students)} students ready"))

            # ── 3. Leave types ───────────────────────────────────────────────
            self.stdout.write("Creating leave types...")
            leave_types = []
            for lt_data in [
                ("Sick Leave", 12, True),
                ("Casual Leave", 6, True),
                ("Annual Leave", 18, True),
                ("Unpaid Leave", 0, False),
            ]:
                lt, _ = LeaveType.objects.get_or_create(
                    org=org,
                    name=lt_data[0],
                    defaults={"annual_allocation": lt_data[1], "is_paid": lt_data[2]},
                )
                leave_types.append(lt)
            self.stdout.write(self.style.SUCCESS(f"  {len(leave_types)} leave types ready"))

            # ── 4. Attendance records ────────────────────────────────────────
            self.stdout.write("Creating attendance records...")
            all_working_days = list(working_days_in_range(start_date, end_date))
            attendance_count = 0
            batch = []
            use_tz = is_aware(timezone.now())

            for mem_obj in members:
                for work_date in all_working_days:
                    if random.random() < 0.10:
                        continue  # ~10% absence rate
                    checkin_t = random_time_near(9, 0, 20)
                    checkout_t = random_time_near(17, 0, 30)
                    checkin_dt = datetime.combine(work_date, checkin_t)
                    checkout_dt = datetime.combine(work_date, checkout_t)
                    if use_tz:
                        checkin_dt = make_aware(checkin_dt)
                        checkout_dt = make_aware(checkout_dt)
                    batch.append(AttendanceRecord(mem=mem_obj, org=org, scanned_time=checkin_dt))
                    batch.append(AttendanceRecord(mem=mem_obj, org=org, scanned_time=checkout_dt))
                    attendance_count += 2
                    if len(batch) >= 500:
                        AttendanceRecord.objects.bulk_create(batch, ignore_conflicts=True)
                        batch = []

            if batch:
                AttendanceRecord.objects.bulk_create(batch, ignore_conflicts=True)
            self.stdout.write(self.style.SUCCESS(f"  {attendance_count} attendance records created"))

            # ── 5. Leave reports ─────────────────────────────────────────────
            self.stdout.write("Creating leave applications...")
            leave_count = 0
            for mem_obj in members:
                num_leaves = random.randint(1, 4)
                for _ in range(num_leaves):
                    gap_start = start_date + timedelta(days=random.randint(0, months * 28))
                    gap_end = gap_start + timedelta(days=random.randint(0, 2))
                    lt = random.choice(leave_types)
                    approved = random.random() < 0.75
                    LeaveReport.objects.get_or_create(
                        member=mem_obj,
                        org=org,
                        gap_start=gap_start,
                        defaults={
                            "leave_type": lt,
                            "gap_end": gap_end,
                            "approved": approved,
                            "rejected": not approved and random.random() < 0.3,
                            "reason": random.choice([
                                "Not feeling well",
                                "Family function",
                                "Personal work",
                                "Medical appointment",
                                "Out of town",
                            ]),
                            "seen": True,
                        },
                    )
                    leave_count += 1
            self.stdout.write(self.style.SUCCESS(f"  {leave_count} leave records created"))

            # ── 6. Payslips (6 months) ───────────────────────────────────────
            self.stdout.write("Creating payslips...")
            payslip_count = 0
            month_names = []
            d = start_date.replace(day=1)
            while d <= end_date:
                month_names.append((d.year, d.month, d.strftime("%B %Y")))
                if d.month == 12:
                    d = d.replace(year=d.year + 1, month=1)
                else:
                    d = d.replace(month=d.month + 1)

            for mem_obj in members:
                for yr, mo, mname in month_names:
                    from_date = date(yr, mo, 1)
                    last_day = calendar.monthrange(yr, mo)[1]
                    to_date = date(yr, mo, last_day)
                    gross = float(mem_obj.salary_amount)
                    tax = round(gross * float(mem_obj.tax_percentage) / 100, 2)
                    pf_emp = round(gross * 0.10, 2)
                    pf_er = round(gross * 0.10, 2)
                    ssf_emp = round(gross * 0.11, 2)
                    ssf_er = round(gross * 0.20, 2)
                    allowance = round(gross * 0.05, 2)
                    net = round(gross + allowance - tax - pf_emp - ssf_emp, 2)
                    work_days = len(list(working_days_in_range(from_date, to_date)))
                    present = random.randint(int(work_days * 0.85), work_days)
                    PaySlip.objects.get_or_create(
                        member=mem_obj,
                        org=org,
                        month_name=mname,
                        defaults={
                            "from_date": from_date,
                            "to_date": to_date,
                            "total_days": last_day,
                            "present_days": present,
                            "paid_leaves": random.randint(0, 2),
                            "holidays": 4,
                            "unpaid_absences": work_days - present,
                            "salary_type": "monthly",
                            "gross_salary": gross,
                            "allowance_total": allowance,
                            "bonus_total": 0,
                            "tax_deduction": tax,
                            "pf_employee": pf_emp,
                            "pf_employer": pf_er,
                            "ssf_employee": ssf_emp,
                            "ssf_employer": ssf_er,
                            "net_payable": net,
                            "status": "paid" if to_date < date.today() else "draft",
                        },
                    )
                    payslip_count += 1
            self.stdout.write(self.style.SUCCESS(f"  {payslip_count} payslips created"))

            # ── 6b. Student bills, send logs, exams and results ─────────────
            self.stdout.write("Creating student bills and result data...")
            bill_count = bill_log_count = result_count = result_log_count = 0
            for stu in students:
                class_subjects = [s for s in subjects if s.classification_id == stu.classification_id and not s.section_id]
                for yr, mo, mname in month_names[-min(months, 6):]:
                    base_amount = 0
                    course_fee = 0
                    if stu.billing_type == "course_wise":
                        course_fee = sum(int(s.monthly_fee or 0) for s in class_subjects)
                        subtotal = course_fee
                    elif stu.billing_type == "scholarship":
                        subtotal = 0
                    else:
                        base_amount = int(stu.monthly_fee or 0)
                        subtotal = base_amount
                    discount = int(stu.discount_amount or 0)
                    if stu.discount_type == "percentage":
                        discount = int(subtotal * float(stu.discount_amount or 0) / 100)
                    scholarship = int(stu.scholarship_amount or 0)
                    total = max(0, subtotal - discount - scholarship)
                    if total == 0:
                        paid = 0
                        status = "Paid"
                    else:
                        paid = random.choice([0, int(total * 0.5), total])
                        status = "Paid" if paid >= total else ("Partial" if paid > 0 else "Unpaid")
                    due_date = date(yr, mo, min(int(stu.due_day or 15), calendar.monthrange(yr, mo)[1]))
                    invoice = f"DEMO-BILL-{yr}{mo:02d}-{stu.id}"
                    bill, created = Bill.objects.get_or_create(
                        org=org,
                        member=stu,
                        billing_month=mo,
                        billing_year=yr,
                        defaults={
                            "classification": stu.classification,
                            "section": stu.section,
                            "invoice_number": invoice,
                            "due_date": due_date,
                            "billing_type": stu.billing_type,
                            "base_amount": base_amount,
                            "course_fee_amount": course_fee,
                            "discount_amount": discount,
                            "scholarship_amount": scholarship,
                            "previous_due": 0,
                            "total_amount": total,
                            "amount_paid": paid,
                            "status": status,
                            "generated_by": admin_user,
                            "is_sent": random.random() < 0.75,
                            "sent_method": "email",
                        },
                    )
                    if created:
                        bill_count += 1
                        if stu.billing_type == "course_wise":
                            for subj in class_subjects:
                                BillItem.objects.create(
                                    bill=bill,
                                    subject=subj,
                                    description=f"{subj.name} Course Fee - {mname}",
                                    fee_type="course",
                                    amount=subj.monthly_fee or 0,
                                )
                        elif base_amount:
                            BillItem.objects.create(
                                bill=bill,
                                description=f"{mname} Monthly Fee",
                                fee_type="monthly",
                                amount=base_amount,
                            )
                        if discount:
                            BillItem.objects.create(bill=bill, description="Demo Discount", fee_type="misc", amount=0, discount=discount)
                    if bill.is_sent and not BillSendLog.objects.filter(bill=bill).exists():
                        BillSendLog.objects.create(
                            bill=bill,
                            sent_to_email=stu.guardian_email or stu.email,
                            sent_to_phone=str(stu.guardian_phone or stu.phone or ""),
                            sent_method="email",
                            message_body=f"Dear {stu.guardian_name or stu.name}, bill {bill.invoice_number} is ready.",
                            status="sent",
                            sent_by=admin_user,
                        )
                        bill_log_count += 1

            exam, _ = ExamTerm.objects.get_or_create(
                org=org,
                name=f"{DEMO_MARKER} First Terminal Examination",
                defaults={
                    "academic_year": f"{date.today().year}",
                    "classification": None,
                    "start_date": date.today() - timedelta(days=30),
                    "end_date": date.today() - timedelta(days=25),
                    "status": "published",
                    "is_published": True,
                },
            )
            for stu in students:
                class_subjects = [s for s in subjects if s.classification_id == stu.classification_id and not s.section_id]
                for subj in class_subjects:
                    obtained = random.randint(35, 95)
                    ResultRecord.objects.update_or_create(
                        student=stu,
                        exam=exam,
                        subject=subj,
                        defaults={
                            "obtained_marks": obtained,
                            "is_absent": False,
                            "remarks": "Demo marks",
                            "created_by": admin_user,
                            "updated_by": admin_user,
                        },
                    )
                    result_count += 1
                if not ResultSendLog.objects.filter(exam=exam, member=stu).exists():
                    ResultSendLog.objects.create(
                        exam=exam,
                        member=stu,
                        sent_to_email=stu.guardian_email or stu.email,
                        sent_to_phone=str(stu.guardian_phone or stu.phone or ""),
                        sent_method="email",
                        message_body=f"Dear {stu.guardian_name or stu.name}, result of {stu.name} for {exam.name} has been published.",
                        status="sent",
                        sent_by=admin_user,
                    )
                    result_log_count += 1
            self.stdout.write(self.style.SUCCESS(f"  {bill_count} bills, {bill_log_count} bill logs, {result_count} marks and {result_log_count} result logs ready"))

            # ── 7. Payroll adjustments ───────────────────────────────────────
            self.stdout.write("Creating payroll adjustments...")
            adj_count = 0
            for mem_obj in members:
                # Festival bonus
                PayrollAdjustment.objects.get_or_create(
                    org=org,
                    member=mem_obj,
                    adjustment_type="bonus",
                    title=f"{DEMO_MARKER} Dashain Bonus",
                    defaults={
                        "amount": round(float(mem_obj.salary_amount) * 0.5, 2),
                        "effective_date": date.today() - timedelta(days=random.randint(60, 150)),
                        "status": "applied",
                    },
                )
                # Monthly transport allowance
                PayrollAdjustment.objects.get_or_create(
                    org=org,
                    member=mem_obj,
                    adjustment_type="allowance",
                    title=f"{DEMO_MARKER} Transport Allowance",
                    defaults={
                        "amount": random.choice([1000, 1500, 2000]),
                        "effective_date": start_date,
                        "status": "applied",
                    },
                )
                adj_count += 2
            self.stdout.write(self.style.SUCCESS(f"  {adj_count} payroll adjustments created"))

            # ── 8. Transaction categories & financial transactions ───────────
            self.stdout.write("Creating financial transactions...")
            income_cats = []
            for cat_name in INCOME_CATEGORIES:
                cat, _ = TransactionCategory.objects.get_or_create(
                    org=org,
                    name=f"{DEMO_MARKER} {cat_name}",
                    transaction_type="income",
                )
                income_cats.append(cat)

            expense_cats = []
            for cat_name in EXPENSE_CATEGORIES:
                cat, _ = TransactionCategory.objects.get_or_create(
                    org=org,
                    name=f"{DEMO_MARKER} {cat_name}",
                    transaction_type="expense",
                )
                expense_cats.append(cat)

            tx_count = 0
            for i in range(40):
                tx_type = random.choice(["income", "expense"])
                cat = random.choice(income_cats if tx_type == "income" else expense_cats)
                tx_date = start_date + timedelta(days=random.randint(0, months * 30))
                amount = random.randint(5000, 200000) if tx_type == "income" else random.randint(1000, 80000)
                FinancialTransaction.objects.create(
                    org=org,
                    category=cat,
                    transaction_type=tx_type,
                    title=f"{DEMO_MARKER} {cat.name.replace(DEMO_MARKER, '').strip()} - {tx_date.strftime('%b %Y')}",
                    amount=amount,
                    transaction_date=tx_date,
                    payment_method=random.choice(["cash", "bank", "online"]),
                    note="Auto-generated demo transaction",
                )
                tx_count += 1
            self.stdout.write(self.style.SUCCESS(f"  {tx_count} financial transactions created"))

            # ── 9. Stock ─────────────────────────────────────────────────────
            self.stdout.write("Creating stock categories and items...")
            stock_items_created = 0
            for cat_name, item_names in STOCK_CATEGORIES:
                s_cat, _ = StockCategory.objects.get_or_create(
                    org=org,
                    name=f"{DEMO_MARKER} {cat_name}",
                )
                for item_name in item_names:
                    item, created = StockItem.objects.get_or_create(
                        org=org,
                        name=f"{DEMO_MARKER} {item_name}",
                        defaults={
                            "category": s_cat,
                            "unit": "pcs",
                            "quantity": random.randint(20, 200),
                            "low_stock_threshold": 5,
                            "purchase_cost": random.randint(100, 5000),
                            "purchase_date": start_date + timedelta(days=random.randint(0, 30)),
                            "status": "active",
                        },
                    )
                    if created:
                        # Add initial stock movement
                        try:
                            StockMovement.objects.create(
                                org=org,
                                item=item,
                                movement_type="in",
                                quantity=item.quantity,
                                unit_cost=item.purchase_cost,
                                movement_date=start_date,
                                note=f"{DEMO_MARKER} Initial stock",
                            )
                        except Exception:
                            pass  # StockMovement.save() modifies quantity; skip if errors
                        stock_items_created += 1
            self.stdout.write(self.style.SUCCESS(f"  {stock_items_created} stock items created"))

            # ── 10. Events ───────────────────────────────────────────────────
            self.stdout.write("Creating events...")
            event_count = 0
            for title in EVENT_TITLES:
                ev_start = start_date + timedelta(days=random.randint(0, months * 28))
                ev_end = ev_start + timedelta(days=random.randint(0, 2))
                Event.objects.get_or_create(
                    org=org,
                    title=title,
                    start_date=ev_start,
                    defaults={
                        "end_date": ev_end,
                        "event_type": random.choice(EVENT_TYPES),
                        "location": random.choice(["Main Hall", "Conference Room A", "Outdoor Ground", "Seminar Hall", "Office"]),
                        "description": f"Demo event: {title.replace(DEMO_MARKER, '').strip()}",
                        "status": "completed" if ev_end < date.today() else "upcoming",
                    },
                )
                event_count += 1
            self.stdout.write(self.style.SUCCESS(f"  {event_count} events created"))

            # ── 11. Occasions (holidays) ─────────────────────────────────────
            self.stdout.write("Creating occasions/holidays...")
            occ_count = 0
            for i, holiday_name in enumerate(NEPALI_HOLIDAYS):
                h_date = start_date + timedelta(days=i * 18 + random.randint(0, 10))
                try:
                    Occasion.objects.get_or_create(
                        org=org,
                        name=f"{DEMO_MARKER} {holiday_name}",
                        date=h_date,
                    )
                    occ_count += 1
                except Exception as e:
                    self.stdout.write(self.style.WARNING(f"  Skipping occasion: {e}"))
            self.stdout.write(self.style.SUCCESS(f"  {occ_count} occasions created"))

            # ── 12. Tasks ────────────────────────────────────────────────────
            self.stdout.write("Creating tasks...")
            task_count = 0
            for task_title in TASK_TITLES:
                t_start = start_date + timedelta(days=random.randint(0, months * 20))
                t_due = t_start + timedelta(days=random.randint(3, 14))
                assigned_members = random.sample(members, min(3, len(members)))
                try:
                    task_obj = Task.objects.filter(org=org, title=task_title).first()
                    if not task_obj:
                        task_obj = Task.objects.create(
                            org=org,
                            title=task_title,
                            description=f"Demo task for testing purposes.",
                            priority=random.choice(["low", "medium", "high"]),
                            task_type="one_time",
                            start_date=t_start,
                            due_date=t_due,
                        )
                        task_obj.assigned_to.set(assigned_members)
                        task_obj.save()
                        # Create task instances
                        for mem_obj in assigned_members:
                            TaskInstance.objects.get_or_create(
                                task=task_obj,
                                assigned_member=mem_obj,
                                due_date=t_due,
                                defaults={
                                    "status": random.choice(["completed", "pending", "in_progress"]),
                                },
                            )
                        task_count += 1
                except Exception as e:
                    self.stdout.write(self.style.WARNING(f"  Skipping task '{task_title}': {e}"))
            self.stdout.write(self.style.SUCCESS(f"  {task_count} tasks created"))

            # ── 13. Complaints ───────────────────────────────────────────────
            self.stdout.write("Creating complaints...")
            complaint_count = 0
            for mem_obj in random.sample(members, min(5, len(members))):
                try:
                    Complaint.objects.get_or_create(
                        org=org,
                        filed_by=mem_obj,
                        subject=f"{DEMO_MARKER} {random.choice(COMPLAINT_TYPES)}",
                        defaults={
                            "complaint_type": random.choice(COMPLAINT_TYPES),
                            "description": "This is a demo complaint filed for testing purposes.",
                            "priority": random.choice(["low", "medium", "high"]),
                            "status": random.choice(["pending", "reviewing", "resolved"]),
                            "admin_remarks": "Demo complaint — reviewed and resolved." if random.random() > 0.5 else "",
                        },
                    )
                    complaint_count += 1
                except Exception as e:
                    self.stdout.write(self.style.WARNING(f"  Skipping complaint: {e}"))
            self.stdout.write(self.style.SUCCESS(f"  {complaint_count} complaints created"))

        # Summary
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("✓ Demo seeding complete!"))
        self.stdout.write(f"  Org: {org.name} (id={org.id})")
        self.stdout.write(f"  Staff: {len(members)}")
        self.stdout.write(f"  Attendance records: ~{attendance_count}")
        self.stdout.write(f"  Payslips: {payslip_count}")
        self.stdout.write(f"  Events: {event_count}")
        self.stdout.write("")
        self.stdout.write("  All demo data uses email prefixes 'demo.staff' / 'demo.student' and title prefix '[DEMO]'.")
        self.stdout.write("  To remove all demo data: python manage.py seed_demo_data --reset-demo")

    def _reset_demo_data(
        self, org, CustomUser, member, Staff, Classification,
        LeaveType, LeaveReport, Occasion,
        PaySlip, PayrollAdjustment,
        StockCategory, StockItem, StockMovement,
        FinancialTransaction, TransactionCategory,
        Event, Task, TaskInstance, Complaint,
        Bill, BillSendLog, ResultSendLog, ExamTerm,
    ):
        self.stdout.write(self.style.WARNING("-- Resetting demo data --"))

        # Find demo members by email prefix
        demo_users = CustomUser.objects.filter(email__startswith=DEMO_EMAIL_PREFIX)
        demo_members = member.objects.filter(org=org).filter(
            Q(email__startswith=DEMO_EMAIL_PREFIX) | Q(email__startswith=DEMO_STUDENT_EMAIL_PREFIX)
        )
        demo_member_ids = list(demo_members.values_list("id", flat=True))

        # Delete member-linked records first (cascades handle AttendanceRecord, etc.)
        with transaction.atomic():
            # Task instances for demo members
            try:
                TaskInstance.objects.filter(assigned_member_id__in=demo_member_ids).delete()
            except Exception as e:
                self.stdout.write(self.style.WARNING(f"  TaskInstance delete: {e}"))

            # Tasks with DEMO marker
            try:
                Task.objects.filter(org=org, title__startswith=DEMO_MARKER).delete()
            except Exception as e:
                self.stdout.write(self.style.WARNING(f"  Task delete: {e}"))

            try:
                Complaint.objects.filter(org=org, filed_by_id__in=demo_member_ids).delete()
            except Exception as e:
                self.stdout.write(self.style.WARNING(f"  Complaint delete: {e}"))

            try:
                LeaveReport.objects.filter(org=org, member_id__in=demo_member_ids).delete()
            except Exception as e:
                self.stdout.write(self.style.WARNING(f"  LeaveReport delete: {e}"))

            try:
                PaySlip.objects.filter(org=org, member_id__in=demo_member_ids).delete()
            except Exception as e:
                self.stdout.write(self.style.WARNING(f"  PaySlip delete: {e}"))

            try:
                PayrollAdjustment.objects.filter(org=org, member_id__in=demo_member_ids).delete()
            except Exception as e:
                self.stdout.write(self.style.WARNING(f"  PayrollAdjustment delete: {e}"))

            # Org-level records with DEMO marker
            try:
                FinancialTransaction.objects.filter(org=org, title__startswith=DEMO_MARKER).delete()
            except Exception as e:
                self.stdout.write(self.style.WARNING(f"  FinancialTransaction delete: {e}"))

            try:
                TransactionCategory.objects.filter(org=org, name__startswith=DEMO_MARKER).delete()
            except Exception as e:
                self.stdout.write(self.style.WARNING(f"  TransactionCategory delete: {e}"))

            try:
                StockItem.objects.filter(org=org, name__startswith=DEMO_MARKER).delete()
            except Exception as e:
                self.stdout.write(self.style.WARNING(f"  StockItem delete: {e}"))

            try:
                StockCategory.objects.filter(org=org, name__startswith=DEMO_MARKER).delete()
            except Exception as e:
                self.stdout.write(self.style.WARNING(f"  StockCategory delete: {e}"))

            try:
                Event.objects.filter(org=org, title__startswith=DEMO_MARKER).delete()
            except Exception as e:
                self.stdout.write(self.style.WARNING(f"  Event delete: {e}"))

            try:
                ExamTerm.objects.filter(org=org, name__startswith=DEMO_MARKER).delete()
            except Exception as e:
                self.stdout.write(self.style.WARNING(f"  ExamTerm delete: {e}"))

            try:
                Occasion.objects.filter(org=org, name__startswith=DEMO_MARKER).delete()
            except Exception as e:
                self.stdout.write(self.style.WARNING(f"  Occasion delete: {e}"))

            try:
                Classification.objects.filter(org=org, name__startswith=DEMO_MARKER).delete()
            except Exception as e:
                self.stdout.write(self.style.WARNING(f"  Classification delete: {e}"))

            # Delete members (cascades AttendanceRecord)
            demo_members.delete()

            # Delete users (cascades Staff)
            demo_users.delete()

        self.stdout.write(self.style.SUCCESS("  Demo data removed."))
