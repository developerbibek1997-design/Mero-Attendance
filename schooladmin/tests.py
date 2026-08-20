import datetime
import json
from decimal import Decimal
import nepali_datetime

from django.contrib.messages import get_messages
from django.test import TestCase, Client
from django.db.models import Sum
from django.urls import reverse
from django.utils import timezone
from rest_framework_simplejwt.tokens import RefreshToken

from management.models import CustomUser, Organization, Schooladmin, LeaveReport, LeaveType, AutoCheckin
from handle.models import (
    member, PaySlip, PayrollPolicy, Bill, BillItem, IDCardTemplate, CertificateTemplate,
    Client as CRMClient, CustomerBill, CustomerBillPayment,
    FinancialTransaction, Supplier, Purchase, PurchaseItem, StockItem,
    Staff, Classification, Section, Course, Subject, SubjectTeacherAssignment,
    AcademicYear, StudentCourseEnrollment, RoutinePeriod,
    TeachingLog, SubjectAttendanceRecord, DynamicFeature,
    OrganizationFeatureGrant, Assignment, AssignmentSubmission,
    Homework, HomeworkStatus, ExamTerm, ResultRecord,
    Shift, ShiftWindow, AttendanceRecord, AttendanceReminderPolicy,
    MemberWeekdayShift, MemberShiftOverride, MemberHistory, LocationPing,
    QRAttendanceSession, FieldVisit, FieldVisitReport, ClientFollowUp,
    Branch, DailyNote, TemporaryShiftAssignment, DutyType,
)


def _make_org_and_admin(name_suffix):
    org = Organization.objects.create(
        name=f"Org {name_suffix}",
        category="school",
        expire_on=timezone.make_aware(datetime.datetime(2030, 1, 1)),
        feature_payroll=True,
    )
    user = CustomUser.objects.create_user(
        username=f"admin{name_suffix}",
        email=f"admin{name_suffix}@example.com",
        password="testpass123",
        user_type="2",
    )
    Schooladmin.objects.create(admin=user, org=org)
    return org, user


class SchooladminSignupSignalTests(TestCase):
    """Regression test: creating a user_type='2' CustomUser directly (as the
    agent portal and mobile API signup both do) must not crash. The
    post_save signal used to try Schooladmin.objects.create(admin=instance)
    with no org, which violates the NOT NULL constraint on Schooladmin.org.
    """

    def test_creating_schooladmin_user_type_user_does_not_raise(self):
        org = Organization.objects.create(
            name="Org Signal Test",
            category="school",
            expire_on=timezone.make_aware(datetime.datetime(2030, 1, 1)),
        )
        user = CustomUser.objects.create_user(
            username="signaltest",
            email="signaltest@example.com",
            password="testpass123",
            user_type="2",
        )
        # The real call sites create Schooladmin explicitly right after.
        Schooladmin.objects.create(admin=user, org=org)
        self.assertEqual(Schooladmin.objects.filter(admin=user).count(), 1)


