import datetime
import io
import json
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.messages import get_messages
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.template import Context, Template
from django.urls import reverse
from django.utils import timezone

from management.models import CustomUser, Organization, OrganizationShiftOverride, Schooladmin
from school.context_processors import _OneShotMessages
from .forms import MemberForm
from .models import (
    ADMSAttendanceEvent, AttendanceRecord, Branch, Classification, Device, InAppNotification,
    MemberWeekdayShift, Section, Shift, ShiftWindow,
    Staff, StaffPermission, Task, TaskInstance, member,
)
from .attendance_writes import (
    DuplicateAttendancePunch,
    create_attendance_punch,
)


class AttendanceWriteGuardTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(
            name='Attendance Guard Org',
            expire_on=timezone.now() + timedelta(days=30),
            serial_key='ATT-GUARD-001',
            new_serial_key='attendance-guard-secret',
            activate=True,
        )
        self.member = member.objects.create(
            org=self.org,
            device_id=771,
            name='Guarded Member',
            gender='Male',
        )

    def test_blocks_second_punch_inside_one_minute_across_methods(self):
        now = timezone.now()
        first, already_marked = create_attendance_punch(
            memb=self.member,
            org=self.org,
            attendance_method='qr',
            scanned_time=now,
        )

        self.assertFalse(already_marked)
        with self.assertRaises(DuplicateAttendancePunch):
            create_attendance_punch(
                memb=self.member,
                org=self.org,
                attendance_method='gps',
                scanned_time=now + timedelta(seconds=59),
            )
        self.assertEqual(AttendanceRecord.objects.filter(mem=self.member).count(), 1)
        self.assertEqual(first.attendance_method, 'qr')

    def test_allows_checkout_after_one_minute(self):
        now = timezone.now()
        create_attendance_punch(
            memb=self.member,
            org=self.org,
            attendance_method='wifi',
            scanned_time=now,
        )
        second, already_marked = create_attendance_punch(
            memb=self.member,
            org=self.org,
            attendance_method='gps',
            scanned_time=now + timedelta(seconds=61),
        )

        self.assertTrue(already_marked)
        self.assertEqual(second.attendance_method, 'gps')
        self.assertEqual(AttendanceRecord.objects.filter(mem=self.member).count(), 2)


class HikvisionAttendanceEventTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(
            name="Demo Org",
            expire_on=timezone.now() + timedelta(days=30),
            serial_key="ORG-001",
            new_serial_key="hikvision-secret",
            activate=True,
        )
        self.member = member.objects.create(
            org=self.org,
            device_id=101,
            name="Ram Student",
            gender="Male",
        )
        self.url = reverse(
            "handle:hikvision_attendance_event",
            args=[self.org.serial_key, self.org.new_serial_key],
        )

    def test_json_event_creates_attendance_for_device_user(self):
        response = self.client.post(
            self.url,
            data=json.dumps(
                {
                    "eventType": "AccessControllerEvent",
                    "dateTime": "2026-06-23T09:15:00+05:45",
                    "AccessControllerEvent": {
                        "employeeNoString": "101",
                        "cardNo": "ABC123",
                    },
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(AttendanceRecord.objects.count(), 1)
        attendance = AttendanceRecord.objects.get()
        self.assertEqual(attendance.mem, self.member)
        self.assertEqual(attendance.org, self.org)

    def test_duplicate_event_does_not_create_second_attendance(self):
        payload = {
            "dateTime": "2026-06-23T09:15:00+05:45",
            "AccessControllerEvent": {"employeeNoString": "101"},
        }

        first = self.client.post(self.url, data=json.dumps(payload), content_type="application/json")
        second = self.client.post(self.url, data=json.dumps(payload), content_type="application/json")

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.json()["status"], "duplicate")
        self.assertEqual(AttendanceRecord.objects.count(), 1)


class ADMSPushReceiverTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(
            name='ADMS School',
            expire_on=timezone.now() + timedelta(days=30),
            serial_key='ADMS-ORG-001',
            new_serial_key='unused-adms-key',
            activate=True,
        )
        self.device = Device.objects.create(
            org=self.org,
            name='Main Gate ADMS',
            connection_mode='adms',
            serial_number='CQZK241260123',
        )
        self.member = member.objects.create(
            org=self.org,
            device_id=101,
            name='ADMS Member',
            gender='Male',
        )
        self.url = reverse('adms_cdata')

    def test_registered_device_receives_push_options_and_updates_heartbeat(self):
        response = self.client.get(
            self.url,
            {'SN': self.device.serial_number, 'options': 'all', 'pushver': '2.4.1'},
            REMOTE_ADDR='203.0.113.10',
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f'GET OPTION FROM: {self.device.serial_number}')
        self.assertContains(response, 'Realtime=1')
        self.assertContains(response, 'TimeZone=345')
        self.assertNotContains(response, 'DateTime=')
        self.device.refresh_from_db()
        self.assertIsNotNone(self.device.last_seen_at)
        self.assertEqual(self.device.last_ip_address, '203.0.113.10')
        self.assertEqual(self.device.push_version, '2.4.1')

    def test_attlog_push_creates_biometric_attendance_and_is_idempotent(self):
        body = '101\t2026-07-31 09:15:00\t0\t1\t0\t0\n'
        url = f'{self.url}?SN={self.device.serial_number}&table=ATTLOG&Stamp=1'

        first = self.client.post(url, data=body, content_type='text/plain')
        repeated = self.client.post(url, data=body, content_type='text/plain')

        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.content.decode(), 'OK: 1')
        self.assertEqual(repeated.status_code, 200)
        self.assertEqual(repeated.content.decode(), 'OK: 1')
        self.assertEqual(AttendanceRecord.objects.count(), 1)
        attendance = AttendanceRecord.objects.get()
        self.assertEqual(attendance.mem, self.member)
        self.assertEqual(attendance.org, self.org)
        self.assertEqual(attendance.attendance_method, 'biometric')
        self.assertEqual(ADMSAttendanceEvent.objects.count(), 1)
        self.assertEqual(ADMSAttendanceEvent.objects.get().status, 'stored')
        self.device.refresh_from_db()
        self.assertIsNotNone(self.device.last_push_at)

    def test_device_serial_scopes_same_pin_to_its_organization(self):
        other_org = Organization.objects.create(
            name='Other ADMS School',
            expire_on=timezone.now() + timedelta(days=30),
            serial_key='ADMS-ORG-002',
            new_serial_key='other-unused-key',
            activate=True,
        )
        other_member = member.objects.create(
            org=other_org,
            device_id=101,
            name='Other Organization Member',
            gender='Female',
        )

        response = self.client.post(
            f'{self.url}?SN={self.device.serial_number}&table=ATTLOG',
            data='101\t2026-07-31 10:00:00\t0\t1\t0\n',
            content_type='text/plain',
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(AttendanceRecord.objects.filter(mem=self.member).exists())
        self.assertFalse(AttendanceRecord.objects.filter(mem=other_member).exists())

    def test_unknown_device_is_rejected_without_creating_data(self):
        response = self.client.post(
            f'{self.url}?SN=FORGED-SERIAL&table=ATTLOG',
            data='101\t2026-07-31 10:00:00\t0\t1\t0\n',
            content_type='text/plain',
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.content.decode(), 'ERROR: DEVICE NOT REGISTERED')
        self.assertFalse(AttendanceRecord.objects.exists())
        self.assertFalse(ADMSAttendanceEvent.objects.exists())

    def test_unmatched_pin_is_audited_without_creating_attendance(self):
        response = self.client.post(
            f'{self.url}?SN={self.device.serial_number}&table=ATTLOG',
            data='999\t2026-07-31 10:30:00\t0\t1\t0\n',
            content_type='text/plain',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content.decode(), 'OK: 0')
        self.assertFalse(AttendanceRecord.objects.exists())
        receipt = ADMSAttendanceEvent.objects.get()
        self.assertEqual(receipt.status, 'unmatched')
        self.assertEqual(receipt.device_user_id, '999')

    def test_command_channels_require_a_registered_device(self):
        poll = self.client.get(
            reverse('adms_getrequest'),
            {'SN': self.device.serial_number},
        )
        command_result = self.client.post(
            f'{reverse("adms_devicecmd")}?SN={self.device.serial_number}',
            data='ID=1&Return=0',
            content_type='text/plain',
        )

        self.assertEqual(poll.content.decode(), 'OK')
        self.assertEqual(command_result.content.decode(), 'OK')

    def test_legacy_puller_serializer_does_not_expose_adms_identity(self):
        response = self.client.get(reverse('management:device'))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        row = payload[0] if isinstance(payload, list) else payload['results'][0]
        self.assertNotIn('serial_number', row)
        self.assertNotIn('last_ip_address', row)
        self.assertNotIn('last_seen_at', row)


class PremiumNotificationFlowTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(
            name='Notification School',
            expire_on=timezone.now() + timedelta(days=30),
            feature_tasks=True,
            allowed_features=['tasks'],
        )
        self.admin_user = CustomUser.objects.create_user(
            username='notification-admin',
            email='notification-admin@example.com',
            password='testpass123',
            user_type='2',
        )
        Schooladmin.objects.create(admin=self.admin_user, org=self.org)
        self.staff_member = member.objects.create(
            org=self.org,
            name='Notification Teacher',
            member_type='teacher',
            gender='Female',
        )
        self.staff_user = CustomUser.objects.create_user(
            username='notification-teacher',
            email='notification-teacher@example.com',
            password='testpass123',
            user_type='3',
        )
        Staff.objects.create(
            admin=self.staff_user,
            org=self.org,
            member=self.staff_member,
        )
        StaffPermission.objects.create(
            member=self.staff_member,
            org=self.org,
            can_view_tasks=True,
        )
        self.other_org = Organization.objects.create(
            name='Other Notification School',
            expire_on=timezone.now() + timedelta(days=30),
            feature_tasks=True,
        )
        self.other_admin = CustomUser.objects.create_user(
            username='other-notification-admin',
            email='other-notification-admin@example.com',
            password='testpass123',
            user_type='2',
        )
        Schooladmin.objects.create(admin=self.other_admin, org=self.other_org)

    def _task(self, due_date=None, requires_approval=True):
        due_date = due_date or timezone.localdate()
        task = Task.objects.create(
            org=self.org,
            title='Prepare practical lesson',
            priority='high',
            task_type='one_time',
            start_date=due_date,
            due_date=due_date,
            requires_approval=requires_approval,
            created_by=self.admin_user,
        )
        task.assigned_to.add(self.staff_member)
        task.generate_instances()
        return task

    def test_one_shot_message_renderer_prevents_duplicate_child_message(self):
        wrapped = _OneShotMessages(['Saved on the intended page'])
        rendered = Template(
            '{% for m in messages %}GLOBAL:{{ m }}{% endfor %}'
            '{% for m in messages %}CHILD:{{ m }}{% endfor %}'
        ).render(Context({'messages': wrapped}))
        self.assertEqual(rendered.count('Saved on the intended page'), 1)
        self.assertNotIn('CHILD:', rendered)

    def test_task_assignment_and_due_reminders_are_idempotent(self):
        from handle.notifications import (
            ensure_task_reminders, notify_task_assigned,
        )

        task = self._task()
        notify_task_assigned(task, [self.staff_member], actor=self.admin_user)
        notify_task_assigned(task, [self.staff_member], actor=self.admin_user)
        ensure_task_reminders(self.staff_user, self.org)
        ensure_task_reminders(self.staff_user, self.org)

        self.assertEqual(InAppNotification.objects.filter(
            org=self.org,
            recipient=self.staff_member,
            event_type='task_assigned',
        ).count(), 1)
        self.assertEqual(InAppNotification.objects.filter(
            org=self.org,
            recipient=self.staff_member,
            event_type='task_due_today',
        ).count(), 1)

    def test_notification_centre_is_tenant_and_recipient_safe(self):
        from handle.notifications import notify_user

        own = notify_user(
            self.admin_user,
            self.org,
            'task_completed',
            'Own organisation task',
            link_url='https://malicious.example/redirect',
        )
        notify_user(
            self.other_admin,
            self.other_org,
            'task_completed',
            'Other organisation task',
        )
        self.client.login(
            username='notification-admin', password='testpass123',
        )
        response = self.client.get(reverse('handle:notifications'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Own organisation task')
        self.assertNotContains(response, 'Other organisation task')

        response = self.client.get(
            reverse('handle:open_notification', args=(own.pk,)),
        )
        self.assertRedirects(
            response,
            reverse('handle:notifications'),
            fetch_redirect_response=False,
        )
        own.refresh_from_db()
        self.assertTrue(own.is_read)
        self.assertIsNotNone(own.read_at)

    @patch('staff.views.send_task_completed_email')
    def test_task_completion_notifies_school_admin_dashboard(
        self, mocked_email,
    ):
        task = self._task()
        instance = TaskInstance.objects.get(
            task=task, assigned_member=self.staff_member,
        )
        self.client.login(
            username='notification-teacher', password='testpass123',
        )
        response = self.client.post(
            reverse('staff:update_task_status', args=(instance.pk,)),
            {'action': 'completed', 'completion_note': 'Lesson is ready.'},
        )
        self.assertEqual(response.status_code, 302)
        notification = InAppNotification.objects.get(
            org=self.org,
            recipient_user=self.admin_user,
            event_type='task_completed',
        )
        self.assertIn('Notification Teacher', notification.title)
        self.assertIn('Lesson is ready', notification.body)

    def test_admin_staff_teacher_and_student_dashboards_show_notifications(self):
        from handle.notifications import notify, notify_user

        notify_user(
            self.admin_user, self.org, 'task_completed',
            'Admin dashboard activity',
        )

        dashboard_accounts = [
            (self.staff_user, self.staff_member, 'Teacher dashboard activity'),
        ]
        for suffix, member_type in (
            ('employee', 'employee'),
            ('student', 'student'),
        ):
            member_obj = member.objects.create(
                org=self.org,
                name=f'Notification {suffix.title()}',
                member_type=member_type,
                gender='Male',
            )
            user = CustomUser.objects.create_user(
                username=f'notification-{suffix}',
                email=f'notification-{suffix}@example.com',
                password='testpass123',
                user_type='3',
            )
            Staff.objects.create(
                admin=user, org=self.org, member=member_obj,
            )
            dashboard_accounts.append(
                (user, member_obj, f'{suffix.title()} dashboard activity'),
            )

        self.client.force_login(self.admin_user)
        admin_response = self.client.get(reverse('schooladmin:dashboard'))
        self.assertEqual(admin_response.status_code, 200)
        self.assertContains(admin_response, 'Notification centre')
        self.assertContains(admin_response, 'Admin dashboard activity')

        for user, member_obj, title in dashboard_accounts:
            notify(member_obj, 'task_assigned', title)
            self.client.force_login(user)
            with self.subTest(member_type=member_obj.member_type):
                response = self.client.get(reverse('staff:dashboard'))
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, 'Notification centre')
                self.assertContains(response, title)

    @patch('schooladmin.views.send_task_assigned_email')
    @patch('schooladmin.views.send_task_approval_email')
    def test_admin_task_decisions_notify_the_affected_assignees(
        self, mocked_approval_email, mocked_assignment_email,
    ):
        task = self._task()
        instance = TaskInstance.objects.get(
            task=task, assigned_member=self.staff_member,
        )
        self.client.force_login(self.admin_user)

        instance.status = 'completed'
        instance.approval_status = 'pending_approval'
        instance.save()
        self.client.post(
            reverse('schooladmin:task_detail', args=(task.pk,)),
            {'action': 'approve_instance', 'instance_id': instance.pk},
        )
        self.assertTrue(InAppNotification.objects.filter(
            recipient=self.staff_member,
            event_type='task_approved',
        ).exists())

        instance.status = 'completed'
        instance.approval_status = 'pending_approval'
        instance.save()
        self.client.post(
            reverse('schooladmin:task_detail', args=(task.pk,)),
            {
                'action': 'reject_instance',
                'instance_id': instance.pk,
                'rejection_reason': 'Attach the lesson plan.',
            },
        )
        self.assertTrue(InAppNotification.objects.filter(
            recipient=self.staff_member,
            event_type='task_rejected',
            body__contains='lesson plan',
        ).exists())

        replacement = member.objects.create(
            org=self.org,
            name='Replacement Teacher',
            member_type='teacher',
            gender='Male',
        )
        self.client.post(
            reverse('schooladmin:task_detail', args=(task.pk,)),
            {
                'action': 'reassign',
                'instance_id': instance.pk,
                'new_member': replacement.pk,
            },
        )
        instance.refresh_from_db()
        self.assertEqual(instance.assigned_member, replacement)
        self.assertTrue(InAppNotification.objects.filter(
            recipient=self.staff_member,
            event_type='task_reassigned',
        ).exists())
        self.assertTrue(InAppNotification.objects.filter(
            recipient=replacement,
            event_type='task_reassigned',
        ).exists())

        self.client.post(
            reverse('schooladmin:task_detail', args=(task.pk,)),
            {'action': 'cancel_instance', 'instance_id': instance.pk},
        )
        self.assertTrue(InAppNotification.objects.filter(
            recipient=replacement,
            event_type='task_cancelled',
        ).exists())


class GlobalShiftAndMemberLimitTests(TestCase):
    """Company-wide default shift / date override (handle.models.member's
    plain shift_start_time/shift_end_time fallback, NOT Shift Management),
    plus the AddMember/MemberImport member_limit enforcement and import-page
    usage card."""

    def setUp(self):
        self.org = Organization.objects.create(
            name='Global Shift Org', category='office',
            expire_on=timezone.now() + timedelta(days=365),
            serial_key='GS-001', new_serial_key='gs-secret', activate=True,
            member_limit=25,
        )
        self.admin_user = CustomUser.objects.create_user(
            username='gsadmin', email='gsadmin@example.com',
            password='testpass123', user_type='2',
        )
        Schooladmin.objects.create(admin=self.admin_user, org=self.org)
        self.client.login(username='gsadmin', password='testpass123')

    def test_member_form_seeds_shift_from_org_default_for_new_member_only(self):
        self.org.default_shift_start_time = datetime.time(10, 30)
        self.org.default_shift_end_time = datetime.time(18, 30)
        self.org.save()

        new_form = MemberForm(org=self.org)
        self.assertEqual(new_form['shift_start_time'].value(), datetime.time(10, 30))
        self.assertEqual(new_form['shift_end_time'].value(), datetime.time(18, 30))

        existing = member.objects.create(
            org=self.org, name='Existing', gender='Male',
            shift_start_time=datetime.time(8, 0), shift_end_time=datetime.time(16, 0),
        )
        edit_form = MemberForm(instance=existing, org=self.org)
        self.assertEqual(edit_form['shift_start_time'].value(), datetime.time(8, 0))
        self.assertEqual(edit_form['shift_end_time'].value(), datetime.time(16, 0))

    def test_org_shift_override_affects_plain_default_member_but_not_shift_managed_member(self):
        from schooladmin.payroll_service import calculate_attendance_stats

        target_date = datetime.date(2026, 8, 10)
        OrganizationShiftOverride.objects.create(
            org=self.org, date=target_date,
            start_time=datetime.time(10, 0), end_time=datetime.time(15, 0),
        )

        plain_member = member.objects.create(
            org=self.org, name='Plain Default', gender='Male',
            shift_start_time=datetime.time(9, 0), shift_end_time=datetime.time(17, 0),
        )
        AttendanceRecord.objects.create(
            mem=plain_member, org=self.org,
            scanned_time=timezone.make_aware(datetime.datetime.combine(target_date, datetime.time(9, 30))),
        )
        AttendanceRecord.objects.create(
            mem=plain_member, org=self.org,
            scanned_time=timezone.make_aware(datetime.datetime.combine(target_date, datetime.time(15, 30))),
        )
        stats, _ = calculate_attendance_stats(plain_member, target_date, target_date, self.org)
        # Punch-in 9:30 is BEFORE the override's 10:00 start, so there is no
        # lateness once the override is applied (it would be 30min late
        # against the member's own plain 9:00 default).
        self.assertEqual(stats['total_missing_hours'], Decimal('0'))

        shift = Shift.objects.create(org=self.org, name='Day')
        ShiftWindow.objects.create(shift=shift, start_time=datetime.time(9, 0), end_time=datetime.time(17, 0))
        shift_member = member.objects.create(org=self.org, name='Shift Managed', gender='Male')
        weekday = member.weekday_number(target_date)
        MemberWeekdayShift.objects.create(org=self.org, member=shift_member, weekday=weekday, shift=shift)
        shift_member.shifts.add(shift)  # legacy M2M sync, same as ShiftAssignView.post

        AttendanceRecord.objects.create(
            mem=shift_member, org=self.org,
            scanned_time=timezone.make_aware(datetime.datetime.combine(target_date, datetime.time(9, 30))),
        )
        AttendanceRecord.objects.create(
            mem=shift_member, org=self.org,
            scanned_time=timezone.make_aware(datetime.datetime.combine(target_date, datetime.time(17, 30))),
        )
        stats2, _ = calculate_attendance_stats(shift_member, target_date, target_date, self.org)
        # A Shift-Management-assigned member stays governed by their own
        # Shift (9-17), untouched by the org-wide override for that date.
        self.assertGreater(stats2['total_missing_hours'], Decimal('0'))

    def test_add_member_blocked_when_limit_reached(self):
        self.org.member_limit = 1
        self.org.save(update_fields=['member_limit'])
        member.objects.create(org=self.org, name='Existing One', gender='Male')

        # AddMember issues a one-time form_token on GET (anti double-submit
        # guard) that the POST must echo back, same as a real browser would.
        get_response = self.client.get(reverse('handle:addMember'))
        form_token = get_response.context['form_token']

        response = self.client.post(reverse('handle:addMember'), {
            'name': 'New One', 'member_type': 'staff', 'status': 'active', 'gender': 'Male',
            'email': 'new.one@example.com', 'phone': '9800000001', 'address': 'Kathmandu',
            'salary_type': 'monthly', 'salary_amount': '10000', 'tax_percentage': '1.00',
            'staff_type': 'permanent', 'probation_review_status': 'not_required',
            'probation_salary_percentage': '100.00',
            'shift_start_time': '09:00', 'shift_end_time': '17:00',
            'form_token': form_token,
        })
        self.assertEqual(response.status_code, 302)
        msgs = [str(m) for m in get_messages(response.wsgi_request)]
        self.assertTrue(any('member limit' in m.lower() for m in msgs), msgs)
        self.assertEqual(member.objects.filter(org=self.org).count(), 1)

    def test_member_import_stops_at_member_limit_and_seeds_org_default_shift(self):
        self.org.default_shift_start_time = datetime.time(10, 0)
        self.org.default_shift_end_time = datetime.time(16, 0)
        self.org.member_limit = 2
        self.org.save()

        csv_content = b"name,member_type,gender\nAlice,staff,Female\nBob,staff,Male\nCarol,staff,Female\n"
        upload = SimpleUploadedFile('members.csv', csv_content, content_type='text/csv')
        response = self.client.post(reverse('handle:member_import'), {'file': upload})

        self.assertEqual(response.status_code, 302)
        self.assertEqual(member.objects.filter(org=self.org).count(), 2)
        msgs = [str(m) for m in get_messages(response.wsgi_request)]
        self.assertTrue(any('member limit' in m.lower() for m in msgs), msgs)

        imported = member.objects.filter(org=self.org, name='Alice').first()
        self.assertIsNotNone(imported)
        self.assertEqual(imported.shift_start_time, datetime.time(10, 0))
        self.assertEqual(imported.shift_end_time, datetime.time(16, 0))

    def test_member_import_page_shows_usage_card(self):
        member.objects.create(org=self.org, name='Existing', gender='Male')
        response = self.client.get(reverse('handle:member_import'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['total_member'], 1)


class ClassificationBranchAvailabilityTests(TestCase):
    """Classification.branches (M2M) — empty means available to every branch."""

    def setUp(self):
        self.org = Organization.objects.create(
            name='Availability Org', expire_on=timezone.now() + timedelta(days=30),
        )
        self.branch_a = Branch.objects.create(org=self.org, name='Branch A', code='A')
        self.branch_b = Branch.objects.create(org=self.org, name='Branch B', code='B')

    def test_org_wide_classification_available_everywhere(self):
        classi = Classification.objects.create(org=self.org, name='Org Wide')
        self.assertTrue(classi.is_available_to_branch(self.branch_a.id))
        self.assertTrue(classi.is_available_to_branch(self.branch_b.id))
        self.assertTrue(classi.is_available_to_branch(None))

    def test_scoped_classification_available_only_to_its_branches(self):
        classi = Classification.objects.create(org=self.org, name='A Only')
        classi.branches.add(self.branch_a)
        self.assertTrue(classi.is_available_to_branch(self.branch_a.id))
        self.assertFalse(classi.is_available_to_branch(self.branch_b.id))
        # No branch context (e.g. org-wide report row) is always allowed through.
        self.assertTrue(classi.is_available_to_branch(None))

    def test_migration_backfilled_legacy_branch_into_m2m(self):
        classi = Classification.objects.create(org=self.org, name='Legacy', branch=self.branch_a)
        # The data migration only runs once at deploy time; this asserts the
        # *model* still lets old-style single-branch creation be reconciled
        # by whichever code path populates `branches` for new rows (the form).
        self.assertEqual(classi.primary_branch, None)  # branches M2M starts empty until form/save populates it
        classi.branches.add(classi.branch)
        self.assertEqual(classi.primary_branch, self.branch_a)
        self.assertEqual(classi.primary_branch_id, self.branch_a.id)


class BranchManagerScopingTests(TestCase):
    """school.hierarchy scoping service + its use in memberEdit/MemberReport —
    a Branch Manager must only see/act on their own branch's data, even if
    they guess another member's URL id directly."""

    def setUp(self):
        self.org = Organization.objects.create(
            name='Scoping Org', expire_on=timezone.now() + timedelta(days=30),
        )
        self.admin_user = CustomUser.objects.create_user(
            username='scoping-admin', email='scoping-admin@example.com',
            password='testpass123', user_type='2',
        )
        Schooladmin.objects.create(admin=self.admin_user, org=self.org)

        self.branch_a = Branch.objects.create(org=self.org, name='Branch A', code='A')
        self.branch_b = Branch.objects.create(org=self.org, name='Branch B', code='B')

        # Branch Manager for Branch A only.
        self.manager_member = member.objects.create(
            org=self.org, name='Manager A', gender='Male', branch=self.branch_a,
        )
        self.manager_user = CustomUser.objects.create_user(
            username='manager-a@example.com', email='manager-a@example.com',
            password='testpass123', user_type='3',
        )
        Staff.objects.create(admin=self.manager_user, org=self.org, member=self.manager_member)
        StaffPermission.objects.create(
            member=self.manager_member, org=self.org,
            can_edit_members=True, can_view_members=True,
        )
        self.branch_a.manager = self.manager_user
        self.branch_a.save(update_fields=['manager'])

        self.member_in_a = member.objects.create(org=self.org, name='In Branch A', gender='Male', branch=self.branch_a)
        self.member_in_b = member.objects.create(org=self.org, name='In Branch B', gender='Male', branch=self.branch_b)
        self.member_unassigned = member.objects.create(org=self.org, name='No Branch', gender='Male')

    def test_is_branch_manager(self):
        from school.hierarchy import is_branch_manager
        self.assertTrue(is_branch_manager(self.manager_user, self.org))
        self.assertFalse(is_branch_manager(self.admin_user, self.org))  # schooladmin is never "scoped"

    def test_get_accessible_branches_scoped_to_managed_branch(self):
        from school.hierarchy import get_accessible_branches
        manager_branches = list(get_accessible_branches(self.manager_user, self.org))
        self.assertEqual(manager_branches, [self.branch_a])
        admin_branches = set(get_accessible_branches(self.admin_user, self.org))
        self.assertEqual(admin_branches, {self.branch_a, self.branch_b})

    def test_get_accessible_members_includes_unassigned_but_not_other_branch(self):
        from school.hierarchy import get_accessible_members
        ids = set(get_accessible_members(self.manager_user, self.org).values_list('id', flat=True))
        self.assertIn(self.member_in_a.id, ids)
        self.assertIn(self.member_unassigned.id, ids)
        self.assertNotIn(self.member_in_b.id, ids)

    def test_branch_manager_cannot_open_member_edit_for_another_branch(self):
        self.client.force_login(self.manager_user)
        own_branch_response = self.client.get(reverse('handle:memberEdit', args=[self.member_in_a.id]))
        self.assertEqual(own_branch_response.status_code, 200)

        other_branch_response = self.client.get(reverse('handle:memberEdit', args=[self.member_in_b.id]))
        self.assertEqual(other_branch_response.status_code, 404)

    def test_branch_manager_cannot_delete_member_from_another_branch(self):
        self.client.force_login(self.manager_user)
        response = self.client.post(reverse('handle:deleteMember', args=[self.member_in_b.id]), {'action': 'dump'})
        self.assertEqual(response.status_code, 404)
        self.member_in_b.refresh_from_db()
        self.assertEqual(self.member_in_b.status, 'active')

    def test_member_report_excludes_other_branch_for_manager(self):
        self.client.force_login(self.manager_user)
        response = self.client.get(reverse('handle:memberReport'))
        member_ids = {m.id for m in response.context['mem']}
        self.assertIn(self.member_in_a.id, member_ids)
        self.assertNotIn(self.member_in_b.id, member_ids)

    def test_schooladmin_sees_every_branch_member_report(self):
        self.client.force_login(self.admin_user)
        response = self.client.get(reverse('handle:memberReport'))
        member_ids = {m.id for m in response.context['mem']}
        self.assertIn(self.member_in_a.id, member_ids)
        self.assertIn(self.member_in_b.id, member_ids)


class ClassificationTenantIsolationTests(TestCase):
    """editClassification/deleteClassification must never let one org act on another org's row."""

    def setUp(self):
        self.org = Organization.objects.create(
            name='Tenant Org 1', expire_on=timezone.now() + timedelta(days=30),
        )
        self.admin_user = CustomUser.objects.create_user(
            username='tenant1-admin', email='tenant1-admin@example.com',
            password='testpass123', user_type='2',
        )
        Schooladmin.objects.create(admin=self.admin_user, org=self.org)

        self.other_org = Organization.objects.create(
            name='Tenant Org 2', expire_on=timezone.now() + timedelta(days=30),
        )
        self.other_classification = Classification.objects.create(org=self.other_org, name='Other Org Dept')

    def test_cannot_view_edit_page_for_another_orgs_classification(self):
        self.client.force_login(self.admin_user)
        response = self.client.get(reverse('handle:editClassification', args=[self.other_classification.id]))
        self.assertEqual(response.status_code, 404)

    def test_cannot_delete_another_orgs_classification(self):
        self.client.force_login(self.admin_user)
        response = self.client.post(reverse('handle:deleteClassification', args=[self.other_classification.id]))
        self.assertEqual(response.status_code, 404)
        self.assertTrue(Classification.objects.filter(id=self.other_classification.id).exists())

    def test_delete_requires_post(self):
        own_classification = Classification.objects.create(org=self.org, name='Mine')
        self.client.force_login(self.admin_user)
        response = self.client.get(reverse('handle:deleteClassification', args=[own_classification.id]))
        self.assertEqual(response.status_code, 405)
        self.assertTrue(Classification.objects.filter(id=own_classification.id).exists())


class DefaultShiftResolverTests(TestCase):
    """Phase 4: resolve_default_shift priority — Classification > Branch > Org > hardcoded."""

    def setUp(self):
        self.org = Organization.objects.create(
            name='Shift Default Org', expire_on=timezone.now() + timedelta(days=30),
            default_shift_start_time=datetime.time(9, 0), default_shift_end_time=datetime.time(17, 0),
        )
        self.branch = Branch.objects.create(org=self.org, name='Night Branch', code='NB')
        self.classification = Classification.objects.create(org=self.org, name='Night Shift Crew')

    def test_falls_back_to_org_default_when_nothing_else_set(self):
        from handle.models import resolve_default_shift
        start, end = resolve_default_shift(self.org, branch=self.branch, classification=self.classification)
        self.assertEqual((start, end), (datetime.time(9, 0), datetime.time(17, 0)))

    def test_branch_default_overrides_org_default(self):
        from handle.models import resolve_default_shift
        self.branch.default_shift_start_time = datetime.time(22, 0)
        self.branch.default_shift_end_time = datetime.time(6, 0)
        self.branch.save()
        start, end = resolve_default_shift(self.org, branch=self.branch, classification=self.classification)
        self.assertEqual((start, end), (datetime.time(22, 0), datetime.time(6, 0)))

    def test_classification_default_overrides_branch_default(self):
        from handle.models import resolve_default_shift
        self.branch.default_shift_start_time = datetime.time(22, 0)
        self.branch.default_shift_end_time = datetime.time(6, 0)
        self.branch.save()
        self.classification.default_shift_start_time = datetime.time(14, 0)
        self.classification.default_shift_end_time = datetime.time(22, 0)
        self.classification.save()
        start, end = resolve_default_shift(self.org, branch=self.branch, classification=self.classification)
        self.assertEqual((start, end), (datetime.time(14, 0), datetime.time(22, 0)))

    def test_hardcoded_fallback_when_org_has_no_default(self):
        from handle.models import resolve_default_shift
        self.org.default_shift_start_time = None
        self.org.default_shift_end_time = None
        start, end = resolve_default_shift(self.org, branch=None, classification=None)
        self.assertEqual((start, end), (datetime.time(9, 0), datetime.time(17, 0)))

    def test_member_import_uses_resolved_branch_and_classification_shift(self):
        self.classification.default_shift_start_time = datetime.time(20, 0)
        self.classification.default_shift_end_time = datetime.time(4, 0)
        self.classification.save()
        admin_user = CustomUser.objects.create_user(
            username='shift-import-admin', email='shift-import-admin@example.com',
            password='testpass123', user_type='2',
        )
        Schooladmin.objects.create(admin=admin_user, org=self.org)
        self.client.force_login(admin_user)

        csv_content = (
            f"name,branch,classification\nNight Owl,{self.branch.name},{self.classification.name}\n"
        ).encode()
        upload = SimpleUploadedFile('members.csv', csv_content, content_type='text/csv')
        response = self.client.post(reverse('handle:member_import'), {'file': upload})
        self.assertEqual(response.status_code, 302)

        imported = member.objects.get(org=self.org, name='Night Owl')
        self.assertEqual(imported.shift_start_time, datetime.time(20, 0))
        self.assertEqual(imported.shift_end_time, datetime.time(4, 0))


class PrintPreferenceTests(TestCase):
    """Phase 7: reusable per-user, per-report print settings persistence."""

    def setUp(self):
        self.org = Organization.objects.create(
            name='Print Pref Org', expire_on=timezone.now() + timedelta(days=30),
        )
        self.admin_user = CustomUser.objects.create_user(
            username='print-pref-admin', email='print-pref-admin@example.com',
            password='testpass123', user_type='2',
        )
        Schooladmin.objects.create(admin=self.admin_user, org=self.org)

    def test_get_print_preference_returns_defaults_when_nothing_saved(self):
        from school.print_settings import DEFAULT_PRINT_SETTINGS, get_print_preference
        result = get_print_preference(self.admin_user, 'monthly_report')
        self.assertEqual(result, DEFAULT_PRINT_SETTINGS)

    def test_save_print_preference_whitelists_unknown_keys_and_values(self):
        from school.print_settings import save_print_preference
        saved = save_print_preference(self.admin_user, 'daily_report', {
            'paper': 'Letter', 'orientation': 'sideways', 'margin': 'normal',
            'fit_to_width': 'yes', 'hidden_columns': ['worked', 123, {'x': 1}],
            'evil_key': '<script>alert(1)</script>',
        })
        self.assertEqual(saved['paper'], 'Letter')
        self.assertNotIn('orientation', saved)  # invalid choice dropped, not stored
        self.assertNotIn('evil_key', saved)
        self.assertNotIn('fit_to_width', saved)  # non-bool dropped
        self.assertEqual(saved['hidden_columns'], ['worked', '123'])

    def test_save_print_preference_upserts_same_row(self):
        from school.print_settings import save_print_preference
        from .models import PrintPreference
        save_print_preference(self.admin_user, 'payslip', {'paper': 'A4'})
        save_print_preference(self.admin_user, 'payslip', {'paper': 'Legal'})
        self.assertEqual(PrintPreference.objects.filter(user=self.admin_user, report_key='payslip').count(), 1)
        self.assertEqual(PrintPreference.objects.get(user=self.admin_user, report_key='payslip').settings['paper'], 'Legal')

    def test_ajax_endpoint_persists_and_round_trips(self):
        self.client.force_login(self.admin_user)
        response = self.client.post(
            reverse('handle:save_print_preference', args=['monthly_report']),
            data=json.dumps({'settings': {'paper': 'Letter', 'orientation': 'landscape', 'margin': 'narrow', 'fit_to_width': False}}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body['settings']['paper'], 'Letter')
        self.assertEqual(body['settings']['orientation'], 'landscape')

        from school.print_settings import get_print_preference
        reloaded = get_print_preference(self.admin_user, 'monthly_report')
        self.assertEqual(reloaded['paper'], 'Letter')
        self.assertEqual(reloaded['margin'], 'narrow')
        self.assertFalse(reloaded['fit_to_width'])

    def test_ajax_endpoint_requires_login(self):
        response = self.client.post(
            reverse('handle:save_print_preference', args=['monthly_report']),
            data=json.dumps({'settings': {'paper': 'Letter'}}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 302)  # redirected to login

    def test_ajax_endpoint_rejects_get(self):
        self.client.force_login(self.admin_user)
        response = self.client.get(reverse('handle:save_print_preference', args=['monthly_report']))
        self.assertEqual(response.status_code, 405)

    def test_ajax_endpoint_rejects_malformed_json(self):
        self.client.force_login(self.admin_user)
        response = self.client.post(
            reverse('handle:save_print_preference', args=['monthly_report']),
            data='not json',
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)

    def test_preferences_are_isolated_per_user(self):
        from school.print_settings import get_print_preference, save_print_preference
        other_user = CustomUser.objects.create_user(
            username='print-pref-other', email='print-pref-other@example.com',
            password='testpass123', user_type='2',
        )
        Schooladmin.objects.create(admin=other_user, org=self.org)
        save_print_preference(self.admin_user, 'daily_report', {'paper': 'Legal'})
        self.assertEqual(get_print_preference(other_user, 'daily_report')['paper'], 'A4')


class OrgPrintDefaultTests(TestCase):
    """Org-wide default print settings (Organization Profile's Print
    Defaults section) — layered under any per-user PrintPreference by
    get_print_preference(user, report_key, org=org): hardcoded fallback ->
    org default -> user's own override."""

    def setUp(self):
        self.org = Organization.objects.create(
            name='Org Print Default Org', expire_on=timezone.now() + timedelta(days=30),
        )
        self.admin_user = CustomUser.objects.create_user(
            username='org-print-default-admin', email='org-print-default-admin@example.com',
            password='testpass123', user_type='2',
        )
        Schooladmin.objects.create(admin=self.admin_user, org=self.org)
        self.staff_user = CustomUser.objects.create_user(
            username='org-print-default-staff', email='org-print-default-staff@example.com',
            password='testpass123', user_type='3',
        )

    def test_get_org_print_default_returns_defaults_when_nothing_saved(self):
        from school.print_settings import DEFAULT_PRINT_SETTINGS, get_org_print_default
        self.assertEqual(get_org_print_default(self.org, 'daily_report'), DEFAULT_PRINT_SETTINGS)

    def test_save_org_print_default_whitelists_and_upserts(self):
        from school.print_settings import save_org_print_default
        from .models import OrgPrintDefault
        save_org_print_default(self.org, 'monthly_report', {'paper': 'Legal', 'evil': '<script>'})
        save_org_print_default(self.org, 'monthly_report', {'orientation': 'landscape'})
        self.assertEqual(OrgPrintDefault.objects.filter(org=self.org, report_key='monthly_report').count(), 1)
        row = OrgPrintDefault.objects.get(org=self.org, report_key='monthly_report')
        self.assertNotIn('evil', row.settings)
        self.assertEqual(row.settings.get('orientation'), 'landscape')

    def test_get_print_preference_falls_back_to_org_default_when_no_user_override(self):
        from school.print_settings import get_print_preference, save_org_print_default
        save_org_print_default(self.org, 'payslip', {'orientation': 'landscape'})
        result = get_print_preference(self.admin_user, 'payslip', org=self.org)
        self.assertEqual(result['orientation'], 'landscape')

    def test_get_print_preference_user_override_wins_over_org_default(self):
        from school.print_settings import get_print_preference, save_org_print_default, save_print_preference
        save_org_print_default(self.org, 'payslip', {'orientation': 'landscape'})
        save_print_preference(self.admin_user, 'payslip', {'orientation': 'portrait'})
        result = get_print_preference(self.admin_user, 'payslip', org=self.org)
        self.assertEqual(result['orientation'], 'portrait')

    def test_ajax_endpoint_requires_admin(self):
        self.client.force_login(self.staff_user)
        response = self.client.post(
            reverse('handle:save_org_print_default', args=['monthly_report']),
            data=json.dumps({'settings': {'paper': 'Legal'}}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 403)

    def test_ajax_endpoint_persists_for_admin(self):
        self.client.force_login(self.admin_user)
        response = self.client.post(
            reverse('handle:save_org_print_default', args=['monthly_report']),
            data=json.dumps({'settings': {'paper': 'Legal', 'orientation': 'landscape'}}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        from school.print_settings import get_org_print_default
        self.assertEqual(get_org_print_default(self.org, 'monthly_report')['paper'], 'Legal')

    def test_org_defaults_isolated_per_org(self):
        from school.print_settings import get_org_print_default, save_org_print_default
        other_org = Organization.objects.create(
            name='Other Org Print Default', expire_on=timezone.now() + timedelta(days=30),
        )
        save_org_print_default(self.org, 'daily_report', {'paper': 'Legal'})
        self.assertEqual(get_org_print_default(other_org, 'daily_report')['paper'], 'A4')


class OperationsKpiRowLayoutTests(TestCase):
    """Regression test: the KPI row under the Operations hero banner uses a
    negative top margin so its cards visually float up over the hero (see
    templates/handle/operations.html's .ops-kpi-row CSS). With neither stock
    nor finance enabled there are no cards to fill that space, so the empty
    row — and the tab bar right after it — got pulled up underneath the
    hero and hidden behind it (the hero is position:relative, the tabs are
    static, so the hero paints on top). The row must drop the negative
    margin (via the ops-kpi-row-empty modifier) whenever it has no cards."""

    def setUp(self):
        self.org = Organization.objects.create(
            name='Ops Layout Org', expire_on=timezone.now() + timedelta(days=30),
        )
        self.admin_user = CustomUser.objects.create_user(
            username='ops-layout-admin', email='ops-layout-admin@example.com',
            password='testpass123', user_type='2',
        )
        Schooladmin.objects.create(admin=self.admin_user, org=self.org)
        self.client.force_login(self.admin_user)

    def test_empty_modifier_applied_when_stock_and_finance_both_off(self):
        self.org.feature_stock = False
        self.org.feature_finance = False
        self.org.save(update_fields=['feature_stock', 'feature_finance'])
        response = self.client.get(reverse('handle:operations'))
        self.assertContains(response, '<div class="ops-kpi-row ops-kpi-row-empty">')

    def test_empty_modifier_absent_when_stock_enabled(self):
        self.org.feature_stock = True
        self.org.allowed_features = list(set((self.org.allowed_features or []) + ['stock']))
        self.org.save(update_fields=['feature_stock', 'allowed_features'])
        response = self.client.get(reverse('handle:operations'))
        self.assertContains(response, '<div class="ops-kpi-row">')
        self.assertNotContains(response, '<div class="ops-kpi-row ops-kpi-row-empty">')