class MemberHistoryAndWeekdayShiftTests(TestCase):
    def setUp(self):
        self.org, self.admin_user = _make_org_and_admin('HistoryShift')
        self.org.feature_hrms = True
        self.org.feature_field_visits = True
        self.org.allowed_features = list(set((self.org.allowed_features or []) + ['hrms', 'field_visits']))
        self.org.save(update_fields=['feature_hrms', 'feature_field_visits', 'allowed_features'])
        self.member = member.objects.create(
            org=self.org, name='Weekly Worker', member_type='staff',
            gender='Male', salary_amount=Decimal('20000.00'),
        )
        self.day_shift = Shift.objects.create(org=self.org, name='Day')
        ShiftWindow.objects.create(
            shift=self.day_shift, start_time=datetime.time(9),
            end_time=datetime.time(17),
        )
        self.night_shift = Shift.objects.create(org=self.org, name='Night')
        ShiftWindow.objects.create(
            shift=self.night_shift, start_time=datetime.time(19),
            end_time=datetime.time(23),
        )
        MemberWeekdayShift.objects.create(
            org=self.org, member=self.member, weekday=0, shift=self.day_shift,
        )

    def test_weekday_schedule_resolves_sunday_and_keeps_monday_off(self):
        from schooladmin.payroll_service import compute_shift_breakdown
        sunday = datetime.date(2026, 8, 2)
        monday = datetime.date(2026, 8, 3)
        self.assertIsNotNone(compute_shift_breakdown(self.member, sunday))
        self.assertIsNone(compute_shift_breakdown(self.member, monday))

    def test_member_field_changes_are_written_to_append_only_history(self):
        self.member.salary_amount = Decimal('25000.00')
        self.member.status = 'resigned'
        self.member.save()
        rows = MemberHistory.objects.filter(member=self.member)
        self.assertTrue(rows.filter(field_name='salary_amount', old_value='20000.00', new_value='25000.00').exists())
        self.assertTrue(rows.filter(field_name='status', old_value='active', new_value='resigned').exists())

    def test_tracking_attendance_requires_pings_and_is_idempotent(self):
        self.client.login(username='adminHistoryShift', password='testpass123')
        today = timezone.localdate()
        url = reverse('schooladmin:live_tracking_mark_attendance', args=[self.member.pk])
        no_evidence = self.client.post(url, {'date': today.isoformat()})
        self.assertEqual(no_evidence.status_code, 302)
        self.assertFalse(AttendanceRecord.objects.filter(mem=self.member).exists())
        LocationPing.objects.create(
            org=self.org, member=self.member, latitude=27.7172, longitude=85.3240,
        )
        self.client.post(url, {'date': today.isoformat()})
        self.client.post(url, {'date': today.isoformat()})
        self.assertEqual(AttendanceRecord.objects.filter(mem=self.member, attendance_method='field_visit').count(), 1)

    def test_member_profile_and_history_pages_render(self):
        self.client.login(username='adminHistoryShift', password='testpass123')
        self.assertEqual(self.client.get(reverse('schooladmin:member_profile', args=[self.member.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse('schooladmin:member_history', args=[self.member.pk])).status_code, 200)

    def test_shift_assignment_post_saves_each_weekday(self):
        self.client.login(username='adminHistoryShift', password='testpass123')
        response = self.client.post(reverse('schooladmin:shift_assign'), {
            'member_id': self.member.pk,
            'shift_0': self.day_shift.pk,
            'shift_1': self.day_shift.pk,
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.member.weekday_shifts.count(), 2)

    def test_shift_assignment_post_allows_multiple_shifts_same_weekday(self):
        self.client.login(username='adminHistoryShift', password='testpass123')
        response = self.client.post(reverse('schooladmin:shift_assign'), {
            'member_id': self.member.pk,
            'shift_0': [self.day_shift.pk, self.night_shift.pk],
        })
        self.assertEqual(response.status_code, 302)
        sunday_rows = self.member.weekday_shifts.filter(weekday=0)
        self.assertEqual(sunday_rows.count(), 2)
        self.assertEqual(
            set(sunday_rows.values_list('shift_id', flat=True)),
            {self.day_shift.pk, self.night_shift.pk},
        )
        sunday = datetime.date(2026, 8, 2)
        self.assertEqual(len(self.member.active_shifts(sunday)), 2)

    def test_shift_override_adds_extra_shift_on_top_of_weekly_pattern(self):
        from schooladmin.payroll_service import compute_shift_breakdown
        sunday = datetime.date(2026, 8, 2)
        MemberShiftOverride.objects.create(
            org=self.org, member=self.member, date=sunday, shift=self.night_shift,
        )
        active = self.member.active_shifts(sunday)
        self.assertEqual({s.pk for s in active}, {self.day_shift.pk, self.night_shift.pk})
        breakdown = compute_shift_breakdown(self.member, sunday)
        shift_names = {w['shift_name'] for w in breakdown['windows']}
        self.assertEqual(shift_names, {'Day', 'Night'})

    def test_shift_week_panel_and_override_views(self):
        self.client.login(username='adminHistoryShift', password='testpass123')
        panel_url = reverse('schooladmin:shift_week', args=[self.member.pk])
        resp = self.client.get(panel_url)
        self.assertEqual(resp.status_code, 200)

        today = timezone.localdate()
        add_url = reverse('schooladmin:shift_override_add', args=[self.member.pk])
        resp = self.client.post(add_url, {
            'date': today.isoformat(), 'shift_id': self.night_shift.pk,
        })
        self.assertEqual(resp.status_code, 200)
        override = MemberShiftOverride.objects.get(member=self.member, date=today, shift=self.night_shift)
        self.assertTrue(
            MemberHistory.objects.filter(member=self.member, action='shift_override_added').exists()
        )

        delete_url = reverse('schooladmin:shift_override_delete', args=[override.pk])
        resp = self.client.post(delete_url)
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(MemberShiftOverride.objects.filter(pk=override.pk).exists())
        self.assertTrue(
            MemberHistory.objects.filter(member=self.member, action='shift_override_removed').exists()
        )

    def test_shift_week_and_override_views_are_org_isolated(self):
        other_org, other_admin = _make_org_and_admin('HistoryShiftOther')
        other_member = member.objects.create(
            org=other_org, name='Other Org Worker', member_type='staff', gender='Male',
        )
        self.client.login(username='adminHistoryShift', password='testpass123')
        resp = self.client.get(reverse('schooladmin:shift_week', args=[other_member.pk]))
        self.assertEqual(resp.status_code, 404)


class FieldVisitManualAddTests(TestCase):
    """An admin logging a field visit from scratch (no prior mobile submission)
    with explicit check-in/check-out time — created already-approved."""

    def setUp(self):
        self.org, self.admin_user = _make_org_and_admin('FieldVisitManual')
        self.org.feature_field_visits = True
        self.org.allowed_features = list(set((self.org.allowed_features or []) + ['field_visits']))
        self.org.save(update_fields=['feature_field_visits', 'allowed_features'])
        self.member = member.objects.create(
            org=self.org, name='Field Worker', member_type='staff',
            gender='Male', salary_amount=Decimal('20000.00'),
        )
        self.client_obj = CRMClient.objects.create(
            org=self.org, client_number='CUST-1', client_org_name='Acme Corp',
            created_by=self.admin_user,
        )
        self.client.login(username='adminFieldVisitManual', password='testpass123')

    def test_manual_add_creates_approved_visit_with_attendance(self):
        response = self.client.post(reverse('schooladmin:field_visit_manual_add'), {
            'member_id': self.member.pk,
            'visit_date': '2026-08-02',
            'checkin_time': '09:00',
            'checkout_time': '13:00',
            'client_id': self.client_obj.pk,
            'purpose': 'Site inspection',
            'destination': 'Acme HQ',
            'note': 'All good',
        })
        visit = FieldVisit.objects.get(member=self.member)
        self.assertRedirects(response, reverse('schooladmin:field_visit_detail', args=[visit.pk]))
        self.assertEqual(visit.status, 'approved')
        self.assertEqual(visit.visit_state, 'completed')
        self.assertIsNone(visit.latitude)
        self.assertIsNone(visit.longitude)
        self.assertEqual(visit.client_id, self.client_obj.pk)
        self.assertEqual(visit.created_by, self.admin_user)
        self.assertEqual(visit.reviewed_by, self.admin_user)
        records = AttendanceRecord.objects.filter(field_visit=visit).order_by('scanned_time')
        self.assertEqual(records.count(), 2)
        self.assertTrue(all(r.attendance_method == 'field_visit' for r in records))
        self.assertTrue(FieldVisitReport.objects.filter(visit=visit, note='All good').exists())

    def test_manual_add_checkin_only_creates_single_record(self):
        self.client.post(reverse('schooladmin:field_visit_manual_add'), {
            'member_id': self.member.pk,
            'checkin_time': '09:00',
        })
        visit = FieldVisit.objects.get(member=self.member)
        self.assertEqual(AttendanceRecord.objects.filter(field_visit=visit).count(), 1)

    def test_manual_add_requires_checkin_time(self):
        response = self.client.post(reverse('schooladmin:field_visit_manual_add'), {
            'member_id': self.member.pk,
        })
        self.assertEqual(response.status_code, 302)
        self.assertFalse(FieldVisit.objects.filter(member=self.member).exists())

    def test_manual_add_is_org_isolated(self):
        other_org, other_admin = _make_org_and_admin('FieldVisitManualOther')
        other_member = member.objects.create(
            org=other_org, name='Other Org Worker', member_type='staff', gender='Male',
        )
        response = self.client.post(reverse('schooladmin:field_visit_manual_add'), {
            'member_id': other_member.pk,
            'checkin_time': '09:00',
        })
        self.assertEqual(response.status_code, 404)


class MemberProfileNepaliDateTests(TestCase):
    """Regression test for the confirmed bug where the leave table's 'Nepali'
    column silently rendered the same raw AD date as the English column."""

    def setUp(self):
        self.org, self.admin_user = _make_org_and_admin('NepaliProfile')
        self.org.nepali_date = True
        self.org.save(update_fields=['nepali_date'])
        self.member = member.objects.create(
            org=self.org, name='Nepali Date Member', member_type='staff', gender='Male',
        )
        self.leave = LeaveReport.objects.create(
            member=self.member, org=self.org, reason='Test leave',
            gap_start=datetime.date(2026, 8, 2), gap_end=datetime.date(2026, 8, 4),
            approved=True,
        )
        self.client.login(username='adminNepaliProfile', password='testpass123')

    def test_leave_table_shows_real_bs_dates_not_ad(self):
        import nepali_datetime
        expected_start_bs = str(nepali_datetime.date.from_datetime_date(self.leave.gap_start))
        expected_end_bs = str(nepali_datetime.date.from_datetime_date(self.leave.gap_end))
        # Sanity check the fixture: the BS string must actually differ from
        # the AD one, or this test can't tell a fixed page from a broken one.
        self.assertNotEqual(expected_start_bs, self.leave.gap_start.isoformat())

        response = self.client.get(reverse('schooladmin:member_profile', args=[self.member.pk]))
        self.assertEqual(response.status_code, 200)
        # The leave table's From/To cells must carry the converted BS strings
        # (the bug rendered the same raw AD `gap_start` in both columns).
        leaves_in_ctx = list(response.context['leaves'])
        self.assertEqual(len(leaves_in_ctx), 1)
        self.assertEqual(leaves_in_ctx[0].start_display, expected_start_bs)
        self.assertEqual(leaves_in_ctx[0].end_display, expected_end_bs)
        content = response.content.decode()
        self.assertIn(expected_start_bs, content)
        self.assertIn(expected_end_bs, content)


class ClientFollowUpCloseReopenAndFilterTests(TestCase):
    def setUp(self):
        self.org, self.admin_user = _make_org_and_admin('FollowUp')
        self.org.feature_clients = True
        self.org.allowed_features = sorted(set((self.org.allowed_features or []) + ['clients']))
        self.org.save(update_fields=['feature_clients', 'allowed_features'])
        self.client_obj = CRMClient.objects.create(
            org=self.org, client_number='FU-1', client_org_name='Follow-up Co',
            created_by=self.admin_user,
        )
        self.past_date = timezone.localdate() - datetime.timedelta(days=3)
        self.follow_up = ClientFollowUp.objects.create(
            client=self.client_obj, org=self.org, feedback='Initial call',
            priority='high', follow_up_date=self.past_date,
            next_follow_up_date=self.past_date, created_by=self.admin_user,
        )
        self.web = Client()
        self.web.login(username='adminFollowUp', password='testpass123')

    def test_close_removes_from_due_list_reopen_restores(self):
        due_resp = self.web.get(reverse('schooladmin:client_followup_due'))
        self.assertIn(self.client_obj, list(due_resp.context['clients_due']))

        close_resp = self.web.post(reverse('schooladmin:client_detail', args=[self.client_obj.pk]), {
            'action': 'close_followup', 'follow_up_id': self.follow_up.pk,
        })
        self.assertEqual(close_resp.status_code, 302)
        self.follow_up.refresh_from_db()
        self.assertEqual(self.follow_up.status, 'closed')
        self.assertIsNotNone(self.follow_up.closed_at)
        self.assertEqual(self.follow_up.closed_by, self.admin_user)

        due_resp2 = self.web.get(reverse('schooladmin:client_followup_due'))
        self.assertNotIn(self.client_obj, list(due_resp2.context['clients_due']))

        reopen_resp = self.web.post(reverse('schooladmin:client_detail', args=[self.client_obj.pk]), {
            'action': 'reopen_followup', 'follow_up_id': self.follow_up.pk,
        })
        self.assertEqual(reopen_resp.status_code, 302)
        self.follow_up.refresh_from_db()
        self.assertEqual(self.follow_up.status, 'open')
        self.assertIsNone(self.follow_up.closed_at)

        due_resp3 = self.web.get(reverse('schooladmin:client_followup_due'))
        self.assertIn(self.client_obj, list(due_resp3.context['clients_due']))

    def test_close_followup_is_org_isolated(self):
        other_org, other_admin = _make_org_and_admin('FollowUpOther')
        other_client = CRMClient.objects.create(
            org=other_org, client_number='FU-OTHER-1', client_org_name='Other Org Co',
            created_by=other_admin,
        )
        response = self.web.post(reverse('schooladmin:client_detail', args=[other_client.pk]), {
            'action': 'close_followup', 'follow_up_id': self.follow_up.pk,
        })
        self.assertEqual(response.status_code, 404)
        self.follow_up.refresh_from_db()
        self.assertEqual(self.follow_up.status, 'open')

    def test_followup_tab_filters_by_status_and_priority(self):
        closed_low = ClientFollowUp.objects.create(
            client=self.client_obj, org=self.org, feedback='Old resolved issue',
            priority='low', status='closed', follow_up_date=self.past_date,
            created_by=self.admin_user,
        )
        response = self.web.get(
            reverse('schooladmin:client_detail', args=[self.client_obj.pk]),
            {'fu_status': 'open', 'fu_priority': 'high'},
        )
        self.assertEqual(response.status_code, 200)
        follow_ups = list(response.context['follow_ups'])
        self.assertIn(self.follow_up, follow_ups)
        self.assertNotIn(closed_low, follow_ups)


class PayrollGenerateViewTests(TestCase):
    """Regression tests for schooladmin.views.generate (payslip generation)."""

    def setUp(self):
        self.org, self.admin_user = _make_org_and_admin("A")
        self.other_org, self.other_admin_user = _make_org_and_admin("B")

        self.staff_member = member.objects.create(
            org=self.org,
            name="Alice Employee",
            member_type="employee",
            gender="Female",
            salary_type="monthly",
            salary_amount=Decimal("30000.00"),
        )
        self.other_staff_member = member.objects.create(
            org=self.other_org,
            name="Bob Outsider",
            member_type="employee",
            gender="Male",
            salary_type="monthly",
            salary_amount=Decimal("30000.00"),
        )

        PayrollPolicy.objects.get_or_create(org=self.org)

        self.client = Client()
        self.client.login(username="adminA", password="testpass123")

        self.start = datetime.date(2026, 1, 1)
        self.end = datetime.date(2026, 1, 31)

    def _post_generate(self, member_id, start=None, end=None, extra=None):
        data = {
            "first_date": (start or self.start).strftime("%Y-%m-%d"),
            "last_date": (end or self.end).strftime("%Y-%m-%d"),
        }
        if extra:
            data.update(extra)
        return self.client.post(reverse("schooladmin:generate", args=(member_id,)), data)

    def test_generate_creates_one_payslip_with_server_computed_net(self):
        self._post_generate(self.staff_member.id)
        slips = PaySlip.objects.filter(member=self.staff_member)
        self.assertEqual(slips.count(), 1)
        slip = slips.first()
        # No attendance/leave records exist for the period, so every day is
        # correctly counted as unpaid absence and fully deducted.
        self.assertEqual(slip.gross_salary, Decimal("0.00"))
        self.assertEqual(slip.net_payable, Decimal("0.00"))

    def test_duplicate_generation_is_blocked(self):
        self._post_generate(self.staff_member.id)
        self._post_generate(self.staff_member.id)
        self.assertEqual(PaySlip.objects.filter(member=self.staff_member).count(), 1)

    def test_client_cannot_forge_net_payable(self):
        """Hidden POST fields for money must never be trusted."""
        self._post_generate(
            self.staff_member.id,
            extra={"net_payable": "999999.00", "gross_salary": "999999.00"},
        )
        slip = PaySlip.objects.get(member=self.staff_member)
        self.assertNotEqual(slip.net_payable, Decimal("999999.00"))
        self.assertNotEqual(slip.gross_salary, Decimal("999999.00"))

    def test_client_cannot_target_another_orgs_member_via_url(self):
        """Posting to another org's member id must 404, not create a payslip."""
        response = self._post_generate(self.other_staff_member.id)
        self.assertEqual(response.status_code, 404)
        self.assertFalse(PaySlip.objects.filter(member=self.other_staff_member).exists())

    def test_payslip_unique_constraint_enforced_at_db_level(self):
        PaySlip.objects.create(
            member=self.staff_member, org=self.org,
            from_date=self.start, to_date=self.end, month_name="January 2026",
        )
        with self.assertRaises(Exception):
            PaySlip.objects.create(
                member=self.staff_member, org=self.org,
                from_date=self.start, to_date=self.end, month_name="January 2026 dup",
            )


class BillPaymentUpdateTests(TestCase):
    """Regression tests for BillDetailView.post's 'update_payment' action."""

    def setUp(self):
        self.org, self.admin_user = _make_org_and_admin("Bill")
        self.org.feature_billing = True
        self.org.allowed_features = sorted(set(self.org.allowed_features + ['billing']))
        self.org.save(update_fields=['feature_billing', 'allowed_features'])
        self.student = member.objects.create(
            org=self.org, name="Charlie Student", member_type="student", gender="Male",
        )
        self.bill = Bill.objects.create(
            org=self.org, member=self.student, invoice_number="INV-TEST-0001",
            due_date=datetime.date(2026, 2, 1), total_amount=Decimal("1000.00"),
        )
        self.client = Client()
        self.client.login(username="adminBill", password="testpass123")

    def _post_payment(self, amount, status=None):
        data = {"action": "update_payment", "amount_paid": amount}
        if status is not None:
            data["status"] = status
        return self.client.post(
            reverse("schooladmin:bill_detail", args=(self.bill.pk,)), data
        )

    def test_negative_amount_rejected(self):
        self._post_payment("-500")
        self.bill.refresh_from_db()
        self.assertEqual(self.bill.amount_paid, Decimal("0.00"))

    def test_overpayment_rejected(self):
        self._post_payment("5000")
        self.bill.refresh_from_db()
        self.assertEqual(self.bill.amount_paid, Decimal("0.00"))

    def test_client_cannot_force_paid_status_without_full_amount(self):
        """Status must be derived server-side from the amount, not trusted raw."""
        self._post_payment("100", status="Paid")
        self.bill.refresh_from_db()
        self.assertEqual(self.bill.amount_paid, Decimal("100.00"))
        self.assertEqual(self.bill.status, "Partial")

    def test_full_payment_marks_paid(self):
        self._post_payment("1000")
        self.bill.refresh_from_db()
        self.assertEqual(self.bill.amount_paid, Decimal("1000.00"))
        self.assertEqual(self.bill.status, "Paid")


class CRMCustomerBillingSafetyTests(TestCase):
    def setUp(self):
        self.org, self.admin_user = _make_org_and_admin("CRM")
        self.org.feature_clients = True
        self.org.feature_finance = True
        self.org.allowed_features = sorted(set(self.org.allowed_features + ['clients', 'finance']))
        self.org.save(update_fields=['feature_clients', 'feature_finance', 'allowed_features'])
        self.inquiry = CRMClient.objects.create(
            org=self.org, client_number='LEAD-1', client_org_name='Inquiry Co',
            status='inquiry', priority='high', created_by=self.admin_user,
        )
        self.customer = CRMClient.objects.create(
            org=self.org, client_number='CUST-1', client_org_name='Customer Co',
            status='customer', priority='medium', created_by=self.admin_user,
        )
        self.web = Client()
        self.web.login(username='adminCRM', password='testpass123')

    def _post(self, crm_client, data):
        return self.web.post(
            reverse('schooladmin:client_detail', args=(crm_client.pk,)), data,
        )

    def test_inquiry_cannot_be_billed_server_side(self):
        self._post(self.inquiry, {
            'action': 'add_bill', 'invoice_number': 'CRM-LEAD-1',
            'amount': '1000.00', 'due_date': '2026-08-31',
        })
        self.assertFalse(CustomerBill.objects.filter(client=self.inquiry).exists())

    def test_profile_renders_priority_status_and_inquiry_explanation(self):
        response = self.web.get(reverse('schooladmin:client_detail', args=(self.inquiry.pk,)))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'High Priority')
        self.assertContains(response, 'still an')
        self.assertContains(response, 'Inquiry')
        self.assertContains(response, 'Convert to Customer')
        # Info/Bills/Contracts/Proposals/Docs tabs are hidden until converted.
        self.assertNotContains(response, 'tab-bills')
        self.assertNotContains(response, 'tab-info')

    def test_convert_to_customer_unlocks_other_tabs(self):
        self._post(self.inquiry, {'action': 'convert_to_customer'})
        self.inquiry.refresh_from_db()
        self.assertEqual(self.inquiry.status, 'customer')
        response = self.web.get(reverse('schooladmin:client_detail', args=(self.inquiry.pk,)))
        self.assertContains(response, 'tab-bills')
        self.assertContains(response, 'tab-info')
        self.assertNotContains(response, 'Convert to Customer')

    def test_blank_client_number_is_generated_in_sequence(self):
        first = CRMClient.create_for_org(
            org=self.org, client_org_name='Generated One',
        )
        second = CRMClient.create_for_org(
            org=self.org, client_org_name='Generated Two',
        )
        self.assertEqual(first.client_number, 'CLI-00001')
        self.assertEqual(second.client_number, 'CLI-00002')

    def test_admin_create_view_auto_generates_client_number(self):
        response = self.web.post(reverse('schooladmin:create_client'), {
            'client_number': '',
            'client_org_name': 'Generated Through View',
            'status': 'inquiry',
            'priority': 'medium',
        })
        created = CRMClient.objects.get(client_org_name='Generated Through View')
        self.assertEqual(created.client_number, 'CLI-00001')
        self.assertRedirects(
            response, reverse('schooladmin:client_detail', args=(created.pk,)),
            fetch_redirect_response=False,
        )

    def test_payment_status_and_income_use_only_incremental_payment(self):
        bill = CustomerBill.objects.create(
            org=self.org, client=self.customer, invoice_number='CRM-1',
            amount=Decimal('1000.00'), issue_date=datetime.date(2026, 7, 28),
            due_date=datetime.date(2026, 8, 31), status='unpaid',
            created_by=self.admin_user,
        )
        self._post(self.customer, {
            'action': 'record_bill_payment', 'bill_id': bill.pk,
            'payment_amount': '400.00', 'payment_date': '2026-07-28',
            'payment_method': 'bank', 'payment_reference': 'BANK-1',
            'add_to_income': 'on',
        })
        bill.refresh_from_db()
        self.assertEqual(bill.paid_amount, Decimal('400.00'))
        self.assertEqual(bill.status, 'partial')
        payment = CustomerBillPayment.objects.get(bill=bill)
        self.assertEqual(payment.income_transaction.amount, Decimal('400.00'))

        self._post(self.customer, {
            'action': 'record_bill_payment', 'bill_id': bill.pk,
            'payment_amount': '600.00', 'payment_date': '2026-07-29',
            'payment_method': 'cash',
        })
        bill.refresh_from_db()
        self.assertEqual(bill.paid_amount, Decimal('1000.00'))
        self.assertEqual(bill.status, 'paid')
        self.assertEqual(CustomerBillPayment.objects.filter(bill=bill).count(), 2)
        self.assertEqual(
            FinancialTransaction.objects.filter(
                customer_bill_payment__bill=bill,
            ).aggregate(total=Sum('amount'))['total'],
            Decimal('400.00'),
        )

    def test_overpayment_does_not_create_payment(self):
        bill = CustomerBill.objects.create(
            org=self.org, client=self.customer, invoice_number='CRM-2',
            amount=Decimal('100.00'), issue_date=datetime.date(2026, 7, 28),
            due_date=datetime.date(2026, 8, 31), status='unpaid',
        )
        self._post(self.customer, {
            'action': 'record_bill_payment', 'bill_id': bill.pk,
            'payment_amount': '101.00', 'payment_date': '2026-07-28',
        })
        bill.refresh_from_db()
        self.assertEqual(bill.paid_amount, Decimal('0.00'))
        self.assertFalse(CustomerBillPayment.objects.filter(bill=bill).exists())

    def test_other_organisation_invoice_is_not_accessible(self):
        other_org, _ = _make_org_and_admin("CRMOther")
        other_client = CRMClient.objects.create(
            org=other_org, client_number='OTHER-1', client_org_name='Other',
            status='customer',
        )
        response = self.web.get(reverse('schooladmin:client_detail', args=(other_client.pk,)))
        self.assertEqual(response.status_code, 404)


class CRMClientBranchRequiredTests(TestCase):
    """Branch selection is mandatory for orgs that actually use branches,
    but stays optional for orgs that have never configured any (branch
    management is an opt-in feature - most orgs have zero Branch rows)."""

    def setUp(self):
        self.org, self.admin_user = _make_org_and_admin("CRMBranch")
        self.org.feature_clients = True
        self.org.allowed_features = sorted(set(self.org.allowed_features + ['clients']))
        self.org.save(update_fields=['feature_clients', 'allowed_features'])
        self.branch = Branch.objects.create(org=self.org, name='HQ', status='active')
        self.web = Client()
        self.web.login(username='adminCRMBranch', password='testpass123')

    def test_create_client_without_branch_is_rejected_when_org_has_branches(self):
        response = self.web.post(reverse('schooladmin:create_client'), {
            'client_org_name': 'No Branch Co', 'status': 'inquiry', 'priority': 'medium',
        })
        self.assertFalse(CRMClient.objects.filter(client_org_name='No Branch Co').exists())
        self.assertRedirects(response, reverse('schooladmin:create_client'))

    def test_create_client_with_branch_succeeds(self):
        self.web.post(reverse('schooladmin:create_client'), {
            'client_org_name': 'Has Branch Co', 'status': 'inquiry', 'priority': 'medium',
            'branch': self.branch.pk,
        })
        client = CRMClient.objects.get(client_org_name='Has Branch Co')
        self.assertEqual(client.branch_id, self.branch.pk)

    def test_update_info_without_branch_is_rejected_when_org_has_branches(self):
        client = CRMClient.objects.create(
            org=self.org, client_number='B-1', client_org_name='Existing Co',
            status='customer', branch=self.branch, created_by=self.admin_user,
        )
        self.web.post(reverse('schooladmin:client_detail', args=(client.pk,)), {
            'action': 'update_info', 'client_org_name': 'Existing Co',
            'status': 'customer', 'priority': 'medium',
        })
        client.refresh_from_db()
        self.assertEqual(client.branch_id, self.branch.pk)  # unchanged, not cleared

    def test_client_create_form_without_org_branches_does_not_require_branch(self):
        other_org, other_admin = _make_org_and_admin("CRMNoBranch")
        other_org.feature_clients = True
        other_org.allowed_features = sorted(set(other_org.allowed_features + ['clients']))
        other_org.save(update_fields=['feature_clients', 'allowed_features'])
        web = Client()
        web.login(username='adminCRMNoBranch', password='testpass123')
        web.post(reverse('schooladmin:create_client'), {
            'client_org_name': 'No Branches Org Client', 'status': 'inquiry', 'priority': 'medium',
        })
        self.assertTrue(CRMClient.objects.filter(client_org_name='No Branches Org Client').exists())


class AutoCheckinDateTimeSplitTests(TestCase):
    """The auto check-in form used to render a single native `datetime-local`
    input for checkin/checkout - no BS calendar support and inconsistent with
    every other date field in the app. It's now a date + time pair per
    side, recombined server-side into the model's DateTimeFields."""

    def setUp(self):
        self.org, self.admin_user = _make_org_and_admin("AutoCheckin")
        self.member = member.objects.create(
            org=self.org, name='Auto Checkin Member', member_type='member', gender='Male',
        )
        self.web = Client()
        self.web.login(username='adminAutoCheckin', password='testpass123')

    def test_add_form_renders_date_and_time_fields_not_datetime_local(self):
        response = self.web.get(reverse('schooladmin:auto_checkin_add'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="checkin_date"')
        self.assertContains(response, 'name="checkin_time_only"')
        self.assertContains(response, 'name="checkout_date"')
        self.assertContains(response, 'name="checkout_time_only"')
        self.assertNotContains(response, 'datetime-local')

    def test_create_combines_date_and_time_into_model_datetimes(self):
        response = self.web.post(reverse('schooladmin:auto_checkin_add'), {
            'member': self.member.pk, 'name': 'Morning shift',
            'checkin_date': '2026-08-10', 'checkin_time_only': '09:00',
            'checkout_date': '2026-08-10', 'checkout_time_only': '17:00',
        })
        self.assertRedirects(
            response, reverse('schooladmin:auto_checkin_list'), fetch_redirect_response=False,
        )
        record = AutoCheckin.objects.get(org=self.org, name='Morning shift')
        local_in = timezone.localtime(record.checkin_time)
        local_out = timezone.localtime(record.checkout_time)
        self.assertEqual((local_in.date(), local_in.hour, local_in.minute), (datetime.date(2026, 8, 10), 9, 0))
        self.assertEqual((local_out.date(), local_out.hour, local_out.minute), (datetime.date(2026, 8, 10), 17, 0))
        self.assertTrue(AttendanceRecord.objects.filter(mem=self.member, scanned_time=record.checkin_time).exists())
        self.assertTrue(AttendanceRecord.objects.filter(mem=self.member, scanned_time=record.checkout_time).exists())

    def test_checkout_before_checkin_is_rejected(self):
        response = self.web.post(reverse('schooladmin:auto_checkin_add'), {
            'member': self.member.pk, 'name': 'Bad shift',
            'checkin_date': '2026-08-10', 'checkin_time_only': '17:00',
            'checkout_date': '2026-08-10', 'checkout_time_only': '09:00',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Check-out must be after check-in')
        self.assertFalse(AutoCheckin.objects.filter(org=self.org, name='Bad shift').exists())

    def test_edit_form_prefills_split_fields_from_existing_record(self):
        record = AutoCheckin.objects.create(
            org=self.org, member=self.member, name='Existing shift',
            checkin_time=timezone.make_aware(datetime.datetime(2026, 8, 11, 8, 30)),
            checkout_time=timezone.make_aware(datetime.datetime(2026, 8, 11, 16, 30)),
        )
        response = self.web.get(reverse('schooladmin:auto_checkin_edit', args=(record.pk,)))
        self.assertEqual(response.status_code, 200)
        form = response.context['form']
        self.assertEqual(form.fields['checkin_date'].initial, datetime.date(2026, 8, 11))
        self.assertEqual(form.fields['checkin_time_only'].initial, datetime.time(8, 30))
        self.assertEqual(form.fields['checkout_time_only'].initial, datetime.time(16, 30))
        self.assertContains(response, 'value="2026-08-11"')
        self.assertContains(response, 'value="08:30:00"')

    def test_edit_is_scoped_to_own_organisation(self):
        other_org, other_admin = _make_org_and_admin("AutoCheckinOther")
        other_member = member.objects.create(
            org=other_org, name='Other Org Member', member_type='member', gender='Female',
        )
        other_record = AutoCheckin.objects.create(
            org=other_org, member=other_member, name='Other org shift',
            checkin_time=timezone.make_aware(datetime.datetime(2026, 8, 11, 8, 30)),
            checkout_time=timezone.make_aware(datetime.datetime(2026, 8, 11, 16, 30)),
        )
        response = self.web.get(reverse('schooladmin:auto_checkin_edit', args=(other_record.pk,)))
        self.assertEqual(response.status_code, 404)


class DailyAndGapReportPrintTests(TestCase):
    """Attendance Issues moved from an inline card into a `.no-print` modal
    (so it no longer bloats the printed report), and the Member Gap Report's
    calendar view is now the default (previously table-first)."""

    def setUp(self):
        self.org, self.admin_user = _make_org_and_admin("ReportPrint")
        self.member = member.objects.create(
            org=self.org, name='Report Print Member', member_type='member', gender='Male',
            shift_start_time=datetime.time(9, 0), shift_end_time=datetime.time(17, 0),
        )
        self.web = Client()
        self.web.login(username='adminReportPrint', password='testpass123')

    def test_daily_report_moves_issues_into_no_print_modal(self):
        response = self.web.get(reverse('schooladmin:dailyReport'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="attendanceIssuesModal"')
        self.assertContains(response, 'modal fade no-print')
        self.assertContains(response, 'data-bs-target="#attendanceIssuesModal"')
        # The old inline card wrapper is gone - the table now only exists
        # inside the modal.
        self.assertNotContains(response, 'class="issue-card mb-3"')

    def test_daily_report_summary_tiles_excluded_from_print(self):
        response = self.web.get(reverse('schooladmin:dailyReport'))
        self.assertContains(response, 'summary-tabs-wrapper mb-3 no-print')

    def test_daily_report_print_css_resets_report_card_overflow(self):
        # Regression: "only 1 page prints with 100 members, rest cut off".
        # .report-card's base (screen) rule sets overflow:hidden to clip the
        # table's square corners to the card's rounded border. Left in
        # effect at print time, it clips the table itself past whatever
        # height the box's first layout pass produced, silently truncating
        # any members beyond that - regardless of page count. Must be reset
        # to visible specifically inside @media print.
        response = self.web.get(reverse('schooladmin:dailyReport'))
        self.assertContains(response, 'overflow: visible !important;')

    def test_member_gap_report_get_context_has_first_and_last_date(self):
        # Regression test: the calendar's `initialDate` is built from
        # first_date, which the GET view never used to set (only POST did) -
        # defaulting to the calendar view surfaced a JS crash on first load
        # because FullCalendar received an empty date string.
        response = self.web.get(reverse('schooladmin:memberGapReport', args=(self.member.pk,)))
        self.assertEqual(response.status_code, 200)
        self.assertIn('first_date', response.context)
        self.assertIn('last_date', response.context)
        self.assertIsNotNone(response.context['first_date'])
        self.assertIsNotNone(response.context['last_date'])

    def test_member_gap_report_calendar_is_default_view(self):
        response = self.web.get(reverse('schooladmin:memberGapReport', args=(self.member.pk,)))
        self.assertContains(response, 'id="table-view" class="card filter-card hidden"')
        self.assertContains(response, '<i class="fas fa-list"></i> Table View')

    def test_member_switcher_lists_org_members_with_current_one_selected(self):
        other_member = member.objects.create(
            org=self.org, name='Another Member', member_type='member', gender='Female',
        )
        response = self.web.get(reverse('schooladmin:memberGapReport', args=(self.member.pk,)))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="memberSwitcher"')
        self.assertContains(
            response,
            f'<option value="{self.member.pk}" selected>Report Print Member</option>',
        )
        self.assertContains(response, f'<option value="{other_member.pk}" >Another Member</option>')

    def test_member_switcher_excludes_other_orgs_members(self):
        other_org, _ = _make_org_and_admin('OtherOrgForSwitcher')
        outsider = member.objects.create(org=other_org, name='Outsider Member', gender='Male')
        response = self.web.get(reverse('schooladmin:memberGapReport', args=(self.member.pk,)))
        self.assertNotContains(response, 'Outsider Member')

    def test_switching_member_via_url_shows_new_members_report(self):
        # Simulates what the switcher's JS does client-side: re-submit to
        # the newly selected member's own gap-report URL.
        other_member = member.objects.create(
            org=self.org, name='Switched To Member', member_type='member', gender='Female',
        )
        response = self.web.get(reverse('schooladmin:memberGapReport', args=(other_member.pk,)))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['current_member'], other_member)
        self.assertContains(
            response,
            f'<option value="{other_member.pk}" selected>Switched To Member</option>',
        )

    def test_gap_report_does_not_force_single_page_print(self):
        # Regression: a named `@page gap-calendar-page` rule was added
        # alongside this page's own pre-existing unnamed `@page { size: A4
        # landscape; margin: 8mm; }` rule - two conflicting page geometries
        # on one stylesheet, which named-page CSS support handles
        # inconsistently across browsers/print engines. Only Monthly
        # Report's per-member Calendar tab ("month report of staff") should
        # force one page; the Gap Report calendar prints normally, same as
        # its table view always has.
        response = self.web.get(reverse('schooladmin:memberGapReport', args=(self.member.pk,)))
        self.assertNotContains(response, 'gap-calendar-page')

    def test_member_report_print_keeps_the_selected_calendar_or_table_view(self):
        # Print the view selected by the admin. Do not hide a rendered calendar
        # and silently substitute the table when print mode starts.
        response = self.web.get(reverse('schooladmin:memberGapReport', args=(self.member.pk,)))
        self.assertNotContains(response, '#calendar-view { display: none !important; }')
        self.assertNotContains(response, '#table-view { display: block !important; }')

    def test_long_report_print_css_removes_dashboard_viewport_clipping(self):
        urls = (
            reverse('schooladmin:dailyReport'),
            reverse('schooladmin:gapReport'),
            reverse('schooladmin:memberGapReport', args=(self.member.pk,)),
        )
        for url in urls:
            with self.subTest(url=url):
                response = self.web.get(url)
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, 'max-height: none !important;')
                self.assertContains(response, '#printarea .table-responsive')
                self.assertContains(response, 'display: table-header-group;')
                self.assertContains(response, 'break-inside: avoid-page;')


class SupplierPurchaseWorkflowTests(TestCase):
    def setUp(self):
        self.org, self.admin_user = _make_org_and_admin('SupplierPurchase')
        self.org.feature_stock = True
        self.org.allowed_features = sorted(set(self.org.allowed_features + ['stock']))
        self.org.save(update_fields=['feature_stock', 'allowed_features'])
        self.supplier = Supplier.objects.create(
            org=self.org, name='Everest Supplies', status='active',
            credit_limit=Decimal('5000.00'), created_by=self.admin_user,
        )
        self.item = StockItem.objects.create(
            org=self.org, name='Printer Paper', unit='ream',
            status='active', purchase_cost=Decimal('450.00'),
        )
        self.web = Client()
        self.web.login(username='adminSupplierPurchase', password='testpass123')

    def test_supplier_profile_link_preselects_supplier(self):
        response = self.web.get(
            reverse('schooladmin:add_purchase'), {'supplier': self.supplier.pk},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['form'].initial['supplier'], self.supplier)
        self.assertContains(response, 'Creating a purchase for')
        profile = self.web.get(
            reverse('schooladmin:supplier_detail', args=(self.supplier.pk,)),
        )
        self.assertContains(profile, f'?supplier={self.supplier.pk}')

    def test_purchase_can_be_created_with_blank_tax(self):
        response = self.web.post(reverse('schooladmin:add_purchase'), {
            'supplier': self.supplier.pk,
            'purchase_date': '2026-07-28',
            'invoice_number': 'SUP-INV-1',
            'payment_method': 'cash',
            'tax_amount': '',
            'notes': '',
            'source_supplier': self.supplier.pk,
            'items-TOTAL_FORMS': '1',
            'items-INITIAL_FORMS': '0',
            'items-MIN_NUM_FORMS': '1',
            'items-MAX_NUM_FORMS': '1000',
            'items-0-stock_item': self.item.pk,
            'items-0-description': '',
            'items-0-quantity': '2',
            'items-0-unit_cost': '450.00',
        })
        purchase = Purchase.objects.get(invoice_number='SUP-INV-1')
        self.assertEqual(purchase.supplier, self.supplier)
        self.assertEqual(purchase.tax_amount, Decimal('0.00'))
        self.assertEqual(purchase.total_amount, Decimal('900.00'))
        self.assertEqual(purchase.items.count(), 1)
        self.assertRedirects(
            response, reverse('schooladmin:purchase_detail', args=(purchase.pk,)),
            fetch_redirect_response=False,
        )

    def test_invalid_line_shows_specific_error(self):
        response = self.web.post(reverse('schooladmin:add_purchase'), {
            'supplier': self.supplier.pk,
            'purchase_date': '2026-07-28',
            'payment_method': 'cash',
            'tax_amount': '0',
            'items-TOTAL_FORMS': '1',
            'items-INITIAL_FORMS': '0',
            'items-MIN_NUM_FORMS': '1',
            'items-MAX_NUM_FORMS': '1000',
            'items-0-stock_item': self.item.pk,
            'items-0-description': '',
            'items-0-quantity': '0',
            'items-0-unit_cost': '450.00',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Quantity must be greater than zero.')
        self.assertFalse(Purchase.objects.exists())

    def test_supplier_profile_uses_real_purchase_totals(self):
        purchase = Purchase.objects.create(
            org=self.org, supplier=self.supplier, purchase_date=datetime.date(2026, 7, 28),
            invoice_number='PROFILE-1', status='received',
        )
        PurchaseItem.objects.create(
            purchase=purchase, stock_item=self.item,
            quantity=Decimal('3.00'), unit_cost=Decimal('450.00'),
        )
        purchase.recalc_totals()
        response = self.web.get(
            reverse('schooladmin:supplier_detail', args=(self.supplier.pk,)),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['supplied_quantity'], Decimal('3.00'))
        self.assertEqual(response.context['purchase_count'], 1)
        self.assertContains(response, 'Stock Supplied')


class SupplierBillPaymentTrackingTests(TestCase):
    """Phase 6: per-bill due date / discount / paid / due tracking on
    Purchase, on top of (not replacing) the existing supplier-level running
    balance via SupplierPayment."""

    def setUp(self):
        self.org, self.admin_user = _make_org_and_admin('SupplierBillPayment')
        self.org.feature_stock = True
        self.org.allowed_features = sorted(set(self.org.allowed_features + ['stock']))
        self.org.save(update_fields=['feature_stock', 'allowed_features'])
        self.supplier = Supplier.objects.create(org=self.org, name='Kathmandu Traders', status='active')
        self.other_supplier = Supplier.objects.create(org=self.org, name='Other Vendor', status='active')
        self.item = StockItem.objects.create(
            org=self.org, name='Toner Cartridge', unit='pcs', status='active', purchase_cost=Decimal('1000.00'),
        )
        self.purchase = Purchase.objects.create(
            org=self.org, supplier=self.supplier, purchase_date=datetime.date(2026, 7, 1),
            due_date=datetime.date(2026, 7, 31), invoice_number='SUP-100',
            discount_amount=Decimal('50.00'), tax_amount=Decimal('13.00'),
        )
        PurchaseItem.objects.create(purchase=self.purchase, stock_item=self.item, quantity=Decimal('1.00'), unit_cost=Decimal('1000.00'))
        self.purchase.recalc_totals()
        self.web = Client()
        self.web.login(username='adminSupplierBillPayment', password='testpass123')

    def test_recalc_totals_applies_discount(self):
        self.purchase.refresh_from_db()
        # subtotal 1000, discount 50, tax 13 -> 963
        self.assertEqual(self.purchase.subtotal, Decimal('1000.00'))
        self.assertEqual(self.purchase.total_amount, Decimal('963.00'))

    def test_unpaid_bill_has_full_due_amount(self):
        self.assertEqual(self.purchase.paid_amount, Decimal('0.00'))
        self.assertEqual(self.purchase.due_amount, Decimal('963.00'))
        self.assertEqual(self.purchase.payment_status, 'Unpaid')

    def test_payment_allocated_to_purchase_reduces_due_amount(self):
        response = self.web.post(
            reverse('schooladmin:add_supplier_payment', args=(self.supplier.pk,)),
            {
                'purchase': self.purchase.id, 'amount': '400.00',
                'payment_date': '2026-07-15', 'payment_method': 'cash',
            },
        )
        self.assertRedirects(response, reverse('schooladmin:purchase_detail', args=(self.purchase.pk,)))
        self.purchase.refresh_from_db()
        self.assertEqual(self.purchase.paid_amount, Decimal('400.00'))
        self.assertEqual(self.purchase.due_amount, Decimal('563.00'))
        self.assertEqual(self.purchase.payment_status, 'Partial')

    def test_full_payment_marks_bill_paid(self):
        self.web.post(
            reverse('schooladmin:add_supplier_payment', args=(self.supplier.pk,)),
            {
                'purchase': self.purchase.id, 'amount': '963.00',
                'payment_date': '2026-07-20', 'payment_method': 'bank',
            },
        )
        self.purchase.refresh_from_db()
        self.assertEqual(self.purchase.due_amount, Decimal('0.00'))
        self.assertEqual(self.purchase.payment_status, 'Paid')

    def test_general_payment_without_purchase_still_works(self):
        """Backward compatibility: a payment not tied to any specific bill
        still counts toward the supplier's running balance, same as before
        this phase, and never affects any individual Purchase's paid_amount."""
        response = self.web.post(
            reverse('schooladmin:add_supplier_payment', args=(self.supplier.pk,)),
            {'amount': '200.00', 'payment_date': '2026-07-10', 'payment_method': 'cash'},
        )
        self.assertRedirects(
            response,
            f"{reverse('schooladmin:supplier_detail', args=(self.supplier.pk,))}?tab=payments",
        )
        self.supplier.refresh_from_db()
        self.assertEqual(self.supplier.total_paid(), Decimal('200.00'))
        self.purchase.refresh_from_db()
        self.assertEqual(self.purchase.paid_amount, Decimal('0.00'))

    def test_cannot_allocate_payment_to_another_suppliers_bill(self):
        other_purchase = Purchase.objects.create(
            org=self.org, supplier=self.other_supplier, purchase_date=datetime.date(2026, 7, 1),
        )
        response = self.web.post(
            reverse('schooladmin:add_supplier_payment', args=(self.supplier.pk,)),
            {
                'purchase': other_purchase.id, 'amount': '100.00',
                'payment_date': '2026-07-15', 'payment_method': 'cash',
            },
        )
        # The form scopes `purchase` choices to this supplier only, so an
        # id from a different supplier is simply not a valid choice.
        other_purchase.refresh_from_db()
        self.assertEqual(other_purchase.paid_amount, Decimal('0.00'))


class NepaliMonthlyAttendanceReportTests(TestCase):
    def setUp(self):
        self.org, self.admin_user = _make_org_and_admin('NepaliMonthly')
        self.org.nepali_date = True
        self.org.save(update_fields=['nepali_date'])
        self.web = Client()
        self.web.login(username='adminNepaliMonthly', password='testpass123')

    def test_default_report_uses_current_bs_month(self):
        today = timezone.localdate()
        today_np = nepali_datetime.date.from_datetime_date(today)
        expected_start = nepali_datetime.date(
            today_np.year, today_np.month, 1,
        ).to_datetime_date()

        response = self.web.get(reverse('schooladmin:monthly_report'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['start'], expected_start)
        self.assertEqual(response.context['end'], today)
        self.assertEqual(response.context['days'][0]['dom'], '01')
        self.assertEqual(
            response.context['days'][-1]['dom'], f'{today_np.day:02d}',
        )
        self.assertContains(response, '(BS)')
        self.assertContains(response, f'value="{today_np.year}-{today_np.month:02d}-01"')

    def test_last_month_uses_complete_previous_bs_month(self):
        today = timezone.localdate()
        today_np = nepali_datetime.date.from_datetime_date(today)
        current_bs_start = nepali_datetime.date(
            today_np.year, today_np.month, 1,
        ).to_datetime_date()
        if today_np.month == 1:
            previous_year, previous_month = today_np.year - 1, 12
        else:
            previous_year, previous_month = today_np.year, today_np.month - 1
        expected_start = nepali_datetime.date(
            previous_year, previous_month, 1,
        ).to_datetime_date()

        response = self.web.get(
            reverse('schooladmin:monthly_report'), {'preset': 'last_month'},
        )

        self.assertEqual(response.context['start'], expected_start)
        self.assertEqual(
            response.context['end'], current_bs_start - datetime.timedelta(days=1),
        )
        self.assertEqual(response.context['days'][0]['dom'], '01')

    def test_custom_bs_range_is_converted_for_database_query(self):
        today_np = nepali_datetime.date.from_datetime_date(timezone.localdate())
        from_np = nepali_datetime.date(today_np.year, today_np.month, 2)
        to_np = nepali_datetime.date(today_np.year, today_np.month, 5)

        response = self.web.get(reverse('schooladmin:monthly_report'), {
            'from_date_np': str(from_np),
            'to_date_np': str(to_np),
        })

        self.assertEqual(response.context['start'], from_np.to_datetime_date())
        self.assertEqual(response.context['end'], to_np.to_datetime_date())
        self.assertEqual(
            [day['dom'] for day in response.context['days']],
            ['02', '03', '04', '05'],
        )


class MonthlyReportEnhancementsTests(TestCase):
    """Phase 7: Monthly Report branch scoping fix + Section/Attendance %/
    Paid-Unpaid Leave columns + print-preference context."""

    def setUp(self):
        self.org, self.admin_user = _make_org_and_admin('MonthlyEnh')
        self.branch_a = Branch.objects.create(org=self.org, name='Branch A', code='MEA')
        self.branch_b = Branch.objects.create(org=self.org, name='Branch B', code='MEB')
        dept = Classification.objects.create(org=self.org, name='Dept')
        self.section = Section.objects.create(org=self.org, branch=self.branch_a, classification=dept, name='Team X')

        self.member_a = member.objects.create(
            org=self.org, name='Amber A', gender='Female', branch=self.branch_a, section=self.section,
        )
        self.member_b = member.objects.create(org=self.org, name='Bailey B', gender='Male', branch=self.branch_b)

        self.manager_member = member.objects.create(org=self.org, name='Manager A', gender='Male', branch=self.branch_a)
        self.manager_user = CustomUser.objects.create_user(
            username='monthly-mgr-a', email='monthly-mgr-a@example.com', password='testpass123', user_type='3',
        )
        from handle.models import StaffPermission
        Staff.objects.create(admin=self.manager_user, org=self.org, member=self.manager_member)
        StaffPermission.objects.create(member=self.manager_member, org=self.org, can_view_members=True)
        self.branch_a.manager = self.manager_user
        self.branch_a.save(update_fields=['manager'])

        self.web = Client()

    def test_branch_manager_is_blocked_by_admin_only_gate(self):
        # Monthly Report is admin-only (AdminRequiredMixin restricts to
        # user_type 1/2) — Staff/branch-manager users (user_type 3) never
        # reach the view, so get_accessible_members's scoping is inert
        # for them today. This locks in that existing access boundary; the
        # scoped queryset itself is exercised via get_accessible_members's
        # own tests in handle.tests.BranchManagerScopingTests.
        self.web.force_login(self.manager_user)
        response = self.web.get(reverse('schooladmin:monthly_report'))
        self.assertEqual(response.status_code, 302)

    def test_admin_sees_all_branches_in_summary(self):
        self.web.force_login(self.admin_user)
        response = self.web.get(reverse('schooladmin:monthly_report'))
        names = {r['name'] for r in response.context['rows']}
        self.assertIn('Amber A', names)
        self.assertIn('Bailey B', names)

    def test_summary_rows_include_new_fields(self):
        self.web.force_login(self.admin_user)
        response = self.web.get(reverse('schooladmin:monthly_report'))
        row = next(r for r in response.context['rows'] if r['name'] == 'Amber A')
        self.assertEqual(row['section'], 'Team X')
        self.assertIn('paid_leave', row)
        self.assertIn('unpaid_leave', row)
        self.assertIn('attendance_pct', row)

    def test_member_without_section_shows_blank(self):
        self.web.force_login(self.admin_user)
        response = self.web.get(reverse('schooladmin:monthly_report'))
        row = next(r for r in response.context['rows'] if r['name'] == 'Bailey B')
        self.assertEqual(row['section'], '')

    def test_print_preference_defaults_in_context(self):
        self.web.force_login(self.admin_user)
        response = self.web.get(reverse('schooladmin:monthly_report'))
        self.assertEqual(response.context['print_preference']['paper'], 'A4')

    def test_csv_export_includes_new_columns(self):
        self.web.force_login(self.admin_user)
        response = self.web.get(reverse('schooladmin:monthly_report'), {'export': 'csv'})
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        header = content.splitlines()[0]
        self.assertIn('Section', header)
        self.assertIn('Paid Leave', header)
        self.assertIn('Unpaid Leave', header)
        self.assertIn('Attendance %', header)


class PermanentQRHistoryTests(TestCase):
    def setUp(self):
        self.org, self.admin_user = _make_org_and_admin("QRHistory")
        self.org.enable_qr_attendance = True
        self.org.save(update_fields=["enable_qr_attendance"])
        self.client = Client()
        self.client.login(username="adminQRHistory", password="testpass123")
        now = timezone.now()
        self.active_qr = QRAttendanceSession.objects.create(
            org=self.org,
            generated_by=self.admin_user,
            token="active-permanent-token",
            session_type="permanent",
            status="active",
            valid_from=now,
            location_name="Main Gate",
            latitude=27.717245,
            longitude=85.323961,
            radius_meters=120,
        )
        self.archived_qr = QRAttendanceSession.objects.create(
            org=self.org,
            generated_by=self.admin_user,
            token="archived-permanent-token",
            session_type="permanent",
            status="closed",
            valid_from=now - datetime.timedelta(days=1),
            closed_at=now,
            location_name="Old Office",
            latitude=27.700001,
            longitude=85.300001,
            radius_meters=80,
        )

    def test_qr_page_lists_saved_permanent_qrs_with_location_and_print_links(self):
        response = self.client.get(reverse("schooladmin:qr_attendance"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Previously Generated Permanent QR Codes")
        self.assertContains(response, "Main Gate")
        self.assertContains(response, "Old Office")
        self.assertContains(response, "27.717245")
        self.assertContains(response, "data:image/png;base64,")
        self.assertContains(
            response,
            reverse("schooladmin:qr_permanent_print", args=[self.active_qr.pk]),
        )

    def test_a4_print_view_contains_qr_and_archived_warning(self):
        response = self.client.get(
            reverse("schooladmin:qr_permanent_print", args=[self.archived_qr.pk])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Archived · attendance disabled")
        self.assertContains(response, "Old Office")
        self.assertContains(response, "27.700001, 85.300001")
        self.assertContains(response, "data:image/png;base64,")
        self.assertContains(response, "will not mark attendance")

    def test_print_view_rejects_another_organizations_qr(self):
        other_org, other_admin = _make_org_and_admin("QROther")
        other_qr = QRAttendanceSession.objects.create(
            org=other_org,
            generated_by=other_admin,
            token="other-org-permanent-token",
            session_type="permanent",
            status="active",
            valid_from=timezone.now(),
            location_name="Other Premises",
            latitude=27.1,
            longitude=85.1,
            radius_meters=100,
        )

        response = self.client.get(
            reverse("schooladmin:qr_permanent_print", args=[other_qr.pk])
        )

        self.assertEqual(response.status_code, 404)


class IDCardTests(TestCase):
    def setUp(self):
        self.org, self.admin_user = _make_org_and_admin("IDC")
        self.org.feature_id_cards = True
        self.org.allowed_features = sorted(set(self.org.allowed_features + ['id_cards']))
        self.org.save(update_fields=['feature_id_cards', 'allowed_features'])
        self.classification = None
        from handle.models import Classification
        self.classification = Classification.objects.create(org=self.org, name="Grade 10")
        self.member1 = member.objects.create(
            org=self.org, name="Card Holder One", member_type="student", gender="Male",
            classification=self.classification, roll_number="R-001",
        )
        self.member2 = member.objects.create(
            org=self.org, name="Card Holder Two", member_type="student", gender="Female",
        )
        self.client = Client()
        self.client.login(username="adminIDC", password="testpass123")

    def test_settings_view_creates_default_template(self):
        resp = self.client.get(reverse('schooladmin:idcard_settings'))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(IDCardTemplate.objects.filter(org=self.org).count(), 1)
        template = IDCardTemplate.objects.get(org=self.org)
        self.assertEqual(template.card_dimensions_mm(), (54, 86))

    def test_settings_post_saves_field_toggles(self):
        self.client.get(reverse('schooladmin:idcard_settings'))
        self.client.post(reverse('schooladmin:idcard_settings'), {
            'card_size': 'cr80',
            'custom_width_mm': 86,
            'custom_height_mm': 54,
            'photo_size': 'large',
            'custom_photo_size_mm': 25,
            'show_logo': '',
            'show_org_name': 'on',
            'show_photo': 'on',
            'show_member_id': 'on',
            'show_roll_number': 'on',
            'show_address': '',
            'show_phone': '',
            'show_email': '',
            'show_classification': 'on',
        })
        template = IDCardTemplate.objects.get(org=self.org)
        self.assertFalse(template.show_logo)
        self.assertTrue(template.show_org_name)
        self.assertEqual(template.photo_size, 'large')

    def test_generate_view_without_filter_shows_no_cards(self):
        resp = self.client.get(reverse('schooladmin:idcard_generate'))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.context['members']), 0)

    def test_generate_view_all_members(self):
        resp = self.client.get(reverse('schooladmin:idcard_generate'), {'generate': '1'})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.context['members']), 2)

    def test_generate_view_filtered_by_classification(self):
        resp = self.client.get(reverse('schooladmin:idcard_generate'), {
            'generate': '1', 'classification': self.classification.id,
        })
        members = list(resp.context['members'])
        self.assertEqual(len(members), 1)
        self.assertEqual(members[0].id, self.member1.id)

    def test_cross_org_member_excluded(self):
        other_org, _ = _make_org_and_admin("IDCOther")
        member.objects.create(org=other_org, name="Outsider", member_type="student", gender="Male")
        resp = self.client.get(reverse('schooladmin:idcard_generate'), {'generate': '1'})
        names = [m.name for m in resp.context['members']]
        self.assertNotIn("Outsider", names)

    def test_settings_rejects_unknown_design_key(self):
        resp = self.client.get(
            reverse('schooladmin:idcard_settings'),
            {'design': '../../not-a-template'},
        )

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context['selected_design'], IDCardTemplate.DESIGN_CHOICES[0][0])
        self.assertFalse(
            IDCardTemplate.objects.filter(
                org=self.org, name='../../not-a-template',
            ).exists()
        )

    def test_generate_filters_by_member_type_and_search(self):
        resp = self.client.get(reverse('schooladmin:idcard_generate'), {
            'generate': '1',
            'member_type': 'student',
            'q': 'Holder One',
        })

        self.assertEqual(resp.status_code, 200)
        self.assertEqual([item.pk for item in resp.context['members']], [self.member1.pk])

    def test_id_card_typography_saves_and_legacy_fields_stay_disabled(self):
        self.client.get(reverse('schooladmin:idcard_settings'))
        response = self.client.post(reverse('schooladmin:idcard_settings'), {
            'card_size': 'cr80', 'custom_width_mm': 86, 'custom_height_mm': 54,
            'photo_size': 'medium', 'custom_photo_size_mm': 25,
            'primary_color': '#172554', 'secondary_color': '#c59d3f',
            'text_color': '#111827', 'font_family': 'montserrat',
            'base_font_size': 11, 'name_font_size': 16, 'org_font_size': 14,
            'line_height': '1.40', 'card_title': 'STUDENT ID',
            'footer_text': 'Return to the administration office.',
            'show_logo': 'on', 'show_org_name': 'on', 'show_photo': 'on',
            'show_member_id': 'on', 'show_roll_number': 'on',
            'show_classification': 'on', 'show_blood_group': 'on',
            'show_signature': 'on', 'show_valid_until': 'on',
        })
        self.assertEqual(response.status_code, 302)
        template = IDCardTemplate.objects.get(org=self.org, is_default=True)
        self.assertEqual(template.font_family, 'montserrat')
        self.assertEqual(template.name_font_size, 16)
        self.assertFalse(template.show_blood_group)
        self.assertFalse(template.show_signature)
        self.assertFalse(template.show_valid_until)


class CertificateDesignerTests(TestCase):
    def setUp(self):
        self.org, self.admin_user = _make_org_and_admin('Certificate')
        self.org.feature_id_cards = True
        self.org.allowed_features = sorted(set(self.org.allowed_features + ['id_cards']))
        self.org.save(update_fields=['feature_id_cards', 'allowed_features'])
        self.classification = Classification.objects.create(org=self.org, name='Grade 12')
        self.member = member.objects.create(
            org=self.org, name='Certificate Recipient', member_type='student',
            gender='Female', classification=self.classification, roll_number='C-001',
        )
        self.client = Client()
        self.client.login(username='adminCertificate', password='testpass123')

    def _create_template(self, **overrides):
        values = {
            'org': self.org, 'name': 'Completion Certificate',
            'certificate_type': 'completion', 'title': 'Certificate of Completion',
            'body_html': '<p>Presented to <strong>[[member_name]]</strong> of [[classification]] at [[organization]].</p>',
            'is_default': True,
        }
        values.update(overrides)
        return CertificateTemplate.objects.create(**values)

    def test_certificate_designer_saves_sanitized_rich_text(self):
        response = self.client.post(reverse('schooladmin:certificate_settings'), {
            'name': 'Achievement 2026', 'certificate_type': 'achievement',
            'orientation': 'landscape', 'title': 'Certificate of Achievement',
            'subtitle': 'Proudly presented to',
            'body_html': '<p style="text-align:center">Well done <strong>[[member_name]]</strong><script>alert(1)</script></p>',
            'serial_prefix': 'ach 2026!', 'primary_color': '#172554',
            'secondary_color': '#c59d3f', 'text_color': '#1f2937',
            'border_style': 'classic', 'font_family': 'georgia',
            'title_font_size': 38, 'recipient_font_size': 34,
            'body_font_size': 17, 'line_height': '1.60',
            'show_logo': 'on', 'show_issue_date': 'on',
            'show_certificate_number': 'on', 'is_active': 'on', 'is_default': 'on',
        })
        self.assertEqual(response.status_code, 302)
        template = CertificateTemplate.objects.get(org=self.org, name='Achievement 2026')
        self.assertNotIn('<script', template.body_html)
        self.assertIn('text-align:center', template.body_html)
        self.assertEqual(template.serial_prefix, 'ACH2026')

    def test_bulk_certificate_generation_replaces_tokens(self):
        template = self._create_template()
        response = self.client.get(reverse('schooladmin:certificate_generate'), {
            'template': template.pk, 'generate': '1',
            'classification': self.classification.pk,
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual([item.pk for item in response.context['members']], [self.member.pk])
        rendered = str(response.context['members'][0].certificate_body_html)
        self.assertIn('Certificate Recipient', rendered)
        self.assertIn('Grade 12', rendered)
        self.assertIn(self.org.name, rendered)

    def test_certificate_template_is_organization_scoped(self):
        other_org, _ = _make_org_and_admin('CertificateOther')
        other_template = CertificateTemplate.objects.create(
            org=other_org, name='Private Template', certificate_type='custom',
        )
        response = self.client.get(reverse('schooladmin:certificate_generate'), {
            'template': other_template.pk, 'generate': '1',
        })
        self.assertEqual(response.status_code, 404)

    def test_bulk_certificate_excludes_other_organization_members(self):
        template = self._create_template()
        other_org, _ = _make_org_and_admin('CertificateRosterOther')
        member.objects.create(
            org=other_org, name='Outside Recipient', member_type='student', gender='Male',
        )
        response = self.client.get(reverse('schooladmin:certificate_generate'), {
            'template': template.pk, 'generate': '1',
        })
        self.assertEqual([item.name for item in response.context['members']], ['Certificate Recipient'])


class ShiftReportWorkspaceTests(TestCase):
    def setUp(self):
        self.org, self.admin_user = _make_org_and_admin("ShiftReport")
        self.org.feature_hrms = True
        self.org.allowed_features = sorted(set(self.org.allowed_features + ['hrms']))
        self.org.save(update_fields=['feature_hrms', 'allowed_features'])
        self.member = member.objects.create(
            org=self.org,
            name='Shift Member',
            member_type='employee',
            gender='Male',
        )
        self.shift = Shift.objects.create(org=self.org, name='Day Shift')
        ShiftWindow.objects.create(
            shift=self.shift,
            start_time=datetime.time(9, 0),
            end_time=datetime.time(17, 0),
        )
        self.member.shifts.add(self.shift)
        self.client.login(username="adminShiftReport", password="testpass123")

    def test_rejects_unbounded_reporting_range(self):
        response = self.client.get(reverse('schooladmin:shift_report'), {
            'member': self.member.pk,
            'from_date': '2024-01-01',
            'to_date': '2026-01-02',
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'generate at most 367 days')
        self.assertEqual(response.context['days'], [])

    def test_admin_can_configure_mobile_attendance_reminders(self):
        response = self.client.post(reverse('schooladmin:shift_list'), {
            'enabled': 'on',
            'checkin_enabled': 'on',
            'checkout_enabled': 'on',
            'checkin_offsets': '0, 12, 30',
            'checkout_offsets': '0, 20',
        })

        self.assertRedirects(response, reverse('schooladmin:shift_list'))
        policy = AttendanceReminderPolicy.objects.get(org=self.org)
        self.assertTrue(policy.enabled)
        self.assertEqual(policy.checkin_offsets, [0, 12, 30])
        self.assertEqual(policy.checkout_offsets, [0, 20])

    def test_admin_reminder_policy_rejects_invalid_offsets(self):
        response = self.client.post(reverse('schooladmin:shift_list'), {
            'enabled': 'on',
            'checkin_enabled': 'on',
            'checkout_enabled': 'on',
            'checkin_offsets': 'soon',
            'checkout_offsets': '0, 20',
        }, follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            'Reminder offsets must be whole minutes separated by commas.',
        )

    def test_csv_export_is_scoped_to_selected_member(self):
        report_date = timezone.localdate()
        AttendanceRecord.objects.create(
            org=self.org,
            mem=self.member,
            scanned_time=timezone.make_aware(datetime.datetime.combine(
                report_date, datetime.time(9, 0),
            )),
        )
        AttendanceRecord.objects.create(
            org=self.org,
            mem=self.member,
            scanned_time=timezone.make_aware(datetime.datetime.combine(
                report_date, datetime.time(17, 0),
            )),
        )

        response = self.client.get(reverse('schooladmin:shift_report'), {
            'member': self.member.pk,
            'from_date': report_date.isoformat(),
            'to_date': report_date.isoformat(),
            'export': 'csv',
        })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/csv')
        self.assertIn('Shift Member', response.content.decode())


class CourseSubjectTeacherAttendanceTests(TestCase):
    def setUp(self):
        self.org, self.admin_user = _make_org_and_admin("SubjectAttendance")
        self.org.feature_courses = True
        self.org.course_based_attendance = True
        self.org.allowed_features = sorted(set(self.org.allowed_features + ['courses']))
        self.org.save(update_fields=[
            'feature_courses', 'course_based_attendance', 'allowed_features',
        ])
        academic_feature, _ = DynamicFeature.objects.get_or_create(
            key='academic_management',
            defaults={'label': 'Academic Management', 'is_active': True},
        )
        OrganizationFeatureGrant.objects.create(
            org=self.org, feature=academic_feature, enabled=True
        )

        self.teacher_member = member.objects.create(
            org=self.org,
            name="Assigned Teacher",
            member_type="teacher",
            gender="Female",
        )
        self.teacher_user = CustomUser.objects.create_user(
            username="subjectteacher",
            email="subjectteacher@example.com",
            password="testpass123",
            user_type="3",
        )
        Staff.objects.create(
            admin=self.teacher_user,
            org=self.org,
            member=self.teacher_member,
        )
        self.classification = Classification.objects.create(
            org=self.org, name="Grade 8"
        )
        self.section = Section.objects.create(
            org=self.org, classification=self.classification, name="A"
        )
        self.course = Course.objects.create(
            org=self.org, name="BSc Computing", code="BSC-COMP"
        )
        self.course.classifications.add(self.classification)
        self.course.sections.add(self.section)
        self.academic_year = AcademicYear.objects.create(
            org=self.org,
            name="2083/84",
            start_date=datetime.date(2026, 4, 14),
            end_date=datetime.date(2027, 4, 13),
            is_current=True,
        )
        self.subject = Subject.objects.create(
            org=self.org,
            course=self.course,
            classification=self.classification,
            section=self.section,
            name="Programming Fundamentals",
            code="CS101",
            teacher=self.teacher_user,
        )
        SubjectTeacherAssignment.objects.create(
            subject=self.subject,
            teacher=self.teacher_user,
            is_primary=True,
            academic_year=self.academic_year,
        )
        self.assigned_student = member.objects.create(
            org=self.org,
            name="Enrolled Student",
            member_type="student",
            gender="Male",
            classification=self.classification,
            section=self.section,
        )
        self.assigned_student.courses.add(self.course)
        StudentCourseEnrollment.objects.create(
            org=self.org,
            academic_year=self.academic_year,
            student=self.assigned_student,
            course=self.course,
            classification=self.classification,
            section=self.section,
            start_date=datetime.date(2026, 4, 14),
        )
        self.unenrolled_student = member.objects.create(
            org=self.org,
            name="Not Enrolled",
            member_type="student",
            gender="Female",
            classification=self.classification,
            section=self.section,
        )

    def test_course_page_leads_to_subject_management(self):
        client = Client()
        client.login(username="adminSubjectAttendance", password="testpass123")
        response = client.get(reverse('schooladmin:course_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            f"{reverse('schooladmin:subject_list')}?course={self.course.pk}",
        )
        self.assertNotContains(response, "Assign Course Attendance Staff")

    def test_admin_cannot_assign_other_org_teacher_to_subject(self):
        other_org, _ = _make_org_and_admin("SubjectAttendanceOther")
        other_member = member.objects.create(
            org=other_org, name="Other Teacher", member_type="teacher", gender="Male"
        )
        other_user = CustomUser.objects.create_user(
            username="othercourseteacher",
            email="othercourseteacher@example.com",
            password="testpass123",
            user_type="3",
        )
        Staff.objects.create(admin=other_user, org=other_org, member=other_member)

        client = Client()
        client.login(username="adminSubjectAttendance", password="testpass123")
        client.post(
            reverse('schooladmin:subject_teachers', args=(self.subject.pk,)),
            {'action': 'add', 'teacher': other_user.pk},
        )
        self.assertFalse(SubjectTeacherAssignment.objects.filter(
            subject=self.subject, teacher=other_user
        ).exists())

    def test_admin_creates_subject_inside_course_and_assigns_teacher(self):
        client = Client()
        client.login(username="adminSubjectAttendance", password="testpass123")
        response = client.post(reverse('schooladmin:subject_list'), {
            'action': 'add',
            'course': self.course.pk,
            'classification': self.classification.pk,
            'section': self.section.pk,
            'name': 'Database Systems',
            'code': 'CS202',
            'teacher': self.teacher_user.pk,
            'full_marks': '100',
            'pass_marks': '40',
            'status': 'active',
        })
        self.assertEqual(response.status_code, 302)
        created = Subject.objects.get(org=self.org, code='CS202')
        self.assertEqual(created.course, self.course)
        self.assertEqual(created.classification, self.classification)
        self.assertEqual(created.section, self.section)
        self.assertTrue(SubjectTeacherAssignment.objects.filter(
            subject=created, teacher=self.teacher_user
        ).exists())

    def test_subject_rejects_classification_outside_course(self):
        other_class = Classification.objects.create(
            org=self.org, name="Grade 9"
        )
        client = Client()
        client.login(username="adminSubjectAttendance", password="testpass123")
        client.post(reverse('schooladmin:subject_list'), {
            'action': 'add',
            'course': self.course.pk,
            'classification': other_class.pk,
            'name': 'Invalid Subject',
            'full_marks': '100',
            'pass_marks': '40',
        })
        self.assertFalse(Subject.objects.filter(
            org=self.org, name='Invalid Subject'
        ).exists())

    def test_teacher_sees_only_assigned_subjects(self):
        other_subject = Subject.objects.create(
            org=self.org,
            course=self.course,
            classification=self.classification,
            section=self.section,
            name="Unassigned Networks",
        )
        client = Client()
        client.login(username="subjectteacher", password="testpass123")
        response = client.get(reverse('staff:subject_teaching_log'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.subject.name)
        self.assertNotContains(response, other_subject.name)

    def test_course_less_subject_assignment_supports_dashboard_form_api_and_attendance(self):
        course_less = Subject.objects.create(
            org=self.org,
            classification=self.classification,
            section=self.section,
            name="Course-less Computer",
            teacher=self.teacher_user,
        )
        SubjectTeacherAssignment.objects.create(
            subject=course_less,
            teacher=self.teacher_user,
            academic_year=self.academic_year,
            is_primary=True,
        )
        self.teacher_member.classification = self.classification
        self.teacher_member.section = self.section
        self.teacher_member.save(update_fields=['classification', 'section'])

        client = Client()
        client.login(username="subjectteacher", password="testpass123")

        dashboard = client.get(reverse('staff:dashboard'))
        self.assertEqual(dashboard.status_code, 200)
        self.assertContains(dashboard, course_less.name)
        self.assertEqual(dashboard.context['teacher_assigned_subject_count'], 2)
        self.assertEqual(dashboard.context['teacher_assigned_course_count'], 1)

        form_page = client.get(reverse('staff:subject_teaching_log'), {
            'subject': course_less.pk,
            'classification': self.classification.pk,
            'section': self.section.pk,
        })
        self.assertEqual(form_page.status_code, 200)
        self.assertContains(form_page, course_less.name)
        self.assertNotContains(form_page, "No active subject is assigned to you")
        roster_ids = set(form_page.context['manual_roster'].values_list('pk', flat=True))
        self.assertEqual(
            roster_ids,
            {self.assigned_student.pk, self.unenrolled_student.pk},
        )

        submitted = client.post(reverse('staff:subject_teaching_log'), {
            'subject': course_less.pk,
            'classification': self.classification.pk,
            'section': self.section.pk,
            'academic_year': self.academic_year.pk,
            'date': timezone.localdate().isoformat(),
            'period': '4',
            'topic_covered': 'Computer basics',
            f'status_{self.assigned_student.pk}': 'present',
            f'status_{self.unenrolled_student.pk}': 'late',
        })
        self.assertEqual(submitted.status_code, 302)
        log = TeachingLog.objects.get(
            org=self.org, subject=course_less, period=4,
        )
        self.assertIsNone(log.course)
        self.assertTrue(SubjectAttendanceRecord.objects.filter(
            teaching_log=log, member=self.assigned_student, status='present',
        ).exists())
        self.assertTrue(SubjectAttendanceRecord.objects.filter(
            teaching_log=log, member=self.unenrolled_student, status='late',
        ).exists())
        log.status = 'approved'
        log.save(update_fields=['status'])

        auth = f"Bearer {RefreshToken.for_user(self.teacher_user).access_token}"
        assignments = client.get(
            reverse('staff:api_my_subject_assignments'),
            HTTP_AUTHORIZATION=auth,
        )
        self.assertEqual(assignments.status_code, 200)
        api_assignment = next(
            row for row in assignments.json()['results']
            if row['subject']['id'] == course_less.pk
        )
        self.assertIsNone(api_assignment['course'])

        api_roster = client.get(
            reverse('staff:api_assigned_subject_roster', args=(course_less.pk,)),
            HTTP_AUTHORIZATION=auth,
        )
        self.assertEqual(api_roster.status_code, 200)
        self.assertIsNone(api_roster.json()['subject']['course'])
        self.assertEqual(
            {row['id'] for row in api_roster.json()['students']},
            {self.assigned_student.pk, self.unenrolled_student.pk},
        )

        student_user = CustomUser.objects.create_user(
            username="courselessstudent",
            email="courselessstudent@example.com",
            password="testpass123",
            user_type="3",
        )
        Staff.objects.create(
            admin=student_user,
            org=self.org,
            member=self.assigned_student,
        )
        student_client = Client()
        student_client.login(username="courselessstudent", password="testpass123")
        student_dashboard = student_client.get(reverse('staff:dashboard'))
        self.assertEqual(student_dashboard.status_code, 200)
        self.assertContains(student_dashboard, course_less.name)
        student_report = student_client.get(
            reverse('staff:student_subject_attendance'),
        )
        self.assertEqual(student_report.status_code, 200)
        self.assertContains(student_report, course_less.name)

    def test_routine_accepts_assigned_subject_without_course(self):
        from handle.forms import RoutinePeriodForm

        course_less = Subject.objects.create(
            org=self.org,
            classification=self.classification,
            section=self.section,
            name="Course-less Routine Subject",
        )
        assignment = SubjectTeacherAssignment.objects.create(
            subject=course_less,
            teacher=self.teacher_user,
            academic_year=self.academic_year,
        )
        form = RoutinePeriodForm(data={
            'teacher_assignment': assignment.pk,
            'day_of_week': 1,
            'period_number': 2,
            'start_time': '10:00',
            'end_time': '11:00',
            'room': 'R-2',
            'shift': 'day',
            'is_active': 'on',
        }, org=self.org)
        self.assertTrue(form.is_valid(), form.errors.as_json())
        period = form.save(commit=False)
        period.org = self.org
        period.save()
        self.assertEqual(period.subject, course_less)
        self.assertEqual(period.teacher_assignment.subject, course_less)

    def test_routine_creation_uses_assignment_hierarchy_and_weekly_grid(self):
        assignment = SubjectTeacherAssignment.objects.get(
            subject=self.subject,
            teacher=self.teacher_user,
        )
        client = Client()
        client.login(username="adminSubjectAttendance", password="testpass123")
        form_page = client.get(reverse('schooladmin:add_routine_period'))
        self.assertEqual(form_page.status_code, 200)
        self.assertContains(form_page, "Choose the assigned teaching scope")
        self.assertContains(form_page, "Assigned Teacher / Subject")

        created = client.post(reverse('schooladmin:add_routine_period'), {
            'teacher_assignment': assignment.pk,
            'day_of_week': 2,
            'period_number': 3,
            'start_time': '11:00',
            'end_time': '12:00',
            'room': 'Lab 1',
            'shift': 'day',
            'is_active': 'on',
            # These forged legacy fields are intentionally ignored.
            'classification': '',
            'subject': '',
            'teacher': self.admin_user.pk,
        })
        self.assertRedirects(
            created,
            reverse('schooladmin:routine_grid'),
            fetch_redirect_response=False,
        )
        period = RoutinePeriod.objects.get(
            org=self.org, period_number=3, day_of_week=2,
        )
        self.assertEqual(period.teacher_assignment, assignment)
        self.assertEqual(period.teacher, self.teacher_user)
        self.assertEqual(period.subject, self.subject)
        self.assertEqual(period.classification, self.classification)
        self.assertEqual(period.section, self.section)
        self.assertEqual(period.academic_year, self.academic_year)

        grid = client.get(reverse('schooladmin:routine_grid'))
        self.assertEqual(grid.status_code, 200)
        self.assertContains(grid, "Weekly Class Routine")
        self.assertContains(grid, self.subject.name)
        self.assertContains(grid, "Lab 1")
        self.assertEqual(grid.context['period_count'], 1)

        duplicate = client.post(reverse('schooladmin:add_routine_period'), {
            'teacher_assignment': assignment.pk,
            'day_of_week': 2,
            'period_number': 3,
            'start_time': '13:00',
            'end_time': '14:00',
            'room': 'Lab 2',
            'shift': 'day',
            'is_active': 'on',
        })
        self.assertEqual(duplicate.status_code, 200)
        self.assertContains(
            duplicate,
            "already has a routine for that day and period number",
        )
        self.assertEqual(RoutinePeriod.objects.filter(org=self.org).count(), 1)

    def test_multi_day_routine_create_makes_one_period_per_selected_day(self):
        assignment = SubjectTeacherAssignment.objects.get(
            subject=self.subject, teacher=self.teacher_user,
        )
        client = Client()
        client.login(username="adminSubjectAttendance", password="testpass123")

        response = client.post(reverse('schooladmin:add_routine_period'), {
            'teacher_assignment': assignment.pk,
            'days': ['0', '1', '3'],
            'period_number': 4,
            'start_time': '09:00',
            'end_time': '10:00',
            'room': 'Lab 3',
            'shift': 'day',
            'is_active': 'on',
        })
        self.assertRedirects(
            response, reverse('schooladmin:routine_grid'), fetch_redirect_response=False,
        )
        created_days = set(
            RoutinePeriod.objects.filter(
                org=self.org, period_number=4, room='Lab 3',
            ).values_list('day_of_week', flat=True)
        )
        self.assertEqual(created_days, {0, 1, 3})

    def test_multi_day_routine_create_skips_conflicting_day_only(self):
        assignment = SubjectTeacherAssignment.objects.get(
            subject=self.subject, teacher=self.teacher_user,
        )
        # Pre-existing period that only conflicts on Monday (day_of_week=1).
        RoutinePeriod.objects.create(
            org=self.org, classification=self.classification, section=self.section,
            subject=self.subject, teacher=self.teacher_user,
            teacher_assignment=assignment, academic_year=self.academic_year,
            day_of_week=1, period_number=5,
            start_time=datetime.time(11, 0), end_time=datetime.time(12, 0),
        )
        client = Client()
        client.login(username="adminSubjectAttendance", password="testpass123")

        response = client.post(reverse('schooladmin:add_routine_period'), {
            'teacher_assignment': assignment.pk,
            'days': ['1', '2'],
            'period_number': 5,
            'start_time': '11:00',
            'end_time': '12:00',
            'room': 'Lab 4',
            'shift': 'day',
            'is_active': 'on',
        })
        self.assertRedirects(
            response, reverse('schooladmin:routine_grid'), fetch_redirect_response=False,
        )
        # Monday was already booked for this class/period -> left empty (skipped).
        self.assertFalse(RoutinePeriod.objects.filter(
            org=self.org, period_number=5, day_of_week=1, room='Lab 4',
        ).exists())
        # Tuesday had no conflict -> created normally.
        self.assertTrue(RoutinePeriod.objects.filter(
            org=self.org, period_number=5, day_of_week=2, room='Lab 4',
        ).exists())

    def test_add_routine_form_prefills_day_and_period_from_query_params(self):
        client = Client()
        client.login(username="adminSubjectAttendance", password="testpass123")
        response = client.get(
            reverse('schooladmin:add_routine_period'), {'day': '3', 'period': '6'},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn('3', response.context['preselected_days'])
        self.assertEqual(response.context['form'].initial.get('period_number'), '6')

    def test_routine_grid_links_empty_cell_to_add_and_card_to_edit(self):
        assignment = SubjectTeacherAssignment.objects.get(
            subject=self.subject, teacher=self.teacher_user,
        )
        period = RoutinePeriod.objects.create(
            org=self.org, classification=self.classification, section=self.section,
            subject=self.subject, teacher=self.teacher_user,
            teacher_assignment=assignment, academic_year=self.academic_year,
            day_of_week=2, period_number=7,
            start_time=datetime.time(9, 0), end_time=datetime.time(10, 0),
        )
        client = Client()
        client.login(username="adminSubjectAttendance", password="testpass123")
        response = client.get(reverse('schooladmin:routine_grid'))
        self.assertEqual(response.status_code, 200)
        add_url = reverse('schooladmin:add_routine_period')
        edit_url = reverse('schooladmin:edit_routine_period', args=(period.pk,))
        self.assertContains(response, f'{add_url}?day=')
        self.assertContains(response, f"location.href='{edit_url}'")

    def test_teacher_dashboard_and_weekly_routine_show_class_reminder(self):
        assignment = SubjectTeacherAssignment.objects.get(
            subject=self.subject,
            teacher=self.teacher_user,
        )
        weekday = (timezone.localdate().weekday() + 1) % 7
        period = RoutinePeriod.objects.create(
            org=self.org,
            academic_year=self.academic_year,
            classification=self.classification,
            section=self.section,
            subject=self.subject,
            teacher=self.teacher_user,
            teacher_assignment=assignment,
            day_of_week=weekday,
            period_number=1,
            start_time=datetime.time(0, 0),
            end_time=datetime.time(23, 59),
            room='Classroom A',
        )
        client = Client()
        client.login(username="subjectteacher", password="testpass123")

        dashboard = client.get(reverse('staff:dashboard'))
        self.assertEqual(dashboard.status_code, 200)
        self.assertContains(dashboard, "Routine Reminder")
        self.assertContains(dashboard, "Class is running")
        self.assertEqual(
            dashboard.context['teacher_routine_reminder'].pk,
            period.pk,
        )
        self.assertEqual(
            dashboard.context['teacher_routine_reminder'].reminder_state,
            'live',
        )

        weekly = client.get(reverse('staff:teacher_routine'))
        self.assertEqual(weekly.status_code, 200)
        self.assertContains(weekly, "My Assigned Class Routine")
        self.assertContains(weekly, self.subject.name)
        self.assertContains(weekly, "Classroom A")

        TeachingLog.objects.create(
            org=self.org,
            academic_year=self.academic_year,
            course=self.course,
            teacher=self.teacher_user,
            teacher_assignment=assignment,
            routine_period=period,
            subject=self.subject,
            classification=self.classification,
            section=self.section,
            date=timezone.localdate(),
            period=1,
            topic_covered='Routine reminder lesson',
            status='submitted',
        )
        completed_dashboard = client.get(reverse('staff:dashboard'))
        self.assertEqual(
            completed_dashboard.context['teacher_routine_reminder'].reminder_state,
            'completed',
        )
        self.assertContains(completed_dashboard, "Attendance submitted")

    def test_section_neutral_subject_can_be_assigned_per_section(self):
        from handle.forms import RoutinePeriodForm

        section_b = Section.objects.create(
            org=self.org,
            classification=self.classification,
            name="B",
        )
        neutral_subject = Subject.objects.create(
            org=self.org,
            course=self.course,
            classification=self.classification,
            name="Section-neutral Mathematics",
        )
        assignment_a = SubjectTeacherAssignment.objects.create(
            subject=neutral_subject,
            teacher=self.teacher_user,
            academic_year=self.academic_year,
            section=self.section,
        )
        assignment_b = SubjectTeacherAssignment.objects.create(
            subject=neutral_subject,
            teacher=self.teacher_user,
            academic_year=self.academic_year,
            section=section_b,
            start_date=timezone.localdate() + datetime.timedelta(days=1),
        )
        self.assertEqual(assignment_a.section, self.section)
        self.assertEqual(assignment_b.section, section_b)

        form = RoutinePeriodForm(data={
            'teacher_assignment': assignment_a.pk,
            'day_of_week': 4,
            'period_number': 2,
            'start_time': '09:00',
            'end_time': '09:45',
            'shift': 'morning',
            'is_active': 'on',
        }, org=self.org)
        self.assertTrue(form.is_valid(), form.errors.as_json())
        period = form.save(commit=False)
        period.org = self.org
        period.save()
        self.assertEqual(period.section, self.section)

    def test_teacher_assigns_student_work_and_grades_submission(self):
        student_user = CustomUser.objects.create_user(
            username="assignmentstudent",
            email="assignmentstudent@example.com",
            password="testpass123",
            user_type="3",
        )
        Staff.objects.create(
            admin=student_user,
            org=self.org,
            member=self.assigned_student,
        )
        scope = SubjectTeacherAssignment.objects.get(
            subject=self.subject,
            teacher=self.teacher_user,
        )
        teacher_client = Client()
        teacher_client.login(username="subjectteacher", password="testpass123")

        homework_response = teacher_client.post(
            reverse('staff:teacher_homework_create'),
            {
                'teaching_scope': scope.pk,
                'description': 'Complete chapter one practice.',
                'due_date': (timezone.localdate() + datetime.timedelta(days=2)).isoformat(),
                'priority': 'high',
                'estimated_time_minutes': '30',
                'frequency': 'one_time',
                'status': 'active',
            },
        )
        self.assertEqual(homework_response.status_code, 302)
        homework = Homework.objects.get(
            org=self.org,
            assigned_by=self.teacher_user,
        )
        self.assertEqual(homework.teacher_assignment, scope)
        self.assertTrue(HomeworkStatus.objects.filter(
            homework=homework,
            student=self.assigned_student,
        ).exists())
        self.assertFalse(HomeworkStatus.objects.filter(
            homework=homework,
            student=self.unenrolled_student,
        ).exists())

        assignment_response = teacher_client.post(
            reverse('staff:teacher_assignment_create'),
            {
                'teaching_scope': scope.pk,
                'title': 'Programming Practice',
                'description': 'Solve the practice set.',
                'instructions': 'Show your working.',
                'start_date': timezone.localdate().isoformat(),
                'due_date': (timezone.localdate() + datetime.timedelta(days=5)).isoformat(),
                'total_marks': '25',
                'passing_marks': '10',
                'visibility': 'published',
                'status': 'open',
            },
        )
        self.assertEqual(assignment_response.status_code, 302)
        assignment = Assignment.objects.get(
            org=self.org,
            title='Programming Practice',
        )
        self.assertEqual(assignment.teacher_assignment, scope)

        student_client = Client()
        student_client.login(username="assignmentstudent", password="testpass123")
        student_dashboard = student_client.get(reverse('staff:dashboard'))
        self.assertContains(student_dashboard, "Assignments Due")
        assignment_list = student_client.get(reverse('staff:student_assignments'))
        self.assertContains(assignment_list, assignment.title)
        submitted = student_client.post(
            reverse('staff:assignment_submit', args=(assignment.pk,)),
            {'student_comments': 'My completed work.'},
        )
        self.assertEqual(submitted.status_code, 302)
        submission = AssignmentSubmission.objects.get(
            assignment=assignment,
            student=self.assigned_student,
        )

        graded = teacher_client.post(
            reverse('staff:teacher_assignment_detail', args=(assignment.pk,)),
            {
                'submission_id': submission.pk,
                'obtained_marks': '20',
                'teacher_remarks': 'Good work.',
                'status': 'graded',
            },
        )
        self.assertEqual(graded.status_code, 302)
        submission.refresh_from_db()
        self.assertEqual(submission.obtained_marks, Decimal('20'))
        self.assertEqual(submission.status, 'graded')

    def test_teacher_sees_only_assigned_exam_subject_and_validated_roster(self):
        self.org.feature_results = True
        self.org.allowed_features = sorted(
            set(self.org.allowed_features + ['results'])
        )
        self.org.save(update_fields=['feature_results', 'allowed_features'])
        exam = ExamTerm.objects.create(
            org=self.org,
            classification=self.classification,
            section=self.section,
            name='Subject Scoped Terminal Exam',
            start_date=timezone.localdate(),
            end_date=timezone.localdate() + datetime.timedelta(days=3),
            status='marks_entry',
        )
        scope = SubjectTeacherAssignment.objects.get(
            subject=self.subject,
            teacher=self.teacher_user,
        )
        client = Client()
        client.login(username="subjectteacher", password="testpass123")
        exam_list = client.get(reverse('staff:teacher_exams'))
        self.assertEqual(exam_list.status_code, 200)
        self.assertContains(exam_list, exam.name)
        self.assertContains(exam_list, self.subject.name)

        marks_page = client.get(
            reverse(
                'staff:teacher_exam_marks',
                args=(exam.pk, scope.pk),
            )
        )
        self.assertEqual(marks_page.status_code, 200)
        self.assertContains(marks_page, self.assigned_student.name)
        self.assertNotContains(marks_page, self.unenrolled_student.name)

        saved = client.post(
            reverse(
                'staff:teacher_exam_marks',
                args=(exam.pk, scope.pk),
            ),
            {
                f'marks_{self.assigned_student.pk}': '78',
                f'marks_{self.unenrolled_student.pk}': '99',
            },
        )
        self.assertEqual(saved.status_code, 302)
        self.assertTrue(ResultRecord.objects.filter(
            exam=exam,
            subject=self.subject,
            student=self.assigned_student,
            obtained_marks=Decimal('78'),
        ).exists())
        self.assertFalse(ResultRecord.objects.filter(
            exam=exam,
            student=self.unenrolled_student,
        ).exists())

    def test_manual_subject_attendance_uses_course_enrollment(self):
        client = Client()
        client.login(username="subjectteacher", password="testpass123")
        response = client.post(reverse('staff:subject_teaching_log'), {
            'routine_period': '',
            'subject': self.subject.pk,
            'classification': self.classification.pk,
            'section': self.section.pk,
            'date': timezone.localdate().isoformat(),
            'period': '1',
            'topic_covered': 'Variables and data types',
            f'present_{self.assigned_student.pk}': 'on',
            f'present_{self.unenrolled_student.pk}': 'on',
        })
        self.assertEqual(response.status_code, 302)
        log = TeachingLog.objects.get(
            org=self.org, teacher=self.teacher_user, subject=self.subject
        )
        self.assertTrue(SubjectAttendanceRecord.objects.filter(
            teaching_log=log, member=self.assigned_student, status='present'
        ).exists())
        self.assertFalse(SubjectAttendanceRecord.objects.filter(
            teaching_log=log, member=self.unenrolled_student
        ).exists())

    def test_teacher_cannot_submit_unassigned_subject(self):
        unassigned = Subject.objects.create(
            org=self.org,
            course=self.course,
            classification=self.classification,
            section=self.section,
            name="Private Networks",
        )
        client = Client()
        client.login(username="subjectteacher", password="testpass123")
        client.post(reverse('staff:subject_teaching_log'), {
            'subject': unassigned.pk,
            'classification': self.classification.pk,
            'section': self.section.pk,
            'date': timezone.localdate().isoformat(),
            'topic_covered': 'Forged topic',
        })
        self.assertFalse(TeachingLog.objects.filter(
            org=self.org, teacher=self.teacher_user, subject=unassigned
        ).exists())

    def test_legacy_course_attendance_url_redirects_to_subject_flow(self):
        client = Client()
        client.login(username="subjectteacher", password="testpass123")
        response = client.get(reverse('staff:teaching_log'))
        self.assertRedirects(
            response,
            reverse('staff:subject_teaching_log'),
            fetch_redirect_response=False,
        )

    def test_admin_dashboard_shows_academic_hierarchy_counts(self):
        client = Client()
        client.login(username="adminSubjectAttendance", password="testpass123")
        response = client.get(reverse('schooladmin:dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Academic Control Center")
        self.assertEqual(response.context['academic_course_count'], 1)
        self.assertEqual(response.context['academic_enrollment_count'], 1)
        self.assertEqual(response.context['academic_active_assignment_count'], 1)

    def test_teacher_dashboard_uses_active_subject_assignments(self):
        client = Client()
        client.login(username="subjectteacher", password="testpass123")
        response = client.get(reverse('staff:dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "My Teaching Dashboard")
        self.assertContains(response, self.subject.name)
        self.assertEqual(response.context['teacher_assigned_subject_count'], 1)
        self.assertEqual(response.context['teacher_roster_student_count'], 1)
        report = client.get(reverse('staff:teacher_subject_attendance_report'))
        self.assertEqual(report.status_code, 200)

    def test_deactivated_assignment_revokes_teacher_attendance_access(self):
        assignment = SubjectTeacherAssignment.objects.get(
            subject=self.subject, teacher=self.teacher_user,
        )
        assignment.status = 'inactive'
        assignment.end_date = datetime.date(2026, 7, 27)
        assignment.save()

        client = Client()
        client.login(username="subjectteacher", password="testpass123")
        client.post(reverse('staff:subject_teaching_log'), {
            'subject': self.subject.pk,
            'classification': self.classification.pk,
            'section': self.section.pk,
            'date': timezone.localdate().isoformat(),
            'period': '2',
            'topic_covered': 'Forged after deactivation',
        })
        self.assertFalse(TeachingLog.objects.filter(
            org=self.org, topic_covered='Forged after deactivation',
        ).exists())

    def test_student_dashboard_and_subject_report_are_student_scoped(self):
        student_user = CustomUser.objects.create_user(
            username="enrolledstudent",
            email="enrolledstudent@example.com",
            password="testpass123",
            user_type="3",
        )
        Staff.objects.create(
            admin=student_user, org=self.org, member=self.assigned_student,
        )
        other_course = Course.objects.create(org=self.org, name="MBBS")
        other_course.classifications.add(self.classification)
        other_course.sections.add(self.section)
        other_subject = Subject.objects.create(
            org=self.org, course=other_course,
            classification=self.classification, section=self.section,
            name="Anatomy",
        )
        weekday = (datetime.date.today().weekday() + 1) % 7
        RoutinePeriod.objects.create(
            org=self.org,
            academic_year=self.academic_year,
            classification=self.classification,
            section=self.section,
            subject=self.subject,
            teacher=self.teacher_user,
            day_of_week=weekday,
            period_number=1,
            start_time=datetime.time(9, 0),
            end_time=datetime.time(10, 0),
        )
        RoutinePeriod.objects.create(
            org=self.org,
            academic_year=self.academic_year,
            classification=self.classification,
            section=self.section,
            subject=other_subject,
            teacher=self.teacher_user,
            day_of_week=weekday,
            period_number=2,
            start_time=datetime.time(10, 0),
            end_time=datetime.time(11, 0),
        )
        log = TeachingLog.objects.create(
            org=self.org,
            academic_year=self.academic_year,
            course=self.course,
            teacher=self.teacher_user,
            subject=self.subject,
            classification=self.classification,
            section=self.section,
            date=datetime.date.today(),
            period=1,
            topic_covered="Variables",
            status='approved',
        )
        SubjectAttendanceRecord.objects.create(
            org=self.org,
            teaching_log=log,
            member=self.assigned_student,
            status='late',
            marked_by=self.teacher_user,
        )

        client = Client()
        client.login(username="enrolledstudent", password="testpass123")
        dashboard = client.get(reverse('staff:dashboard'))
        self.assertEqual(dashboard.status_code, 200)
        self.assertContains(dashboard, self.subject.name)
        self.assertNotContains(dashboard, other_subject.name)
        self.assertEqual(len(dashboard.context['todays_classes']), 1)

        report = client.get(reverse('staff:student_subject_attendance'))
        self.assertEqual(report.status_code, 200)
        self.assertContains(report, self.subject.name)
        self.assertContains(report, "Late")
        self.assertEqual(report.context['total'], 1)
        teacher_page = client.get(reverse('staff:subject_teaching_log'))
        self.assertRedirects(
            teacher_page, reverse('staff:dashboard'),
            fetch_redirect_response=False,
        )

    def test_teacher_subject_attendance_api_is_scoped_and_idempotent(self):
        client = Client()
        anonymous = client.get(reverse('staff:api_my_subject_assignments'))
        self.assertEqual(anonymous.status_code, 401)
        auth = f"Bearer {RefreshToken.for_user(self.teacher_user).access_token}"

        assignments = client.get(
            reverse('staff:api_my_subject_assignments'),
            HTTP_AUTHORIZATION=auth,
        )
        self.assertEqual(assignments.status_code, 200)
        self.assertEqual(len(assignments.json()['results']), 1)
        self.assertEqual(
            assignments.json()['results'][0]['subject']['id'], self.subject.pk,
        )

        roster = client.get(
            reverse('staff:api_assigned_subject_roster', args=(self.subject.pk,)),
            HTTP_AUTHORIZATION=auth,
        )
        self.assertEqual(roster.status_code, 200)
        roster_ids = {row['id'] for row in roster.json()['students']}
        self.assertIn(self.assigned_student.pk, roster_ids)
        self.assertNotIn(self.unenrolled_student.pk, roster_ids)

        payload = {
            'subject': self.subject.pk,
            'classification': self.classification.pk,
            'section': self.section.pk,
            'academic_year': self.academic_year.pk,
            'date': timezone.localdate().isoformat(),
            'period': 3,
            'topic_covered': 'API lesson',
            'attendance': [
                {'student_id': self.assigned_student.pk, 'status': 'late'},
                {'student_id': self.unenrolled_student.pk, 'status': 'present'},
            ],
        }
        first = client.post(
            reverse('staff:api_submit_subject_attendance'),
            data=json.dumps(payload),
            content_type='application/json',
            HTTP_AUTHORIZATION=auth,
        )
        self.assertEqual(first.status_code, 200)
        second = client.post(
            reverse('staff:api_submit_subject_attendance'),
            data=json.dumps(payload),
            content_type='application/json',
            HTTP_AUTHORIZATION=auth,
        )
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first.json()['id'], second.json()['id'])
        self.assertEqual(TeachingLog.objects.filter(
            org=self.org, subject=self.subject, period=3,
        ).count(), 1)
        log = TeachingLog.objects.get(pk=first.json()['id'])
        self.assertTrue(SubjectAttendanceRecord.objects.filter(
            teaching_log=log, member=self.assigned_student, status='late',
        ).exists())
        self.assertFalse(SubjectAttendanceRecord.objects.filter(
            teaching_log=log, member=self.unenrolled_student,
        ).exists())


class EnterpriseVsEducationUITests(TestCase):
    """Phase 3: Student Management views must enforce `feature_student_mgmt`
    at the view level (item 24 — "Do not only hide menu links"), and the
    terminology helper must swap labels based on it."""

    def setUp(self):
        self.school_org = Organization.objects.create(
            name='School Org', category='school',
            expire_on=timezone.now() + datetime.timedelta(days=30),
            feature_student_mgmt=True, feature_courses=True,
        )
        self.school_org.allowed_features = sorted(set(self.school_org.allowed_features + ['student_mgmt', 'courses']))
        self.school_org.save(update_fields=['allowed_features'])
        self.school_admin = CustomUser.objects.create_user(
            username='school-admin', email='school-admin@example.com',
            password='testpass123', user_type='2',
        )
        Schooladmin.objects.create(admin=self.school_admin, org=self.school_org)

        self.office_org = Organization.objects.create(
            name='Office Org', category='office',
            expire_on=timezone.now() + datetime.timedelta(days=30),
            feature_student_mgmt=False, feature_courses=False,
        )
        self.office_admin = CustomUser.objects.create_user(
            username='office-admin', email='office-admin@example.com',
            password='testpass123', user_type='2',
        )
        Schooladmin.objects.create(admin=self.office_admin, org=self.office_org)

    def test_student_list_blocked_without_student_mgmt_feature(self):
        self.client.force_login(self.office_admin)
        response = self.client.get(reverse('schooladmin:student_list'))
        self.assertEqual(response.status_code, 403)

    def test_student_list_allowed_with_student_mgmt_feature(self):
        self.client.force_login(self.school_admin)
        response = self.client.get(reverse('schooladmin:student_list'))
        self.assertEqual(response.status_code, 200)

    def test_student_add_edit_blocked_without_feature(self):
        self.client.force_login(self.office_admin)
        response = self.client.get(reverse('schooladmin:student_add'))
        self.assertEqual(response.status_code, 403)

    def test_terms_are_office_flavoured_for_office_org(self):
        from school.terminology import get_terms
        terms = get_terms(self.office_org)
        self.assertEqual(terms['classification'], 'Department')
        self.assertEqual(terms['section'], 'Team')

    def test_terms_are_school_flavoured_for_school_org(self):
        from school.terminology import get_terms
        terms = get_terms(self.school_org)
        self.assertEqual(terms['classification'], 'Class')
        self.assertEqual(terms['section'], 'Section')

    def test_classification_hub_hides_course_tab_for_office_org(self):
        self.client.force_login(self.office_admin)
        response = self.client.get(reverse('handle:addClassification'))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'id="tab-course"')
        self.assertContains(response, 'Department')

    def test_classification_hub_shows_course_tab_for_school_org(self):
        self.client.force_login(self.school_admin)
        response = self.client.get(reverse('handle:addClassification'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="tab-course"')
        self.assertContains(response, 'Add Class')

    def test_add_course_rejected_server_side_for_office_org(self):
        from handle.models import Classification
        self.client.force_login(self.office_admin)
        classi = Classification.objects.create(org=self.office_org, name='Dept A')
        response = self.client.post(reverse('handle:addClassification'), {
            'add_course': '1', 'name': 'Sneaky Course', 'classifications': [classi.id],
        })
        self.assertEqual(response.status_code, 302)
        from handle.models import Course
        self.assertFalse(Course.objects.filter(org=self.office_org, name='Sneaky Course').exists())


class DutyRosterTests(TestCase):
    """Phase 4: TemporaryShiftAssignment (Duty Roster) — a date-range change
    that REPLACES the regular pattern, unlike MemberShiftOverride which only
    ever adds an extra shift on top of it."""

    def setUp(self):
        self.org, self.admin_user = _make_org_and_admin("DutyRoster")
        self.org.feature_hrms = True
        self.org.allowed_features = sorted(set(self.org.allowed_features + ['hrms']))
        self.org.save(update_fields=['feature_hrms', 'allowed_features'])

        self.day_shift = Shift.objects.create(org=self.org, name='Day Shift')
        ShiftWindow.objects.create(shift=self.day_shift, start_time=datetime.time(9, 0), end_time=datetime.time(17, 0))
        self.night_shift = Shift.objects.create(org=self.org, name='Night Shift')
        ShiftWindow.objects.create(shift=self.night_shift, start_time=datetime.time(21, 0), end_time=datetime.time(5, 0))

        # Shift-Management member: normally on Day Shift every day.
        self.sm_member = member.objects.create(org=self.org, name='Weekday Worker', gender='Male')
        for weekday in range(7):
            MemberWeekdayShift.objects.create(org=self.org, member=self.sm_member, weekday=weekday, shift=self.day_shift)

        # Plain-default member: never touched Shift Management at all.
        self.plain_member = member.objects.create(
            org=self.org, name='Plain Default Worker', gender='Male',
            shift_start_time=datetime.time(9, 0), shift_end_time=datetime.time(17, 0),
        )
        self.client.login(username="adminDutyRoster", password="testpass123")

    def test_temporary_assignment_replaces_shift_management_pattern(self):
        from handle.models import TemporaryShiftAssignment
        target = datetime.date(2026, 3, 10)
        # Before: resolves to the normal Day Shift pattern.
        self.assertEqual([s.id for s in self.sm_member.active_shifts(target)], [self.day_shift.id])

        TemporaryShiftAssignment.objects.create(
            org=self.org, member=self.sm_member, start_date=target, end_date=target, shift=self.night_shift,
        )
        self.assertEqual([s.id for s in self.sm_member.active_shifts(target)], [self.night_shift.id])
        windows = self.sm_member.shift_windows_detailed(target)
        self.assertEqual(windows[0]['start_time'], datetime.time(21, 0))

    def test_temporary_off_assignment_overrides_plain_default_member(self):
        """The bug this closes: a plain-default member (no MemberWeekdayShift
        rows at all) must still show as off when a Duty Roster change marks
        them off — not silently fall back to their normal shift_start_time."""
        from handle.models import TemporaryShiftAssignment
        target = datetime.date(2026, 3, 10)
        self.assertTrue(self.plain_member.shift_windows_detailed(target))  # normally has a window

        TemporaryShiftAssignment.objects.create(
            org=self.org, member=self.plain_member, start_date=target, end_date=target, shift=None,
        )
        self.assertEqual(self.plain_member.active_shifts(target), [])
        self.assertEqual(self.plain_member.shift_windows_detailed(target), [])

    def test_assignment_only_applies_within_its_date_range(self):
        from handle.models import TemporaryShiftAssignment
        TemporaryShiftAssignment.objects.create(
            org=self.org, member=self.sm_member,
            start_date=datetime.date(2026, 3, 10), end_date=datetime.date(2026, 3, 12),
            shift=self.night_shift,
        )
        self.assertEqual(
            [s.id for s in self.sm_member.active_shifts(datetime.date(2026, 3, 9))], [self.day_shift.id],
        )
        self.assertEqual(
            [s.id for s in self.sm_member.active_shifts(datetime.date(2026, 3, 13))], [self.day_shift.id],
        )

    def test_open_ended_assignment_has_no_end_date_limit(self):
        from handle.models import TemporaryShiftAssignment
        assignment = TemporaryShiftAssignment.objects.create(
            org=self.org, member=self.sm_member, start_date=datetime.date(2026, 3, 10), end_date=None,
            shift=self.night_shift,
        )
        self.assertTrue(assignment.covers(datetime.date(2026, 6, 1)))
        self.assertFalse(assignment.covers(datetime.date(2026, 3, 9)))

    def test_duty_roster_view_shows_off_and_on_status(self):
        response = self.client.get(reverse('schooladmin:duty_roster'), {'date': '2026-03-10'})
        self.assertEqual(response.status_code, 200)
        rows_by_member = {row['member'].id: row for row in response.context['rows']}
        self.assertFalse(rows_by_member[self.sm_member.id]['is_off'])
        self.assertFalse(rows_by_member[self.plain_member.id]['is_off'])

    def test_duty_roster_post_creates_assignment_and_history(self):
        response = self.client.post(reverse('schooladmin:duty_roster'), {
            'member_id': self.sm_member.id, 'start_date': '2026-03-10', 'end_date': '2026-03-12',
            'shift_id': self.night_shift.id, 'notes': 'Covering leave',
        })
        self.assertEqual(response.status_code, 302)
        from handle.models import TemporaryShiftAssignment
        assignment = TemporaryShiftAssignment.objects.get(member=self.sm_member)
        self.assertEqual(assignment.shift_id, self.night_shift.id)
        self.assertTrue(MemberHistory.objects.filter(member=self.sm_member, action='duty_roster_change').exists())

    def test_cancelling_assignment_restores_regular_pattern(self):
        from handle.models import TemporaryShiftAssignment
        target = datetime.date(2026, 3, 10)
        assignment = TemporaryShiftAssignment.objects.create(
            org=self.org, member=self.sm_member, start_date=target, end_date=target, shift=self.night_shift,
        )
        self.assertEqual([s.id for s in self.sm_member.active_shifts(target)], [self.night_shift.id])

        response = self.client.post(reverse('schooladmin:duty_roster_cancel', args=[assignment.id]))
        self.assertEqual(response.status_code, 302)
        assignment.refresh_from_db()
        self.assertFalse(assignment.is_active)
        self.assertEqual([s.id for s in self.sm_member.active_shifts(target)], [self.day_shift.id])

    def test_end_date_before_start_date_rejected(self):
        response = self.client.post(reverse('schooladmin:duty_roster'), {
            'member_id': self.sm_member.id, 'start_date': '2026-03-12', 'end_date': '2026-03-10',
            'shift_id': self.night_shift.id,
        }, follow=True)
        from handle.models import TemporaryShiftAssignment
        self.assertFalse(TemporaryShiftAssignment.objects.filter(member=self.sm_member).exists())
        msgs = [str(m) for m in get_messages(response.wsgi_request)]
        self.assertTrue(any('before' in m.lower() for m in msgs), msgs)


class WeeklyDutyRosterTests(TestCase):
    """Duty Roster's Week View — a member x 7-day grid (one <select> per
    cell) that bulk-saves to ordinary TemporaryShiftAssignment rows via
    WeeklyDutyRosterSaveView, so "each week is saved and viewable later"
    falls straight out of the existing model (see MemberCalendarViewTests'
    sibling feature for the analogous Monthly Report work)."""

    def setUp(self):
        self.org, self.admin_user = _make_org_and_admin("WeeklyRoster")
        self.org.feature_hrms = True
        self.org.allowed_features = sorted(set(self.org.allowed_features + ['hrms']))
        self.org.save(update_fields=['feature_hrms', 'allowed_features'])

        self.day_shift = Shift.objects.create(org=self.org, name='Day Shift')
        ShiftWindow.objects.create(shift=self.day_shift, start_time=datetime.time(9, 0), end_time=datetime.time(17, 0))
        self.night_shift = Shift.objects.create(org=self.org, name='Night Shift')
        ShiftWindow.objects.create(shift=self.night_shift, start_time=datetime.time(21, 0), end_time=datetime.time(5, 0))

        self.finance = Classification.objects.create(org=self.org, name='Finance')
        self.hr = Classification.objects.create(org=self.org, name='HR')

        self.member1 = member.objects.create(
            org=self.org, name='Roster Member One', gender='Male', classification=self.finance,
            shift_start_time=datetime.time(9, 0), shift_end_time=datetime.time(17, 0),
        )
        self.member2 = member.objects.create(
            org=self.org, name='Roster Member Two', gender='Female', classification=self.hr,
            shift_start_time=datetime.time(9, 0), shift_end_time=datetime.time(17, 0),
        )
        for weekday in range(7):
            MemberWeekdayShift.objects.create(org=self.org, member=self.member1, weekday=weekday, shift=self.day_shift)

        self.client.login(username="adminWeeklyRoster", password="testpass123")
        # A Sunday, so week_start snapping is a no-op for most of these tests.
        self.sunday = datetime.date(2026, 3, 1)
        self.assertEqual(member.weekday_number(self.sunday), 0)

    def test_week_view_shows_default_pattern_when_no_override(self):
        response = self.client.get(reverse('schooladmin:duty_roster'), {'view': 'week', 'week_start': self.sunday.isoformat()})
        self.assertEqual(response.status_code, 200)
        week_rows = {r['member'].id: r for r in response.context['week_rows']}
        cell = week_rows[self.member1.id]['cells'][0]
        self.assertEqual(cell['value'], '')
        self.assertEqual(cell['label'], 'Day Shift')
        self.assertFalse(cell['is_override'])

    def test_week_start_snaps_back_to_sunday(self):
        wednesday = datetime.date(2026, 3, 4)
        response = self.client.get(reverse('schooladmin:duty_roster'), {'view': 'week', 'week_start': wednesday.isoformat()})
        self.assertEqual(response.context['week_start'], self.sunday)

    def test_save_week_creates_single_day_assignment(self):
        url = reverse('schooladmin:duty_roster_save_week')
        field = f"shift_{self.member1.id}_{self.sunday.isoformat()}"
        response = self.client.post(url, {'week_start': self.sunday.isoformat(), field: str(self.night_shift.id)})
        self.assertEqual(response.status_code, 302)
        ta = TemporaryShiftAssignment.objects.get(member=self.member1, start_date=self.sunday, is_active=True)
        self.assertEqual(ta.end_date, self.sunday)
        self.assertEqual(ta.shift_id, self.night_shift.id)

    def test_save_week_off_value_creates_off_assignment(self):
        url = reverse('schooladmin:duty_roster_save_week')
        field = f"shift_{self.member1.id}_{self.sunday.isoformat()}"
        self.client.post(url, {'week_start': self.sunday.isoformat(), field: 'off'})
        ta = TemporaryShiftAssignment.objects.get(member=self.member1, start_date=self.sunday, is_active=True)
        self.assertIsNone(ta.shift_id)

    def test_save_week_default_value_clears_existing_override(self):
        TemporaryShiftAssignment.objects.create(
            org=self.org, member=self.member1, start_date=self.sunday, end_date=self.sunday, shift=self.night_shift,
        )
        url = reverse('schooladmin:duty_roster_save_week')
        field = f"shift_{self.member1.id}_{self.sunday.isoformat()}"
        self.client.post(url, {'week_start': self.sunday.isoformat(), field: ''})
        self.assertFalse(TemporaryShiftAssignment.objects.filter(
            member=self.member1, start_date=self.sunday, is_active=True,
        ).exists())

    def test_save_week_is_idempotent(self):
        url = reverse('schooladmin:duty_roster_save_week')
        field = f"shift_{self.member1.id}_{self.sunday.isoformat()}"
        self.client.post(url, {'week_start': self.sunday.isoformat(), field: str(self.night_shift.id)})
        self.client.post(url, {'week_start': self.sunday.isoformat(), field: str(self.night_shift.id)})
        self.assertEqual(
            TemporaryShiftAssignment.objects.filter(member=self.member1, start_date=self.sunday).count(), 1,
        )

    def test_save_week_ignores_cross_org_shift_id(self):
        other_org, _ = _make_org_and_admin('WeeklyRosterOther')
        outsider_shift = Shift.objects.create(org=other_org, name='Outsider Shift')
        url = reverse('schooladmin:duty_roster_save_week')
        field = f"shift_{self.member1.id}_{self.sunday.isoformat()}"
        response = self.client.post(url, {'week_start': self.sunday.isoformat(), field: str(outsider_shift.id)})
        self.assertEqual(response.status_code, 302)
        self.assertFalse(TemporaryShiftAssignment.objects.filter(member=self.member1, start_date=self.sunday).exists())

    def test_save_week_does_not_touch_other_org_members(self):
        other_org, other_admin = _make_org_and_admin('WeeklyRosterOutsider')
        outsider = member.objects.create(org=other_org, name='Outsider Member', gender='Male')
        url = reverse('schooladmin:duty_roster_save_week')
        field = f"shift_{outsider.id}_{self.sunday.isoformat()}"
        self.client.post(url, {'week_start': self.sunday.isoformat(), field: 'off'})
        self.assertFalse(TemporaryShiftAssignment.objects.filter(member=outsider).exists())

    def test_week_view_respects_classification_filter(self):
        response = self.client.get(reverse('schooladmin:duty_roster'), {
            'view': 'week', 'week_start': self.sunday.isoformat(), 'classification': self.finance.id,
        })
        member_ids = {r['member'].id for r in response.context['week_rows']}
        self.assertIn(self.member1.id, member_ids)
        self.assertNotIn(self.member2.id, member_ids)

    def test_save_week_logs_one_history_entry_per_changed_member(self):
        url = reverse('schooladmin:duty_roster_save_week')
        field1 = f"shift_{self.member1.id}_{self.sunday.isoformat()}"
        field2 = f"shift_{self.member1.id}_{(self.sunday + datetime.timedelta(days=1)).isoformat()}"
        self.client.post(url, {
            'week_start': self.sunday.isoformat(), field1: str(self.night_shift.id), field2: 'off',
        })
        self.assertEqual(
            MemberHistory.objects.filter(member=self.member1, action='duty_roster_change').count(), 1,
        )

    def test_save_week_records_shift_and_duty_type_together(self):
        duty_type = DutyType.objects.create(org=self.org, name='On-Call')
        url = reverse('schooladmin:duty_roster_save_week')
        shift_field = f"shift_{self.member1.id}_{self.sunday.isoformat()}"
        duty_field = f"dutytype_{self.member1.id}_{self.sunday.isoformat()}"
        self.client.post(url, {
            'week_start': self.sunday.isoformat(),
            shift_field: str(self.night_shift.id), duty_field: str(duty_type.id),
        })
        ta = TemporaryShiftAssignment.objects.get(member=self.member1, start_date=self.sunday, is_active=True)
        self.assertEqual(ta.shift_id, self.night_shift.id)
        self.assertEqual(ta.duty_type_id, duty_type.id)

    def test_save_week_duty_type_alone_is_not_saved(self):
        # Deliberate: shift=None already means "off duty" on this model, so a
        # duty type picked with no shift/off decision has nothing safe to
        # attach to and must not silently create an off-duty row.
        duty_type = DutyType.objects.create(org=self.org, name='On-Call')
        url = reverse('schooladmin:duty_roster_save_week')
        shift_field = f"shift_{self.member1.id}_{self.sunday.isoformat()}"
        duty_field = f"dutytype_{self.member1.id}_{self.sunday.isoformat()}"
        self.client.post(url, {
            'week_start': self.sunday.isoformat(),
            shift_field: '', duty_field: str(duty_type.id),
        })
        self.assertFalse(TemporaryShiftAssignment.objects.filter(member=self.member1, start_date=self.sunday).exists())

    def test_save_week_ignores_cross_org_duty_type_id(self):
        other_org, _ = _make_org_and_admin('WeeklyRosterDutyTypeOther')
        outsider_duty_type = DutyType.objects.create(org=other_org, name='Outsider Duty')
        url = reverse('schooladmin:duty_roster_save_week')
        shift_field = f"shift_{self.member1.id}_{self.sunday.isoformat()}"
        duty_field = f"dutytype_{self.member1.id}_{self.sunday.isoformat()}"
        self.client.post(url, {
            'week_start': self.sunday.isoformat(),
            shift_field: str(self.night_shift.id), duty_field: str(outsider_duty_type.id),
        })
        ta = TemporaryShiftAssignment.objects.get(member=self.member1, start_date=self.sunday, is_active=True)
        self.assertIsNone(ta.duty_type_id)


class DutyTypeTests(TestCase):
    """Org-wide Duty Type labels (Duty Roster's "Manage Duty Types" modal) —
    independent of Shift, recorded alongside it on a TemporaryShiftAssignment
    (see WeeklyDutyRosterTests for the roster-cell saving behaviour)."""

    def setUp(self):
        self.org, self.admin_user = _make_org_and_admin("DutyTypeMgmt")
        self.org.feature_hrms = True
        self.org.allowed_features = sorted(set(self.org.allowed_features + ['hrms']))
        self.org.save(update_fields=['feature_hrms', 'allowed_features'])
        self.client.login(username="adminDutyTypeMgmt", password="testpass123")

    def test_create_duty_type(self):
        url = reverse('schooladmin:duty_type_manage')
        response = self.client.post(url, {'action': 'create', 'name': 'Regular'})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(DutyType.objects.filter(org=self.org, name='Regular').exists())

    def test_create_with_default_unsets_other_defaults(self):
        first = DutyType.objects.create(org=self.org, name='Regular', is_default=True)
        url = reverse('schooladmin:duty_type_manage')
        self.client.post(url, {'action': 'create', 'name': 'On-Call', 'is_default': 'on'})
        first.refresh_from_db()
        self.assertFalse(first.is_default)
        self.assertTrue(DutyType.objects.get(org=self.org, name='On-Call').is_default)

    def test_create_duplicate_name_rejected(self):
        DutyType.objects.create(org=self.org, name='Regular')
        url = reverse('schooladmin:duty_type_manage')
        response = self.client.post(url, {'action': 'create', 'name': 'regular'}, follow=True)
        self.assertEqual(DutyType.objects.filter(org=self.org).count(), 1)
        msgs = [str(m) for m in get_messages(response.wsgi_request)]
        self.assertTrue(any('already exists' in m for m in msgs), msgs)

    def test_set_default_unsets_previous_default(self):
        first = DutyType.objects.create(org=self.org, name='Regular', is_default=True)
        second = DutyType.objects.create(org=self.org, name='On-Call')
        url = reverse('schooladmin:duty_type_manage')
        self.client.post(url, {'action': 'set_default', 'duty_type_id': second.id})
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertFalse(first.is_default)
        self.assertTrue(second.is_default)

    def test_toggle_active_disables_and_clears_default(self):
        dt = DutyType.objects.create(org=self.org, name='Regular', is_default=True)
        url = reverse('schooladmin:duty_type_manage')
        self.client.post(url, {'action': 'toggle_active', 'duty_type_id': dt.id})
        dt.refresh_from_db()
        self.assertFalse(dt.is_active)
        self.assertFalse(dt.is_default)

    def test_disabled_duty_type_not_offered_in_roster(self):
        DutyType.objects.create(org=self.org, name='Retired Type', is_active=False)
        response = self.client.get(reverse('schooladmin:duty_roster'))
        self.assertNotIn('Retired Type', [d.name for d in response.context['duty_types']])

    def test_duty_types_isolated_per_org(self):
        other_org, other_admin = _make_org_and_admin('DutyTypeMgmtOther')
        outsider_dt = DutyType.objects.create(org=other_org, name='Outsider Type')
        response = self.client.get(reverse('schooladmin:duty_roster'))
        self.assertNotIn(outsider_dt.name, [d.name for d in response.context['duty_types']])

    def test_manage_view_requires_admin(self):
        self.client.logout()
        staff_user = CustomUser.objects.create_user(
            username='staffDutyTypeMgmt', email='staffdutytypemgmt@example.com',
            password='testpass123', user_type='3',
        )
        self.client.login(username='staffDutyTypeMgmt', password='testpass123')
        response = self.client.post(reverse('schooladmin:duty_type_manage'), {'action': 'create', 'name': 'X'})
        self.assertNotEqual(response.status_code, 200)
        self.assertFalse(DutyType.objects.filter(name='X').exists())


class DutyRosterNepaliCalendarTests(TestCase):
    """Duty Roster (both Day View and Week View) shows BS dates alongside
    AD when the org has nepali_date enabled, matching the convention used
    everywhere else (Monthly Report, Member Calendar)."""

    def setUp(self):
        self.org, self.admin_user = _make_org_and_admin("DutyRosterNepali")
        self.org.feature_hrms = True
        self.org.nepali_date = True
        self.org.allowed_features = sorted(set(self.org.allowed_features + ['hrms']))
        self.org.save(update_fields=['feature_hrms', 'nepali_date', 'allowed_features'])
        self.member1 = member.objects.create(org=self.org, name='Nepali Roster Member', gender='Male')
        self.client.login(username="adminDutyRosterNepali", password="testpass123")

    def test_day_view_shows_bs_date_by_default(self):
        response = self.client.get(reverse('schooladmin:duty_roster'))
        self.assertTrue(response.context['nepali_enabled'])
        self.assertTrue(response.context['selected_date_np'])
        self.assertContains(response, '(BS)')

    def test_day_view_date_np_param_takes_priority_over_mismatched_ad_date(self):
        # 2083-04-31 BS is 2026-08-16 AD - deliberately pass a nonsense `date`
        # to prove the BS param, not the AD one, is authoritative.
        response = self.client.get(reverse('schooladmin:duty_roster'), {
            'date_np': '2083-04-31', 'date': '2020-01-01',
        })
        self.assertEqual(response.context['selected_date'], datetime.date(2026, 8, 16))

    def test_week_view_days_carry_bs_date(self):
        response = self.client.get(reverse('schooladmin:duty_roster'), {
            'view': 'week', 'week_start': '2026-08-16',
        })
        week_days = response.context['week_days']
        self.assertEqual(len(week_days), 7)
        self.assertTrue(all(d['date_np'] for d in week_days))
        self.assertEqual(week_days[0]['date_np'], '2083-04-31')

    def test_week_view_period_label_np_set(self):
        response = self.client.get(reverse('schooladmin:duty_roster'), {
            'view': 'week', 'week_start': '2026-08-16',
        })
        self.assertIn('2083-04-31', response.context['week_period_label_np'])

    def test_non_nepali_org_has_no_bs_dates(self):
        other_org, other_admin = _make_org_and_admin('DutyRosterNonNepali')
        other_org.feature_hrms = True
        other_org.allowed_features = sorted(set(other_org.allowed_features + ['hrms']))
        other_org.save(update_fields=['feature_hrms', 'allowed_features'])
        self.client.logout()
        self.client.login(username='adminDutyRosterNonNepali', password='testpass123')
        response = self.client.get(reverse('schooladmin:duty_roster'), {'view': 'week'})
        self.assertFalse(response.context['nepali_enabled'])
        self.assertEqual(response.context['selected_date_np'], '')
        self.assertNotContains(response, '(BS)')


class AttendanceStatsNullDateHandlingTests(TestCase):
    """Regression test: Occasion.end_date and LeaveReport.gap_end/gap_start
    are nullable (a single-day leave deliberately has gap_end=None — see
    management/views.py's leave-submit handler), and calculate_attendance_stats
    must not crash on that. The day-loop's occasion/leave matching was
    switched from a per-day DB `.filter()` (where a NULL simply never
    satisfies a >=/<= lookup) to a plain-Python date comparison for
    performance — `None <= x` raises TypeError where the SQL equivalent
    silently excluded the row, so the Python side needs its own explicit
    None guards."""

    def setUp(self):
        self.org, self.admin_user = _make_org_and_admin("NullDateStats")
        self.member = member.objects.create(
            org=self.org, name='Null Date Member', gender='Male',
            salary_type='monthly', salary_amount=Decimal('20000.00'),
        )
        self.start = datetime.date(2026, 8, 1)
        self.end = datetime.date(2026, 8, 17)

    def test_single_day_leave_with_null_gap_end_does_not_crash(self):
        from schooladmin.payroll_service import calculate_attendance_stats
        LeaveReport.objects.create(
            member=self.member, org=self.org, gap_start=datetime.date(2026, 8, 17),
            gap_end=None, approved=True, reason='single day',
        )
        stats, daily_logs = calculate_attendance_stats(self.member, self.start, self.end, self.org)
        self.assertEqual(stats['total_days'], 17)

    def test_leave_with_null_gap_start_does_not_crash(self):
        from schooladmin.payroll_service import calculate_attendance_stats
        LeaveReport.objects.create(
            member=self.member, org=self.org, gap_start=None,
            gap_end=datetime.date(2026, 8, 17), approved=True, reason='malformed',
        )
        stats, daily_logs = calculate_attendance_stats(self.member, self.start, self.end, self.org)
        self.assertEqual(stats['total_days'], 17)

    def test_occasion_with_null_end_date_does_not_crash(self):
        from management.models import Occasion
        from schooladmin.payroll_service import calculate_attendance_stats
        Occasion.objects.create(org=self.org, name='Unbounded', date=datetime.date(2026, 8, 10), end_date=None)
        stats, daily_logs = calculate_attendance_stats(self.member, self.start, self.end, self.org)
        self.assertEqual(stats['total_days'], 17)

    def test_gap_leave_with_both_dates_still_matches(self):
        # Multi-day ("gap") leaves have both ends set — confirm the None
        # guards didn't also break the normal, fully-populated case.
        from schooladmin.payroll_service import calculate_attendance_stats
        LeaveReport.objects.create(
            member=self.member, org=self.org, gap_start=datetime.date(2026, 8, 5),
            gap_end=datetime.date(2026, 8, 7), approved=True, reason='gap leave',
        )
        stats, daily_logs = calculate_attendance_stats(self.member, self.start, self.end, self.org)
        self.assertEqual(stats['days_leave'], 3)


class PayrollComponentOverrideTests(TestCase):
    """Phase 5: calculate_payroll_components's optional overrides — what the
    Bulk Payslip preview/edit step uses. An override must change only the
    numbers it returns, never the member's or org's actual stored settings."""

    def setUp(self):
        self.org, self.admin_user = _make_org_and_admin("PayrollOverride")
        self.policy = PayrollPolicy.objects.create(
            org=self.org, pf_employee_percentage=Decimal('10.00'), pf_employer_percentage=Decimal('10.00'),
            ssf_employee_percentage=Decimal('11.00'), ssf_employer_percentage=Decimal('20.00'),
        )
        self.member = member.objects.create(
            org=self.org, name='Override Test', gender='Male',
            salary_type='monthly', salary_amount=Decimal('30000.00'),
            tax_percentage=Decimal('1.00'), pf_enabled=True, ssf_enabled=True,
        )
        self.stats = {
            'total_days': 30, 'days_present': 30, 'days_paid_leave': 0,
            'days_unpaid_leave': 0, 'days_unpaid_absent': 0, 'days_holiday': 0,
            'total_hours_worked': Decimal('0'), 'total_missing_hours': Decimal('0'),
            'total_overtime_hours': Decimal('0'),
        }
        self.end_date = datetime.date(2026, 1, 31)

    def test_default_call_matches_pre_existing_behavior(self):
        from schooladmin.payroll_service import calculate_payroll_components
        comps = calculate_payroll_components(self.member, self.stats, self.org, self.policy, self.end_date)
        self.assertEqual(comps['tax_pct'], Decimal('1.00'))
        self.assertEqual(comps['pf_employee_pct'], Decimal('10.00'))
        self.assertEqual(comps['tax_amount'], (Decimal('30000.00') * Decimal('1.00') / Decimal('100')).quantize(Decimal('0.01')))

    def test_tds_override_changes_tax_only_for_this_call(self):
        from schooladmin.payroll_service import calculate_payroll_components
        comps = calculate_payroll_components(
            self.member, self.stats, self.org, self.policy, self.end_date,
            tds_pct_override=Decimal('5.00'),
        )
        self.assertEqual(comps['tax_pct'], Decimal('5.00'))
        self.member.refresh_from_db()
        self.assertEqual(self.member.tax_percentage, Decimal('1.00'))

    def test_pf_ssf_overrides_change_deductions_only_for_this_call(self):
        from schooladmin.payroll_service import calculate_payroll_components
        comps = calculate_payroll_components(
            self.member, self.stats, self.org, self.policy, self.end_date,
            pf_employee_pct_override=Decimal('12.00'), ssf_employee_pct_override=Decimal('15.00'),
        )
        self.assertEqual(comps['pf_employee_pct'], Decimal('12.00'))
        self.assertEqual(comps['ssf_employee_pct'], Decimal('15.00'))
        self.policy.refresh_from_db()
        self.assertEqual(self.policy.pf_employee_percentage, Decimal('10.00'))
        self.assertEqual(self.policy.ssf_employee_percentage, Decimal('11.00'))

    def test_extra_bonus_allowance_deduction_flow_into_gross_and_net(self):
        from schooladmin.payroll_service import calculate_payroll_components
        base = calculate_payroll_components(self.member, self.stats, self.org, self.policy, self.end_date)
        with_extra = calculate_payroll_components(
            self.member, self.stats, self.org, self.policy, self.end_date,
            extra_bonus=Decimal('1000.00'), extra_allowance=Decimal('500.00'), extra_deduction=Decimal('200.00'),
        )
        self.assertEqual(
            with_extra['gross_salary'],
            base['gross_salary'] + Decimal('1000.00') + Decimal('500.00') - Decimal('200.00'),
        )
        self.assertGreater(with_extra['net_payable'], base['net_payable'])

    def test_pf_disabled_member_ignores_pf_override(self):
        from schooladmin.payroll_service import calculate_payroll_components
        self.member.pf_enabled = False
        comps = calculate_payroll_components(
            self.member, self.stats, self.org, self.policy, self.end_date,
            pf_employee_pct_override=Decimal('50.00'),
        )
        self.assertEqual(comps['pf_employee'], Decimal('0.00'))


class BulkPayslipPreviewGenerateTests(TestCase):
    """Phase 5: the Bulk Payslip select -> preview -> generate flow."""

    def setUp(self):
        self.org, self.admin_user = _make_org_and_admin("BulkPreview")
        PayrollPolicy.objects.get_or_create(org=self.org, defaults={
            'pf_employee_percentage': Decimal('10.00'), 'ssf_employee_percentage': Decimal('11.00'),
        })
        self.m1 = member.objects.create(
            org=self.org, name='Employee One', gender='Male',
            salary_type='monthly', salary_amount=Decimal('30000.00'), tax_percentage=Decimal('1.00'),
        )
        self.m2 = member.objects.create(
            org=self.org, name='Employee Two', gender='Female',
            salary_type='monthly', salary_amount=Decimal('40000.00'), tax_percentage=Decimal('1.00'),
        )
        self.client.login(username="adminBulkPreview", password="testpass123")
        self.from_date = datetime.date(2026, 1, 1)
        self.to_date = datetime.date(2026, 1, 31)

    def _base_payload(self, member_ids=None):
        return {
            'member_ids': member_ids if member_ids is not None else [self.m1.id, self.m2.id],
            'from_date': self.from_date.strftime('%Y-%m-%d'),
            'to_date': self.to_date.strftime('%Y-%m-%d'),
            'month_name': 'January 2026',
        }

    def test_preview_step_creates_no_payslips(self):
        response = self.client.post(reverse('schooladmin:bulk_payslip'), self._base_payload())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(PaySlip.objects.filter(org=self.org).count(), 0)
        self.assertEqual(len(response.context['rows']), 2)

    def test_preview_shows_computed_net_for_each_member(self):
        # No AttendanceRecord fixtures here, so zero attendance for the whole
        # period correctly nets to Rs. 0 (see calculate_payroll_components's
        # zero-attendance rule) — this just checks the preview actually ran
        # the real calculation for both members rather than erroring out.
        response = self.client.post(reverse('schooladmin:bulk_payslip'), self._base_payload())
        nets = {row['member'].name: row['comps']['net_payable'] for row in response.context['rows']}
        self.assertIn('Employee One', nets)
        self.assertIn('Employee Two', nets)
        self.assertGreaterEqual(nets['Employee One'], Decimal('0'))

    def test_generate_step_creates_payslips_with_overridden_tds(self):
        payload = self._base_payload(member_ids=[self.m1.id])
        payload['step'] = 'generate'
        payload[f'tds_{self.m1.id}'] = '5.00'
        response = self.client.post(reverse('schooladmin:bulk_payslip'), payload)
        self.assertEqual(response.status_code, 302)
        slip = PaySlip.objects.get(member=self.m1, org=self.org)
        expected_tax = (slip.gross_salary * Decimal('5.00') / Decimal('100')).quantize(Decimal('0.01'))
        self.assertEqual(slip.tax_deduction, expected_tax)
        self.m1.refresh_from_db()
        self.assertEqual(self.m1.tax_percentage, Decimal('1.00'))

    def test_generate_step_respects_extra_bonus(self):
        payload = self._base_payload(member_ids=[self.m2.id])
        payload['step'] = 'generate'
        payload[f'bonus_{self.m2.id}'] = '2000.00'
        self.client.post(reverse('schooladmin:bulk_payslip'), payload)
        slip = PaySlip.objects.get(member=self.m2, org=self.org)
        self.assertEqual(slip.bonus_total, Decimal('2000.00'))

    def test_generate_step_skips_existing_payslip(self):
        payload = self._base_payload(member_ids=[self.m1.id])
        payload['step'] = 'generate'
        self.client.post(reverse('schooladmin:bulk_payslip'), payload)
        self.assertEqual(PaySlip.objects.filter(member=self.m1, org=self.org).count(), 1)
        self.client.post(reverse('schooladmin:bulk_payslip'), payload)
        self.assertEqual(PaySlip.objects.filter(member=self.m1, org=self.org).count(), 1)

    def test_preview_flags_already_existing_payslip(self):
        payload = self._base_payload(member_ids=[self.m1.id])
        payload['step'] = 'generate'
        self.client.post(reverse('schooladmin:bulk_payslip'), payload)

        preview_payload = self._base_payload(member_ids=[self.m1.id])
        response = self.client.post(reverse('schooladmin:bulk_payslip'), preview_payload)
        self.assertTrue(response.context['rows'][0]['already_exists'])

    def test_cannot_generate_for_another_orgs_member(self):
        other_org, other_admin = _make_org_and_admin("BulkPreviewOther")
        outsider = member.objects.create(
            org=other_org, name='Outsider', gender='Male',
            salary_type='monthly', salary_amount=Decimal('20000.00'),
        )
        payload = self._base_payload(member_ids=[outsider.id])
        payload['step'] = 'generate'
        self.client.post(reverse('schooladmin:bulk_payslip'), payload)
        self.assertFalse(PaySlip.objects.filter(member=outsider).exists())


class MemberAvatarFilterTests(TestCase):
    """Member-photo display rollout: the member_avatar filter shows a real
    photo when uploaded, and a colored-initial fallback otherwise. Also
    covers the in_list filter added alongside it (fixes a real
    TemplateSyntaxError in staff/attendance.html — see staff.tests)."""

    _ONE_PIXEL_GIF = (
        b'GIF87a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\x00\x00\x00'
        b'!\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;'
    )

    def setUp(self):
        self.org = Organization.objects.create(
            name='Avatar Filter Org', expire_on=timezone.now() + datetime.timedelta(days=30),
        )

    def test_fallback_initial_when_no_photo(self):
        from schooladmin.templatetags.schooladmin_extras import member_avatar
        m = member.objects.create(org=self.org, name='Zara Test', gender='Female')
        html = member_avatar(m)
        self.assertIn('>Z<', html)
        self.assertNotIn('<img', html)

    def test_real_photo_renders_img_tag(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        from schooladmin.templatetags.schooladmin_extras import member_avatar
        photo = SimpleUploadedFile('avatar.gif', self._ONE_PIXEL_GIF, content_type='image/gif')
        m = member.objects.create(org=self.org, name='Photo Test', gender='Male', photo=photo)
        html = member_avatar(m)
        self.assertIn('<img', html)
        self.assertIn('member_photos/', html)

    def test_empty_member_returns_empty_string(self):
        from schooladmin.templatetags.schooladmin_extras import member_avatar
        self.assertEqual(member_avatar(None), '')

    def test_name_is_escaped_against_xss(self):
        from schooladmin.templatetags.schooladmin_extras import member_avatar
        m = member.objects.create(org=self.org, name='<script>alert(1)</script>', gender='Male')
        html = member_avatar(m)
        self.assertNotIn('<script>', html)

    def test_in_list_filter(self):
        from schooladmin.templatetags.schooladmin_extras import in_list
        self.assertTrue(in_list(3, {1, 2, 3}))
        self.assertFalse(in_list(9, {1, 2, 3}))
        self.assertFalse(in_list(3, None))


class MemberCalendarViewTests(TestCase):
    """Monthly Report's Calendar View tab + the Member Gap Report calendar,
    both driven by schooladmin.calendar_service.build_member_calendar and
    the shared MemberCalendarDataView/DayQuickActionView endpoints. Also
    covers the effective_shift_start/end IndexError this work uncovered:
    any Shift-Management member's day off (a day with zero shift windows,
    by design) crashed every caller of late_in()/early_out() with an
    unguarded `shift_windows(...)[0][0]` on an empty list - the Member Gap
    Report's POST handler had no try/except around that call, so opening a
    date range that included such a day 500'd the whole page."""

    def setUp(self):
        self.org, self.admin_user = _make_org_and_admin("MemberCalendar")
        self.day_shift = Shift.objects.create(org=self.org, name='Day Shift')
        ShiftWindow.objects.create(shift=self.day_shift, start_time=datetime.time(9, 0), end_time=datetime.time(17, 0))

        # Shift-Management member with a day off on one specific weekday -
        # the exact real-world shape that used to crash effective_shift_start.
        self.sm_member = member.objects.create(org=self.org, name='Shift Member', gender='Male')
        self.off_weekday = 6  # Mero convention: Saturday
        for weekday in range(7):
            if weekday == self.off_weekday:
                continue
            MemberWeekdayShift.objects.create(org=self.org, member=self.sm_member, weekday=weekday, shift=self.day_shift)

        self.leave_type = LeaveType.objects.create(org=self.org, name='Casual Leave', annual_allocation=12, is_paid=True)
        self.client.login(username="adminMemberCalendar", password="testpass123")

    def _next_off_day(self, start):
        d = start
        while member.weekday_number(d) != self.off_weekday:
            d += datetime.timedelta(days=1)
        return d

    # --- root-cause fix: effective_shift_start/end must not crash on a day
    # with zero shift windows ---

    def test_effective_shift_start_returns_none_not_indexerror_on_day_off(self):
        off_day = self._next_off_day(datetime.date(2026, 3, 1))
        self.assertEqual(self.sm_member.shift_windows(off_day), [])
        self.assertIsNone(self.sm_member.effective_shift_start(off_day))
        self.assertIsNone(self.sm_member.effective_shift_end(off_day))

    def test_late_in_and_early_out_do_not_raise_on_day_off(self):
        off_day = self._next_off_day(datetime.date(2026, 3, 1))
        self.sm_member.date = off_day
        self.assertIsNone(self.sm_member.late_in())
        self.assertIsNone(self.sm_member.early_out())
        self.sm_member.date = None

    def test_member_gap_report_post_does_not_crash_for_member_with_day_off(self):
        off_day = self._next_off_day(datetime.date(2026, 3, 1))
        start = off_day - datetime.timedelta(days=3)
        end = off_day + datetime.timedelta(days=3)
        response = self.client.post(
            reverse('schooladmin:memberGapReport', args=(self.sm_member.pk,)),
            {'first_date': start.isoformat(), 'last_date': end.isoformat()},
        )
        self.assertEqual(response.status_code, 200)

    def test_calculate_attendance_stats_present_on_temp_off_day_does_not_crash(self):
        # A plain-default member marked explicitly off-duty via Duty Roster
        # for one day, who nonetheless punched in/out that day - exercises
        # the same empty-shift-windows path inside calculate_attendance_stats
        # (payroll_service.py), independent of the Gap Report view.
        from schooladmin.payroll_service import calculate_attendance_stats
        plain_member = member.objects.create(
            org=self.org, name='Plain Member', gender='Male',
            shift_start_time=datetime.time(9, 0), shift_end_time=datetime.time(17, 0),
        )
        target = datetime.date(2026, 3, 9)
        TemporaryShiftAssignment.objects.create(
            org=self.org, member=plain_member, start_date=target, end_date=target, shift=None,
        )
        AttendanceRecord.objects.create(
            mem=plain_member, org=self.org,
            scanned_time=timezone.make_aware(datetime.datetime.combine(target, datetime.time(9, 5))),
        )
        AttendanceRecord.objects.create(
            mem=plain_member, org=self.org,
            scanned_time=timezone.make_aware(datetime.datetime.combine(target, datetime.time(17, 10))),
        )
        stats, logs = calculate_attendance_stats(plain_member, target, target, self.org)
        self.assertEqual(logs[0]['status'], 'Present')

    # --- calendar_service: single-day leave display ---

    def test_single_day_leave_shows_as_leave_not_absent_in_calendar(self):
        from schooladmin.calendar_service import build_member_calendar
        leave_date = datetime.date(2026, 3, 5)
        LeaveReport.objects.create(
            member=self.sm_member, org=self.org, leave_type=self.leave_type,
            gap_start=leave_date, gap_end=None, reason='Personal', approved=True,
        )
        days = build_member_calendar(self.sm_member, leave_date, leave_date, self.org)
        self.assertEqual(len(days), 1)
        self.assertEqual(days[0]['code'], 'L')
        self.assertEqual(days[0]['status'], 'Paid Leave')
        self.assertEqual(days[0]['leave_type'], 'Casual Leave')

    def test_note_attached_to_correct_day(self):
        from schooladmin.calendar_service import build_member_calendar
        target = datetime.date(2026, 3, 6)
        DailyNote.objects.create(member=self.sm_member, org=self.org, date=target, text='Left early')
        days = build_member_calendar(self.sm_member, target, target, self.org)
        self.assertEqual(days[0]['note'], 'Left early')

    # --- DailyNote model ---

    def test_daily_note_is_one_per_member_per_day(self):
        target = datetime.date(2026, 3, 7)
        DailyNote.objects.update_or_create(member=self.sm_member, date=target, defaults={'org': self.org, 'text': 'first'})
        DailyNote.objects.update_or_create(member=self.sm_member, date=target, defaults={'org': self.org, 'text': 'second'})
        self.assertEqual(DailyNote.objects.filter(member=self.sm_member, date=target).count(), 1)
        self.assertEqual(DailyNote.objects.get(member=self.sm_member, date=target).text, 'second')

    # --- MemberCalendarDataView ---

    def test_member_calendar_data_view_returns_days(self):
        url = reverse('schooladmin:member_calendar_data', args=(self.sm_member.pk,))
        response = self.client.get(url, {'from_date': '2026-03-01', 'to_date': '2026-03-07'})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data['days']), 7)
        self.assertEqual(data['member']['name'], 'Shift Member')

    def test_member_calendar_data_view_404s_for_other_org_member(self):
        other_org, _ = _make_org_and_admin('MemberCalendarOther')
        outsider = member.objects.create(org=other_org, name='Outsider', gender='Male')
        url = reverse('schooladmin:member_calendar_data', args=(outsider.pk,))
        response = self.client.get(url, {'from_date': '2026-03-01', 'to_date': '2026-03-07'})
        self.assertEqual(response.status_code, 404)

    # --- DayQuickActionView ---

    def test_day_action_creates_leave(self):
        url = reverse('schooladmin:day_quick_action')
        response = self.client.post(url, data=json.dumps({
            'member_id': self.sm_member.pk, 'date': '2026-03-05',
            'action': 'leave', 'leave_type_id': self.leave_type.pk, 'reason': 'Sick',
        }), content_type='application/json')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['ok'])
        self.assertTrue(LeaveReport.objects.filter(
            member=self.sm_member, gap_start=datetime.date(2026, 3, 5), approved=True,
        ).exists())

    def test_day_action_rejects_leave_beyond_balance(self):
        self.leave_type.annual_allocation = 0
        self.leave_type.save(update_fields=['annual_allocation'])
        url = reverse('schooladmin:day_quick_action')
        response = self.client.post(url, data=json.dumps({
            'member_id': self.sm_member.pk, 'date': '2026-03-05',
            'action': 'leave', 'leave_type_id': self.leave_type.pk, 'reason': 'Sick',
        }), content_type='application/json')
        self.assertEqual(response.status_code, 422)
        self.assertFalse(response.json()['ok'])
        self.assertFalse(LeaveReport.objects.filter(member=self.sm_member).exists())

    def test_day_action_creates_and_updates_note(self):
        url = reverse('schooladmin:day_quick_action')
        response = self.client.post(url, data=json.dumps({
            'member_id': self.sm_member.pk, 'date': '2026-03-05',
            'action': 'note', 'text': 'Forgot to punch out',
        }), content_type='application/json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            DailyNote.objects.get(member=self.sm_member, date=datetime.date(2026, 3, 5)).text,
            'Forgot to punch out',
        )

        response = self.client.post(url, data=json.dumps({
            'member_id': self.sm_member.pk, 'date': '2026-03-05',
            'action': 'note', 'text': 'Confirmed with supervisor',
        }), content_type='application/json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            DailyNote.objects.filter(member=self.sm_member, date=datetime.date(2026, 3, 5)).count(), 1,
        )
        self.assertEqual(
            DailyNote.objects.get(member=self.sm_member, date=datetime.date(2026, 3, 5)).text,
            'Confirmed with supervisor',
        )

    def test_day_action_rejects_cross_org_member(self):
        other_org, _ = _make_org_and_admin('DayActionOther')
        outsider = member.objects.create(org=other_org, name='Outsider2', gender='Male')
        url = reverse('schooladmin:day_quick_action')
        response = self.client.post(url, data=json.dumps({
            'member_id': outsider.pk, 'date': '2026-03-05', 'action': 'note', 'text': 'x',
        }), content_type='application/json')
        self.assertEqual(response.status_code, 404)

    def test_day_action_rejects_unknown_action(self):
        url = reverse('schooladmin:day_quick_action')
        response = self.client.post(url, data=json.dumps({
            'member_id': self.sm_member.pk, 'date': '2026-03-05', 'action': 'bogus',
        }), content_type='application/json')
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()['ok'])


class OrganizationProfileEnrichmentTests(TestCase):
    """Organization Profile page: email field and "at a glance" stats
    (feature-gated). The Print Defaults section was removed 2026-08-19 -
    the "fit to page width" auto-zoom it relied on (static/js/print_settings.js)
    could shrink a naturally multi-page report enough, in both dimensions,
    to fit on one page - the reported "only lets 1 page print" bug. See
    OrgPrintDefaultTests in handle/tests.py for the still-intact backend
    (model/service/AJAX endpoint) this UI used to sit on top of."""

    def setUp(self):
        self.org, self.admin_user = _make_org_and_admin("OrgProfileEnrich")
        self.client.login(username="adminOrgProfileEnrich", password="testpass123")

    def test_profile_page_renders_with_stats(self):
        response = self.client.get(reverse('schooladmin:orgDetail'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('org_stats', response.context)
        self.assertIn('total_members', response.context['org_stats'])

    def test_profile_page_has_no_print_settings_panel(self):
        response = self.client.get(reverse('schooladmin:orgDetail'))
        self.assertNotContains(response, 'print_settings.js')
        self.assertNotContains(response, 'orgPrintDefault-')

    def test_stats_hide_student_and_stock_when_features_off(self):
        response = self.client.get(reverse('schooladmin:orgDetail'))
        self.assertNotIn('total_students', response.context['org_stats'])
        self.assertNotIn('total_stock_items', response.context['org_stats'])

    def test_stats_show_students_when_student_mgmt_enabled(self):
        self.org.feature_student_mgmt = True
        self.org.allowed_features = sorted(set(self.org.allowed_features + ['student_mgmt']))
        self.org.save(update_fields=['feature_student_mgmt', 'allowed_features'])
        member.objects.create(org=self.org, name='A Student', gender='Female', member_type='student')
        response = self.client.get(reverse('schooladmin:orgDetail'))
        self.assertEqual(response.context['org_stats']['total_students'], 1)

    def test_updating_profile_saves_email(self):
        response = self.client.post(reverse('schooladmin:orgDetail'), {
            'name': self.org.name, 'address': 'New Address',
            'email': 'contact@orgprofileenrich.example.com', 'serial_key': self.org.serial_key,
        })
        self.assertEqual(response.status_code, 302)
        self.org.refresh_from_db()
        self.assertEqual(self.org.email, 'contact@orgprofileenrich.example.com')

class PresentAbsentTodayDateFilterTests(TestCase):
    """Regression test: PresentToday/AbsentToday's POST handlers took
    request.POST.get('date') as a raw string and assigned it straight to
    the class-level `member.date` with no datetime.strptime() conversion.
    member.late_in()/early_out() (rendered in presentToday.html for every
    present member) call effective_shift_start(self.date) ->
    shift_windows(...) -> weekday_number(target_date), which does
    target_date.weekday() - AttributeError on a plain str. Only reproduces
    with at least one member who actually has an AttendanceRecord for the
    filtered date (an empty present list never touches the buggy line)."""

    def setUp(self):
        self.org, self.admin_user = _make_org_and_admin("TodayDateFilter")
        self.member = member.objects.create(
            org=self.org, name='Punched In Member', gender='Male',
            shift_start_time=datetime.time(9, 0), shift_end_time=datetime.time(17, 0),
        )
        self.target_date = datetime.date(2026, 3, 10)
        tz_aware = timezone.make_aware(datetime.datetime.combine(self.target_date, datetime.time(9, 5)))
        AttendanceRecord.objects.create(mem=self.member, org=self.org, scanned_time=tz_aware)
        tz_aware_out = timezone.make_aware(datetime.datetime.combine(self.target_date, datetime.time(17, 10)))
        AttendanceRecord.objects.create(mem=self.member, org=self.org, scanned_time=tz_aware_out)
        self.client.login(username="adminTodayDateFilter", password="testpass123")

    def test_present_today_post_with_ad_date_does_not_crash(self):
        response = self.client.post(reverse('schooladmin:presentToday'), {'date': self.target_date.isoformat()})
        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response.context['date'], datetime.date)
        self.assertContains(response, 'Punched In Member')

    def test_present_today_post_with_nepali_date_does_not_crash(self):
        self.org.nepali_date = True
        self.org.save(update_fields=['nepali_date'])
        date_np = str(nepali_datetime.date.from_datetime_date(self.target_date))
        response = self.client.post(reverse('schooladmin:presentToday'), {'date_np': date_np})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['date'], self.target_date)

    def test_present_today_post_with_no_date_falls_back_to_today(self):
        response = self.client.post(reverse('schooladmin:presentToday'), {})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['date'], datetime.date.today())

    def test_absent_today_post_with_ad_date_does_not_crash(self):
        response = self.client.post(reverse('schooladmin:absentToday'), {'date': self.target_date.isoformat()})
        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response.context['date'], datetime.date)

    def test_absent_today_post_with_nepali_date_does_not_crash(self):
        self.org.nepali_date = True
        self.org.save(update_fields=['nepali_date'])
        date_np = str(nepali_datetime.date.from_datetime_date(self.target_date))
        response = self.client.post(reverse('schooladmin:absentToday'), {'date_np': date_np})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['date'], self.target_date)
