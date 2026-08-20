import datetime
from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework_simplejwt.tokens import RefreshToken

from handle.models import (
    AcademicYear,
    Assignment,
    AssignmentSubmission,
    AttendingClassification,
    AttendanceRecord,
    AttendanceReminderPolicy,
    Branch,
    Bill,
    BillItem,
    Book,
    BookIssue,
    BusLocationPing,
    BusStudentTripStatus,
    BusTrackingSession,
    Client,
    ClientFollowUp,
    Classification,
    Complaint,
    ComplaintMessage,
    DynamicFeature,
    DynamicPermission,
    Event,
    ExamTerm,
    OrganizationFeatureGrant,
    Staff,
    StaffPermission,
    StaffPermissionGrant,
    Shift,
    ShiftWindow,
    QRAttendanceSession,
    FieldVisit,
    LiveTrackingSession,
    LocationPing,
    Notice,
    NoticeRead,
    Homework,
    HomeworkStatus,
    ResultRecord,
    RoutinePeriod,
    SchoolBus,
    SubjectAttendanceRecord,
    SubjectTeacherAssignment,
    Task,
    TaskInstance,
    TeachingLog,
    Course,
    Section,
    StudentCourseEnrollment,
    StudentBusAssignment,
    Subject,
    member,
)
from management.models import (
    CustomUser,
    Holiday,
    LeaveReport,
    Occasion,
    Organization,
)
from school.navigation import build_portal_navigation


class PortalAccessAndNavigationTests(TestCase):
    password = 'portal-test-pass'

    def setUp(self):
        self.org = Organization.objects.create(
            name='Portal Academy',
            category='school',
            expire_on=timezone.now() + timedelta(days=60),
            serial_key='PORTAL-001',
            new_serial_key='PORTAL-001-NEW',
            activate=True,
            feature_billing=True,
            feature_results=True,
            feature_tasks=True,
            feature_finance=True,
            feature_complaints=True,
            allowed_features=[
                'billing', 'results', 'tasks', 'finance', 'complaints',
            ],
        )
        self.student_member, self.student_user, self.student_permissions = (
            self._make_portal_user('student', 'Student One')
        )
        self.staff_member, self.staff_user, self.staff_permissions = (
            self._make_portal_user('employee', 'Staff One')
        )

    def _make_portal_user(self, member_type, name):
        suffix = member_type.replace('_', '-')
        memb = member.objects.create(
            org=self.org,
            name=name,
            member_type=member_type,
            gender='Male',
        )
        user = CustomUser.objects.create_user(
            username=f'{suffix}-portal-user',
            email=f'{suffix}-portal@example.com',
            password=self.password,
            user_type='3',
        )
        Staff.objects.create(admin=user, org=self.org, member=memb)
        permissions = StaffPermission.objects.create(
            member=memb,
            org=self.org,
            can_view_billing=False,
            can_view_result_report=False,
            can_view_finance=False,
            can_view_tasks=True,
        )
        return memb, user, permissions

    @staticmethod
    def _labels(navigation):
        return {
            link['label']
            for section in navigation
            for link in section['links']
        }

    def test_student_can_open_own_bills_without_staff_billing_permission(self):
        self.client.force_login(self.student_user)

        response = self.client.get(reverse('staff:student_bills'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'My Bills')

    def test_student_can_open_published_results_without_report_permission(self):
        self.client.force_login(self.student_user)

        response = self.client.get(reverse('staff:student_results'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'My Results')

    def test_non_student_cannot_open_student_self_service_pages(self):
        self.client.force_login(self.staff_user)

        for url_name in (
            'staff:student_bills',
            'staff:student_results',
            'staff:student_gaps',
            'staff:student_complaint',
        ):
            with self.subTest(url_name=url_name):
                response = self.client.get(reverse(url_name))
                self.assertRedirects(response, reverse('staff:dashboard'))

    def test_student_sidebar_uses_org_features_not_management_permissions(self):
        navigation, role, role_label = build_portal_navigation(
            self.student_user, self.org,
        )
        labels = self._labels(navigation)

        self.assertEqual(role, 'student')
        self.assertEqual(role_label, 'Student Portal')
        self.assertIn('My Bills', labels)
        self.assertIn('My Results', labels)
        self.assertIn('My Profile', labels)
        self.assertIn('Change Password', labels)
        self.assertNotIn('Finance Dashboard', labels)

    def test_student_sidebar_hides_disabled_org_feature(self):
        self.org.feature_results = False
        self.org.save(update_fields=['feature_results'])

        navigation, _, _ = build_portal_navigation(
            self.student_user, self.org,
        )

        self.assertNotIn('My Results', self._labels(navigation))

    def test_staff_sidebar_requires_both_feature_and_role_permission(self):
        navigation, role, _ = build_portal_navigation(
            self.staff_user, self.org,
        )
        self.assertEqual(role, 'staff')
        self.assertIn('My Profile', self._labels(navigation))
        self.assertIn('Change Password', self._labels(navigation))
        self.assertNotIn('Finance Dashboard', self._labels(navigation))

    def test_purchase_sale_permissions_are_visible_to_any_explicitly_assigned_role(self):
        self.org.feature_stock = True
        self.org.allowed_features = sorted(set(self.org.allowed_features + ['stock']))
        self.org.save(update_fields=['feature_stock', 'allowed_features'])
        self.student_permissions.can_view_purchases = True
        self.student_permissions.can_manage_sales_returns = True
        self.student_permissions.save(update_fields=[
            'can_view_purchases', 'can_manage_sales_returns',
        ])

        navigation, role, _ = build_portal_navigation(
            self.student_user, self.org,
        )
        labels = self._labels(navigation)

        self.assertEqual(role, 'student')
        self.assertIn('Purchases & Suppliers', labels)
        self.assertIn('Sales Returns', labels)
        self.assertNotIn('New Purchase', labels)

    def test_delegated_purchase_page_enforces_staff_permission(self):
        self.org.feature_stock = True
        self.org.allowed_features = sorted(set(self.org.allowed_features + ['stock']))
        self.org.save(update_fields=['feature_stock', 'allowed_features'])
        self.client.force_login(self.staff_user)

        denied = self.client.get(reverse('schooladmin:purchase_list'))
        self.staff_permissions.can_view_purchases = True
        self.staff_permissions.save(update_fields=['can_view_purchases'])
        allowed = self.client.get(reverse('schooladmin:purchase_list'))

        self.assertEqual(denied.status_code, 302)
        self.assertEqual(denied.url, '/')
        self.assertEqual(allowed.status_code, 200)

    def test_library_dynamic_permission_adds_navigation_and_backend_access(self):
        feature = DynamicFeature.objects.get(key='library')
        OrganizationFeatureGrant.objects.create(
            org=self.org, feature=feature, enabled=True,
        )
        permission = DynamicPermission.objects.get(flag='can_view_library')
        StaffPermissionGrant.objects.create(
            member=self.staff_member,
            permission=permission,
            granted=True,
        )
        self.client.force_login(self.staff_user)

        navigation, _, _ = build_portal_navigation(
            self.staff_user, self.org,
        )
        response = self.client.get(reverse('schooladmin:library_dashboard'))

        self.assertIn('Library Dashboard', self._labels(navigation))
        self.assertEqual(response.status_code, 200)

        self.staff_permissions.can_view_finance = True
        self.staff_permissions.save(update_fields=['can_view_finance'])
        navigation, _, _ = build_portal_navigation(
            self.staff_user, self.org,
        )
        self.assertIn('Finance Dashboard', self._labels(navigation))

        self.org.feature_finance = False
        self.org.save(update_fields=['feature_finance'])
        navigation, _, _ = build_portal_navigation(
            self.staff_user, self.org,
        )
        self.assertNotIn('Finance Dashboard', self._labels(navigation))

    def test_student_dashboard_renders_premium_self_service_workspace(self):
        self.client.force_login(self.student_user)

        response = self.client.get(reverse('staff:dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Student command centre')
        self.assertContains(response, 'student-workspace')
        self.assertContains(response, 'My Bills')
        self.assertContains(response, 'My Results')
        self.assertContains(response, 'My Profile')
        self.assertContains(response, 'Change Password')

    def test_mobile_bootstrap_returns_effective_role_scope_and_navigation(self):
        token = RefreshToken.for_user(self.student_user).access_token

        response = self.client.get(
            reverse('staff:api_my_permissions'),
            HTTP_AUTHORIZATION=f'Bearer {token}',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['schema_version'], 1)
        self.assertEqual(payload['role'], 'student')
        self.assertEqual(payload['organization']['id'], self.org.id)
        self.assertEqual(payload['member']['id'], self.student_member.id)
        self.assertTrue(payload['features']['billing'])
        self.assertFalse(payload['permissions']['can_view_billing'])
        self.assertIn(
            'My Bills',
            {
                item['label']
                for section in payload['navigation']
                for item in section['items']
            },
        )

    def test_mobile_bootstrap_filters_cross_organization_class_assignments(self):
        other_org = Organization.objects.create(
            name='Other Academy',
            category='school',
            expire_on=timezone.now() + timedelta(days=60),
            serial_key='OTHER-PORTAL-001',
            new_serial_key='OTHER-PORTAL-001-NEW',
            activate=True,
        )
        own_class = Classification.objects.create(
            org=self.org,
            name='Own Class',
        )
        foreign_class = Classification.objects.create(
            org=other_org,
            name='Foreign Class',
        )
        AttendingClassification.objects.create(
            staff=self.staff_user,
            classification=own_class,
        )
        AttendingClassification.objects.create(
            staff=self.staff_user,
            classification=foreign_class,
        )
        token = RefreshToken.for_user(self.staff_user).access_token

        response = self.client.get(
            reverse('staff:api_my_permissions'),
            HTTP_AUTHORIZATION=f'Bearer {token}',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()['assignments']['classifications'],
            [{'id': own_class.id, 'name': own_class.name}],
        )

    def test_mobile_api_returns_json_401_instead_of_login_redirect(self):
        response = self.client.get(reverse('staff:api_my_permissions'))

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response['Content-Type'], 'application/json')

    def test_mobile_attendance_status_uses_assigned_shift_and_policy(self):
        shift = Shift.objects.create(org=self.org, name='Morning Shift')
        ShiftWindow.objects.create(
            shift=shift,
            order=1,
            start_time=datetime.time(9, 0),
            end_time=datetime.time(17, 0),
        )
        self.staff_member.shifts.add(shift)
        AttendanceReminderPolicy.objects.create(
            org=self.org,
            checkin_offsets=[0, 10, 25, 40],
            checkout_offsets=[0, 15],
        )
        token = RefreshToken.for_user(self.staff_user).access_token

        response = self.client.get(
            reverse('staff:api_my_attendance_status'),
            HTTP_AUTHORIZATION=f'Bearer {token}',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['shift']['names'], ['Morning Shift'])
        self.assertEqual(payload['shift']['expected_punches'], 2)
        self.assertEqual(payload['attendance']['next_action'], 'check_in')
        self.assertEqual(len(payload['reminders']['checkin_times']), 3)
        self.assertEqual(payload['reminders']['checkout_times'], [])

    def test_mobile_attendance_status_suppresses_reminders_on_leave(self):
        LeaveReport.objects.create(
            org=self.org,
            member=self.staff_member,
            gap_start=timezone.localdate(),
            gap_end=timezone.localdate(),
            approved=True,
            reason='Approved leave',
        )
        token = RefreshToken.for_user(self.staff_user).access_token

        response = self.client.get(
            reverse('staff:api_my_attendance_status'),
            HTTP_AUTHORIZATION=f'Bearer {token}',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertFalse(payload['working_day'])
        self.assertEqual(payload['day_reason'], 'approved_leave')
        self.assertFalse(payload['reminders']['enabled'])

    def test_mobile_attendance_status_moves_to_checkout_after_first_punch(self):
        AttendanceRecord.objects.create(
            mem=self.staff_member,
            org=self.org,
            scanned_time=timezone.now(),
            attendance_method='wifi',
        )
        token = RefreshToken.for_user(self.staff_user).access_token

        response = self.client.get(
            reverse('staff:api_my_attendance_status'),
            HTTP_AUTHORIZATION=f'Bearer {token}',
        )

        payload = response.json()
        self.assertEqual(payload['attendance']['next_action'], 'check_out')
        self.assertEqual(payload['reminders']['checkin_times'], [])
        self.assertTrue(payload['reminders']['checkout_times'])

    def test_mobile_attendance_status_is_not_exposed_to_students(self):
        token = RefreshToken.for_user(self.student_user).access_token

        response = self.client.get(
            reverse('staff:api_my_attendance_status'),
            HTTP_AUTHORIZATION=f'Bearer {token}',
        )

        self.assertEqual(response.status_code, 403)

    def test_dynamic_qr_scan_uses_logged_in_member_and_rejects_camera_repeat(self):
        self.org.enable_qr_attendance = True
        self.org.save(update_fields=['enable_qr_attendance'])
        now = timezone.now()
        session = QRAttendanceSession.objects.create(
            org=self.org,
            generated_by=self.staff_user,
            token='secure-mobile-session',
            valid_from=now - timedelta(minutes=1),
            expires_at=now + timedelta(minutes=5),
            date=timezone.localdate(),
        )
        token = RefreshToken.for_user(self.staff_user).access_token

        first = self.client.post(
            reverse('staff:api_qr_attendance_scan'),
            data={'token': session.token, 'member_id': self.student_member.id},
            content_type='application/json',
            HTTP_AUTHORIZATION=f'Bearer {token}',
        )
        repeated = self.client.post(
            reverse('staff:api_qr_attendance_scan'),
            data={'token': session.token},
            content_type='application/json',
            HTTP_AUTHORIZATION=f'Bearer {token}',
        )

        self.assertEqual(first.status_code, 201)
        self.assertEqual(repeated.status_code, 429)
        self.assertEqual(repeated.json()['status'], 'duplicate')
        self.assertEqual(
            AttendanceRecord.objects.filter(
                org=self.org,
                mem=self.staff_member,
                attendance_method='qr',
            ).count(),
            1,
        )
        self.assertFalse(
            AttendanceRecord.objects.filter(mem=self.student_member).exists()
        )

    def test_dynamic_qr_scan_rejects_session_before_valid_from(self):
        self.org.enable_qr_attendance = True
        self.org.save(update_fields=['enable_qr_attendance'])
        now = timezone.now()
        session = QRAttendanceSession.objects.create(
            org=self.org,
            generated_by=self.staff_user,
            token='future-mobile-session',
            valid_from=now + timedelta(minutes=5),
            expires_at=now + timedelta(minutes=10),
            date=timezone.localdate(),
        )
        token = RefreshToken.for_user(self.staff_user).access_token

        response = self.client.post(
            reverse('staff:api_qr_attendance_scan'),
            data={'token': session.token},
            content_type='application/json',
            HTTP_AUTHORIZATION=f'Bearer {token}',
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()['status'], 'not_active')
        self.assertFalse(
            AttendanceRecord.objects.filter(mem=self.staff_member).exists()
        )

    def test_dynamic_qr_scan_enforces_staff_role_permission(self):
        self.org.enable_qr_attendance = True
        self.org.save(update_fields=['enable_qr_attendance'])
        self.staff_permissions.can_scan_qr_attendance = False
        self.staff_permissions.save(update_fields=['can_scan_qr_attendance'])
        now = timezone.now()
        session = QRAttendanceSession.objects.create(
            org=self.org,
            generated_by=self.staff_user,
            token='permission-mobile-session',
            valid_from=now - timedelta(minutes=1),
            expires_at=now + timedelta(minutes=5),
            date=timezone.localdate(),
        )
        token = RefreshToken.for_user(self.staff_user).access_token

        response = self.client.post(
            reverse('staff:api_qr_attendance_scan'),
            data={'token': session.token},
            content_type='application/json',
            HTTP_AUTHORIZATION=f'Bearer {token}',
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(
            AttendanceRecord.objects.filter(mem=self.staff_member).exists()
        )

    def test_permanent_qr_requires_valid_location_and_enforces_geofence(self):
        self.org.enable_qr_attendance = True
        self.org.save(update_fields=['enable_qr_attendance'])
        session = QRAttendanceSession.objects.create(
            org=self.org,
            generated_by=self.staff_user,
            token='permanent-geofenced-session',
            session_type='permanent',
            valid_from=timezone.now() - timedelta(minutes=1),
            location_name='Portal Academy Gate',
            latitude=27.7172,
            longitude=85.3240,
            radius_meters=120,
        )
        token = RefreshToken.for_user(self.staff_user).access_token
        url = reverse('staff:api_qr_attendance_scan')

        missing = self.client.post(
            url,
            data={'token': session.token},
            content_type='application/json',
            HTTP_AUTHORIZATION=f'Bearer {token}',
        )
        invalid = self.client.post(
            url,
            data={
                'token': session.token,
                'latitude': 'NaN',
                'longitude': '85.3240',
            },
            content_type='application/json',
            HTTP_AUTHORIZATION=f'Bearer {token}',
        )
        outside = self.client.post(
            url,
            data={
                'token': session.token,
                'latitude': 27.7000,
                'longitude': 85.3000,
            },
            content_type='application/json',
            HTTP_AUTHORIZATION=f'Bearer {token}',
        )
        inside = self.client.post(
            url,
            data={
                'token': session.token,
                'latitude': 27.7173,
                'longitude': 85.3241,
            },
            content_type='application/json',
            HTTP_AUTHORIZATION=f'Bearer {token}',
        )

        self.assertEqual(missing.status_code, 400)
        self.assertEqual(missing.json()['status'], 'location_required')
        self.assertEqual(invalid.status_code, 400)
        self.assertEqual(outside.status_code, 403)
        self.assertEqual(outside.json()['status'], 'outside_geofence')
        self.assertEqual(inside.status_code, 201)
        self.assertEqual(
            AttendanceRecord.objects.filter(
                mem=self.staff_member,
                attendance_method='qr',
            ).count(),
            1,
        )

    def test_static_qr_mobile_endpoint_is_disabled(self):
        token = RefreshToken.for_user(self.staff_user).access_token

        response = self.client.post(
            reverse('staff:api_qr_checkin'),
            data={'member_id': self.staff_member.id, 'qr_token': 'ORG:1:QR:1'},
            content_type='application/json',
            HTTP_AUTHORIZATION=f'Bearer {token}',
        )

        self.assertEqual(response.status_code, 410)

    def _enable_mobile_field_work(self):
        self.org.feature_field_visits = True
        self.org.allowed_features = sorted(
            set(self.org.allowed_features + ['field_visits'])
        )
        self.org.save(update_fields=[
            'feature_field_visits', 'allowed_features',
        ])
        self.staff_permissions.can_send_location = True
        self.staff_permissions.can_view_field_visits = True
        self.staff_permissions.save(update_fields=[
            'can_send_location', 'can_view_field_visits',
        ])

    def test_mobile_field_visit_uses_authenticated_member_and_lifecycle(self):
        self._enable_mobile_field_work()
        token = RefreshToken.for_user(self.staff_user).access_token

        created = self.client.post(
            reverse('staff:api_my_field_visits'),
            data={
                'member_id': self.student_member.id,
                'purpose': 'Client onboarding',
                'destination': 'Baneshwor',
                'latitude': 27.688,
                'longitude': 85.335,
                'accuracy': 12,
                'note': 'Reached the client office.',
            },
            content_type='application/json',
            HTTP_AUTHORIZATION=f'Bearer {token}',
        )
        visit_id = created.json()['id']
        ended = self.client.post(
            reverse('staff:api_my_field_visit_action', args=[visit_id]),
            data={
                'action': 'end',
                'latitude': 27.689,
                'longitude': 85.336,
                'accuracy': 10,
                'note': 'Meeting completed.',
            },
            content_type='application/json',
            HTTP_AUTHORIZATION=f'Bearer {token}',
        )

        self.assertEqual(created.status_code, 201)
        self.assertEqual(ended.status_code, 200)
        visit = FieldVisit.objects.get(pk=visit_id)
        self.assertEqual(visit.member, self.staff_member)
        self.assertEqual(visit.visit_state, 'completed')
        self.assertIsNotNone(visit.ended_at)
        self.assertFalse(
            FieldVisit.objects.filter(member=self.student_member).exists()
        )

    def test_mobile_field_visit_can_create_client_and_optional_prioritized_followup(self):
        self._enable_mobile_field_work()
        self.org.feature_clients = True
        self.org.allowed_features = sorted(set(self.org.allowed_features + ['clients']))
        self.org.save(update_fields=['feature_clients', 'allowed_features'])
        self.staff_permissions.can_view_clients = True
        self.staff_permissions.can_manage_clients = True
        self.staff_permissions.save(update_fields=['can_view_clients', 'can_manage_clients'])
        token = RefreshToken.for_user(self.staff_user).access_token

        created = self.client.post(
            reverse('staff:api_my_field_visits'),
            data={
                'purpose': 'Priority sales visit',
                'destination': 'New Road',
                'latitude': 27.704,
                'longitude': 85.307,
                'accuracy': 9,
                'client_org_name': 'Safe CRM Client',
                'client_priority': 'high',
                'log_follow_up': True,
                'feedback': 'Requested a quotation.',
                'follow_up_priority': 'high',
            },
            content_type='application/json',
            HTTP_AUTHORIZATION=f'Bearer {token}',
        )

        self.assertEqual(created.status_code, 201)
        client = Client.objects.get(client_org_name='Safe CRM Client')
        visit = FieldVisit.objects.get(pk=created.json()['id'])
        follow_up = ClientFollowUp.objects.get(field_visit=visit)
        self.assertEqual(client.created_by, self.staff_user)
        self.assertEqual(visit.client, client)
        self.assertEqual(follow_up.priority, 'high')
        self.assertEqual(follow_up.created_by, self.staff_user)
        self.assertEqual(created.json()['follow_ups'][0]['priority'], 'high')

    def test_legacy_field_visit_api_ignores_forged_member_id(self):
        self._enable_mobile_field_work()
        token = RefreshToken.for_user(self.staff_user).access_token

        response = self.client.post(
            reverse('staff:api_field_visit_submit'),
            data={
                'member_id': self.student_member.id,
                'latitude': 27.688,
                'longitude': 85.335,
                'accuracy': 12,
            },
            content_type='application/json',
            HTTP_AUTHORIZATION=f'Bearer {token}',
        )

        self.assertEqual(response.status_code, 201)
        self.assertTrue(
            FieldVisit.objects.filter(member=self.staff_member).exists()
        )
        self.assertFalse(
            FieldVisit.objects.filter(member=self.student_member).exists()
        )

    def test_mobile_live_tracking_requires_explicit_start_and_dedupes_pings(self):
        self._enable_mobile_field_work()
        self.staff_member.live_tracking_enabled = True
        self.staff_member.save(update_fields=['live_tracking_enabled'])
        shift = Shift.objects.create(org=self.org, name='All Day Field Shift')
        ShiftWindow.objects.create(
            shift=shift,
            start_time=datetime.time(0, 0),
            end_time=datetime.time(23, 59),
        )
        self.staff_member.shifts.add(shift)
        token = RefreshToken.for_user(self.staff_user).access_token

        started = self.client.post(
            reverse('staff:api_live_tracking'),
            data={'action': 'start'},
            content_type='application/json',
            HTTP_AUTHORIZATION=f'Bearer {token}',
        )
        ping = self.client.post(
            reverse('staff:api_live_tracking'),
            data={
                'action': 'ping',
                'latitude': 27.7,
                'longitude': 85.3,
                'accuracy': 8,
            },
            content_type='application/json',
            HTTP_AUTHORIZATION=f'Bearer {token}',
        )
        repeated = self.client.post(
            reverse('staff:api_live_tracking'),
            data={
                'action': 'ping',
                'latitude': 27.7001,
                'longitude': 85.3001,
                'accuracy': 8,
            },
            content_type='application/json',
            HTTP_AUTHORIZATION=f'Bearer {token}',
        )
        stopped = self.client.post(
            reverse('staff:api_live_tracking'),
            data={'action': 'stop'},
            content_type='application/json',
            HTTP_AUTHORIZATION=f'Bearer {token}',
        )

        self.assertEqual(started.status_code, 200)
        self.assertEqual(ping.status_code, 201)
        self.assertEqual(repeated.status_code, 429)
        self.assertEqual(stopped.status_code, 200)
        self.assertEqual(
            LiveTrackingSession.objects.get(member=self.staff_member).status,
            'stopped',
        )
        self.assertEqual(
            LocationPing.objects.filter(member=self.staff_member).count(), 1,
        )

    def test_mobile_tasks_are_self_scoped_and_transition_is_audited(self):
        task = Task.objects.create(
            org=self.org,
            title='Prepare monthly report',
            description='Submit the attendance summary.',
            priority='high',
            task_type='one_time',
            start_date=timezone.localdate(),
            due_date=timezone.localdate(),
            created_by=self.staff_user,
        )
        staff_instance = TaskInstance.objects.create(
            task=task,
            assigned_member=self.staff_member,
            due_date=timezone.localdate(),
        )
        TaskInstance.objects.create(
            task=task,
            assigned_member=self.student_member,
            due_date=timezone.localdate(),
        )
        token = RefreshToken.for_user(self.staff_user).access_token

        listing = self.client.get(
            reverse('staff:api_my_tasks'),
            HTTP_AUTHORIZATION=f'Bearer {token}',
        )
        started = self.client.post(
            reverse('staff:api_my_task_detail', args=[staff_instance.id]),
            data={'action': 'start', 'note': 'Work started.'},
            content_type='application/json',
            HTTP_AUTHORIZATION=f'Bearer {token}',
        )
        completed = self.client.post(
            reverse('staff:api_my_task_detail', args=[staff_instance.id]),
            data={'action': 'complete', 'note': 'Report submitted.'},
            content_type='application/json',
            HTTP_AUTHORIZATION=f'Bearer {token}',
        )

        self.assertEqual(listing.status_code, 200)
        self.assertEqual(listing.json()['total'], 1)
        self.assertEqual(started.json()['status'], 'in_progress')
        self.assertEqual(completed.json()['status'], 'completed')
        staff_instance.refresh_from_db()
        self.assertEqual(staff_instance.update_logs.count(), 2)

    def _enable_mobile_communications(self):
        self.org.feature_notices = True
        self.org.feature_events = True
        self.org.feature_complaints = True
        self.org.allowed_features = sorted(set(
            self.org.allowed_features
            + ['notices', 'events', 'complaints']
        ))
        self.org.save(update_fields=[
            'feature_notices',
            'feature_events',
            'feature_complaints',
            'allowed_features',
        ])
        self.staff_permissions.can_view_notices = True
        self.staff_permissions.can_view_events = True
        self.staff_permissions.can_view_complaints = True
        self.staff_permissions.save(update_fields=[
            'can_view_notices',
            'can_view_events',
            'can_view_complaints',
        ])

    def test_mobile_notices_are_targeted_and_read_state_is_self_scoped(self):
        self._enable_mobile_communications()
        visible = Notice.objects.create(
            org=self.org,
            title='Staff briefing',
            body='Meet in the conference room.',
            audience='staff_only',
        )
        Notice.objects.create(
            org=self.org,
            title='Student notice',
            body='This must not be visible to staff.',
            audience='students_only',
        )
        other_org = Organization.objects.create(
            name='Other Notice Org',
            category='office',
            expire_on=timezone.now() + timedelta(days=60),
            serial_key='OTHER-NOTICE-001',
            new_serial_key='OTHER-NOTICE-NEW',
            activate=True,
        )
        foreign = Notice.objects.create(
            org=other_org,
            title='Foreign notice',
            body='Private',
        )
        token = RefreshToken.for_user(self.staff_user).access_token

        listing = self.client.get(
            reverse('staff:api_my_notices'),
            HTTP_AUTHORIZATION=f'Bearer {token}',
        )
        marked = self.client.post(
            reverse('staff:api_my_notices'),
            data={'action': 'mark_read', 'notice_id': visible.id},
            content_type='application/json',
            HTTP_AUTHORIZATION=f'Bearer {token}',
        )
        forged = self.client.post(
            reverse('staff:api_my_notices'),
            data={'action': 'mark_read', 'notice_id': foreign.id},
            content_type='application/json',
            HTTP_AUTHORIZATION=f'Bearer {token}',
        )

        self.assertEqual(listing.status_code, 200)
        self.assertEqual(listing.json()['total'], 1)
        self.assertEqual(listing.json()['results'][0]['id'], visible.id)
        self.assertEqual(marked.status_code, 200)
        self.assertTrue(
            NoticeRead.objects.filter(
                notice=visible,
                member=self.staff_member,
            ).exists()
        )
        self.assertEqual(forged.status_code, 404)

    def test_mobile_events_respect_branch_and_global_scope(self):
        self._enable_mobile_communications()
        own_branch = Branch.objects.create(
            org=self.org,
            name='Main Branch',
            code='MAIN',
        )
        other_branch = Branch.objects.create(
            org=self.org,
            name='Remote Branch',
            code='REMOTE',
        )
        self.staff_member.branch = own_branch
        self.staff_member.save(update_fields=['branch'])
        today = timezone.localdate()
        own_event = Event.objects.create(
            org=self.org,
            branch=own_branch,
            title='Main branch event',
            start_date=today,
            end_date=today,
        )
        global_event = Event.objects.create(
            org=self.org,
            title='Organization event',
            start_date=today,
            end_date=today,
        )
        Event.objects.create(
            org=self.org,
            branch=other_branch,
            title='Remote-only event',
            start_date=today,
            end_date=today,
        )
        token = RefreshToken.for_user(self.staff_user).access_token

        response = self.client.get(
            reverse('staff:api_my_events'),
            HTTP_AUTHORIZATION=f'Bearer {token}',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            {item['id'] for item in response.json()['results']},
            {own_event.id, global_event.id},
        )

    def test_mobile_calendar_combines_authorized_staff_schedule(self):
        self._enable_mobile_communications()
        today = timezone.localdate()
        Event.objects.create(
            org=self.org,
            title='Team meeting',
            start_date=today,
            end_date=today,
        )
        Occasion.objects.create(
            org=self.org,
            name='Organization holiday',
            date=today,
        )
        task = Task.objects.create(
            org=self.org,
            title='Calendar task',
            task_type='one_time',
            start_date=today,
            due_date=today,
            created_by=self.staff_user,
        )
        TaskInstance.objects.create(
            task=task,
            assigned_member=self.staff_member,
            due_date=today,
        )
        token = RefreshToken.for_user(self.staff_user).access_token

        response = self.client.get(
            reverse('staff:api_my_calendar'),
            {
                'from_date': today.isoformat(),
                'to_date': today.isoformat(),
            },
            HTTP_AUTHORIZATION=f'Bearer {token}',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            {item['type'] for item in response.json()['items']},
            {'event', 'holiday', 'task'},
        )

    def test_mobile_complaints_support_private_thread_and_reject_cross_member(self):
        self._enable_mobile_communications()
        token = RefreshToken.for_user(self.staff_user).access_token

        created = self.client.post(
            reverse('staff:api_my_complaints'),
            data={
                'complaint_type': 'workplace',
                'subject': 'Equipment request',
                'description': 'A replacement device is required.',
                'priority': 'high',
            },
            content_type='application/json',
            HTTP_AUTHORIZATION=f'Bearer {token}',
        )
        complaint_id = created.json()['id']
        replied = self.client.post(
            reverse(
                'staff:api_my_complaint_detail',
                args=[complaint_id],
            ),
            data={'action': 'message', 'message': 'Additional context.'},
            content_type='application/json',
            HTTP_AUTHORIZATION=f'Bearer {token}',
        )
        foreign = Complaint.objects.create(
            org=self.org,
            filed_by=self.student_member,
            complaint_type='academic',
            subject='Private student complaint',
            description='Private',
        )
        forbidden = self.client.get(
            reverse(
                'staff:api_my_complaint_detail',
                args=[foreign.id],
            ),
            HTTP_AUTHORIZATION=f'Bearer {token}',
        )

        self.assertEqual(created.status_code, 201)
        self.assertEqual(replied.status_code, 200)
        self.assertEqual(replied.json()['messages'][0]['message'], 'Additional context.')
        self.assertTrue(
            ComplaintMessage.objects.filter(
                complaint_id=complaint_id,
                author=self.staff_user,
            ).exists()
        )
        self.assertEqual(forbidden.status_code, 404)

        self.staff_permissions.can_manage_complaints = True
        self.staff_permissions.save(update_fields=['can_manage_complaints'])
        self.client.force_login(self.staff_user)
        management_reply = self.client.post(
            reverse('staff:complaint_detail', args=[complaint_id]),
            data={
                'status': 'reviewing',
                'admin_remarks': 'Management is reviewing this request.',
                'reply_message': 'We have assigned this to the support team.',
            },
        )

        self.assertEqual(management_reply.status_code, 302)
        self.assertTrue(
            ComplaintMessage.objects.filter(
                complaint_id=complaint_id,
                is_staff_reply=True,
                message='We have assigned this to the support team.',
            ).exists()
        )

    def _enable_student_academics(self):
        feature = DynamicFeature.objects.get(key='academic_management')
        OrganizationFeatureGrant.objects.update_or_create(
            org=self.org,
            feature=feature,
            defaults={'enabled': True},
        )
        from school.features import invalidate_org_feature_cache
        invalidate_org_feature_cache(self.org.id)

    def _create_student_academic_fixture(self):
        self._enable_student_academics()
        today = timezone.localdate()
        classification = Classification.objects.create(
            org=self.org,
            name='Grade 10',
        )
        section = Section.objects.create(
            org=self.org,
            classification=classification,
            name='A',
        )
        course = Course.objects.create(
            org=self.org,
            name='Class 10 Programme',
        )
        course.classifications.add(classification)
        course.sections.add(section)
        self.student_member.classification = classification
        self.student_member.section = section
        self.student_member.save(update_fields=['classification', 'section'])
        self.student_member.courses.add(course)
        academic_year = AcademicYear.objects.create(
            org=self.org,
            name='2083/84',
            start_date=today - timedelta(days=30),
            end_date=today + timedelta(days=300),
            is_current=True,
        )
        StudentCourseEnrollment.objects.create(
            org=self.org,
            academic_year=academic_year,
            student=self.student_member,
            course=course,
            classification=classification,
            section=section,
            start_date=today - timedelta(days=30),
        )
        subject = Subject.objects.create(
            org=self.org,
            course=course,
            classification=classification,
            section=section,
            teacher=self.staff_user,
            name='Mathematics',
            full_marks=100,
            pass_marks=40,
        )
        routine = RoutinePeriod.objects.create(
            org=self.org,
            classification=classification,
            section=section,
            subject=subject,
            teacher=self.staff_user,
            academic_year=academic_year,
            day_of_week=(today.weekday() + 1) % 7,
            period_number=1,
            start_time=datetime.time(9, 0),
            end_time=datetime.time(10, 0),
            room='R-10',
        )
        homework = Homework.objects.create(
            org=self.org,
            classification=classification,
            section=section,
            subject=subject,
            assigned_by=self.staff_user,
            description='Complete chapter one exercises.',
            due_date=today + timedelta(days=2),
        )
        HomeworkStatus.objects.create(
            homework=homework,
            student=self.student_member,
        )
        assignment = Assignment.objects.create(
            org=self.org,
            classification=classification,
            section=section,
            subject=subject,
            course=course,
            assigned_by=self.staff_user,
            title='Algebra worksheet',
            due_date=today + timedelta(days=4),
            visibility='published',
            status='open',
        )
        bill = Bill.objects.create(
            org=self.org,
            member=self.student_member,
            classification=classification,
            section=section,
            invoice_number=f'STUDENT-{self.student_member.id}-001',
            due_date=today + timedelta(days=7),
            total_amount=1500,
            amount_paid=500,
            status='Partial',
        )
        BillItem.objects.create(
            bill=bill,
            description='Monthly tuition',
            amount=1500,
        )
        exam = ExamTerm.objects.create(
            org=self.org,
            classification=classification,
            section=section,
            name='First Terminal',
            start_date=today - timedelta(days=10),
            end_date=today - timedelta(days=5),
            status='published',
            is_published=True,
        )
        ResultRecord.objects.create(
            student=self.student_member,
            exam=exam,
            subject=subject,
            obtained_marks=82,
        )
        return {
            'classification': classification,
            'section': section,
            'course': course,
            'academic_year': academic_year,
            'subject': subject,
            'routine': routine,
            'homework': homework,
            'assignment': assignment,
            'bill': bill,
            'exam': exam,
        }

    def test_mobile_student_dashboard_uses_exact_self_service_scope(self):
        fixture = self._create_student_academic_fixture()
        own_branch = Branch.objects.create(
            org=self.org,
            name='Student Branch',
            code='STUDENT',
        )
        foreign_branch = Branch.objects.create(
            org=self.org,
            name='Other Campus',
            code='OTHER-CAMPUS',
        )
        self.student_member.branch = own_branch
        self.student_member.save(update_fields=['branch'])
        RoutinePeriod.objects.create(
            org=self.org,
            branch=foreign_branch,
            classification=fixture['classification'],
            section=fixture['section'],
            subject=fixture['subject'],
            teacher=self.staff_user,
            academic_year=fixture['academic_year'],
            day_of_week=(timezone.localdate().weekday() + 1) % 7,
            period_number=9,
            start_time=datetime.time(16, 0),
            end_time=datetime.time(17, 0),
            room='Other campus',
        )
        self.org.feature_notices = True
        self.org.allowed_features = sorted(set(
            self.org.allowed_features + ['notices']
        ))
        self.org.save(update_fields=['feature_notices', 'allowed_features'])
        Notice.objects.create(
            org=self.org,
            title='Student assembly',
            body='Assembly starts at 8:45.',
            audience='students_only',
        )
        Notice.objects.create(
            org=self.org,
            title='Staff private',
            body='Staff only.',
            audience='staff_only',
        )
        self.org.feature_events = True
        self.org.allowed_features = sorted(set(
            self.org.allowed_features + ['events']
        ))
        self.org.nepali_date = True
        self.org.save(update_fields=[
            'feature_events', 'allowed_features', 'nepali_date',
        ])
        Event.objects.create(
            org=self.org,
            branch=own_branch,
            title='Student sports day',
            start_date=timezone.localdate() + timedelta(days=1),
            end_date=timezone.localdate() + timedelta(days=1),
        )
        token = RefreshToken.for_user(self.student_user).access_token

        response = self.client.get(
            reverse('staff:api_student_dashboard'),
            HTTP_AUTHORIZATION=f'Bearer {token}',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['student']['enrollments'][0]['course']['id'], fixture['course'].id)
        self.assertEqual(payload['routine']['today'][0]['id'], fixture['routine'].id)
        self.assertEqual(len(payload['routine']['today']), 1)
        self.assertEqual(payload['billing']['total_due'], '1000.00')
        self.assertEqual(payload['academic_work']['homework_pending'], 1)
        self.assertEqual(payload['academic_work']['assignments_pending'], 1)
        self.assertEqual(payload['results']['published_exam_count'], 1)
        self.assertEqual(payload['notices']['unread_count'], 1)
        self.assertEqual(payload['events']['upcoming'][0]['title'], 'Student sports day')
        self.assertTrue(payload['nepali_date'])
        self.assertTrue(payload['date_np'])

    def test_mobile_student_bills_and_results_never_expose_another_student(self):
        fixture = self._create_student_academic_fixture()
        foreign_bill = Bill.objects.create(
            org=self.org,
            member=self.staff_member,
            invoice_number='FOREIGN-STUDENT-BILL',
            due_date=timezone.localdate(),
            total_amount=9999,
            status='Unpaid',
        )
        ResultRecord.objects.create(
            student=self.staff_member,
            exam=fixture['exam'],
            subject=fixture['subject'],
            obtained_marks=45,
        )
        token = RefreshToken.for_user(self.student_user).access_token

        bills = self.client.get(
            reverse('staff:api_student_bills'),
            HTTP_AUTHORIZATION=f'Bearer {token}',
        )
        results = self.client.get(
            reverse('staff:api_student_results'),
            HTTP_AUTHORIZATION=f'Bearer {token}',
        )

        self.assertEqual(bills.status_code, 200)
        self.assertEqual(bills.json()['total'], 1)
        self.assertNotEqual(
            bills.json()['results'][0]['id'],
            foreign_bill.id,
        )
        self.assertEqual(results.status_code, 200)
        self.assertEqual(len(results.json()['records']), 1)
        self.assertEqual(
            results.json()['records'][0]['obtained_marks'],
            '82.00',
        )

    def test_mobile_student_academic_actions_are_scoped_and_idempotent(self):
        fixture = self._create_student_academic_fixture()
        token = RefreshToken.for_user(self.student_user).access_token

        submitted = self.client.post(
            reverse('staff:api_student_academic_work'),
            data={
                'action': 'assignment_submit',
                'assignment_id': fixture['assignment'].id,
                'student_comments': 'Completed in the mobile app.',
            },
            content_type='application/json',
            HTTP_AUTHORIZATION=f'Bearer {token}',
        )
        repeated = self.client.post(
            reverse('staff:api_student_academic_work'),
            data={
                'action': 'assignment_submit',
                'assignment_id': fixture['assignment'].id,
                'student_comments': 'Corrected response.',
            },
            content_type='application/json',
            HTTP_AUTHORIZATION=f'Bearer {token}',
        )
        staff_denied = self.client.get(
            reverse('staff:api_student_dashboard'),
            HTTP_AUTHORIZATION=(
                f'Bearer {RefreshToken.for_user(self.staff_user).access_token}'
            ),
        )

        self.assertEqual(submitted.status_code, 201)
        self.assertEqual(repeated.status_code, 200)
        self.assertEqual(
            AssignmentSubmission.objects.filter(
                assignment=fixture['assignment'],
                student=self.student_member,
            ).count(),
            1,
        )
        submission = AssignmentSubmission.objects.get(
            assignment=fixture['assignment'],
            student=self.student_member,
        )
        self.assertEqual(submission.student_comments, 'Corrected response.')
        self.assertEqual(submission.history.count(), 2)
        self.assertEqual(staff_denied.status_code, 403)

    def test_mobile_class_attendance_rejects_foreign_org_member(self):
        other_org = Organization.objects.create(
            name='Foreign Academy',
            category='school',
            expire_on=timezone.now() + timedelta(days=60),
            serial_key='FOREIGN-PORTAL-001',
            new_serial_key='FOREIGN-PORTAL-001-NEW',
            activate=True,
        )
        foreign_member = member.objects.create(
            org=other_org,
            name='Foreign Student',
            member_type='student',
            gender='Male',
        )
        self.staff_permissions.can_add_attendance = True
        self.staff_permissions.can_view_members = True
        self.staff_permissions.save(update_fields=[
            'can_add_attendance', 'can_view_members',
        ])
        token = RefreshToken.for_user(self.staff_user).access_token

        response = self.client.post(
            reverse('staff:api_mark_present'),
            data={'member_id': foreign_member.id},
            content_type='application/json',
            HTTP_AUTHORIZATION=f'Bearer {token}',
        )

        self.assertEqual(response.status_code, 404)

    def test_mobile_refresh_token_endpoint_rotates_access_token(self):
        refresh = RefreshToken.for_user(self.staff_user)

        response = self.client.post(
            reverse('handle:token-refresh'),
            data={'refresh': str(refresh)},
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['access'])

    def test_mobile_password_reset_does_not_disclose_unknown_account(self):
        response = self.client.post(
            reverse('handle:password-reset'),
            data={'email': 'unknown-account@example.invalid'},
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()['message'],
            'Password reset link sent to email',
        )

    def test_teacher_dashboard_and_navigation_are_role_specific(self):
        teacher_member, teacher_user, _ = self._make_portal_user(
            'teacher', 'Teacher One',
        )
        feature, _ = DynamicFeature.objects.get_or_create(
            key='academic_management',
            defaults={'label': 'Academic Management'},
        )
        OrganizationFeatureGrant.objects.create(
            org=self.org,
            feature=feature,
            enabled=True,
        )
        self.client.force_login(teacher_user)

        navigation, role, role_label = build_portal_navigation(
            teacher_user, self.org,
        )
        response = self.client.get(reverse('staff:dashboard'))

        self.assertEqual(role, 'teacher')
        self.assertEqual(role_label, 'Teacher Workspace')
        self.assertIn('My Class Routine', self._labels(navigation))
        self.assertIn('My Profile', self._labels(navigation))
        self.assertIn('Change Password', self._labels(navigation))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Teacher Workspace')
        self.assertContains(response, 'teacher-workspace')
        self.assertContains(response, 'My Profile')
        self.assertContains(response, 'Change Password')

    def test_profile_page_is_self_scoped_and_updates_only_safe_personal_fields(self):
        another_member = member.objects.create(
            org=self.org,
            name='Another Student',
            member_type='student',
            gender='Female',
        )
        self.client.force_login(self.student_user)

        get_response = self.client.get(reverse('staff:profile'))
        post_response = self.client.post(
            reverse('staff:profile'),
            {
                'member_id': str(another_member.pk),
                'org': '999999',
                'name': 'Student One Updated',
                'gender': 'Male',
                'phone': '9800000001',
                'address': 'Kathmandu',
                'date_of_birth': '2008-05-10',
                'blood_group': 'O+',
                'guardian_name': 'Guardian One',
                'guardian_phone': '9800000002',
                'guardian_email': 'guardian@example.com',
            },
        )

        self.assertEqual(get_response.status_code, 200)
        self.assertContains(get_response, 'Student Profile')
        self.assertContains(get_response, self.student_user.email)
        self.assertRedirects(
            post_response,
            reverse('staff:profile'),
            fetch_redirect_response=False,
        )
        self.student_member.refresh_from_db()
        another_member.refresh_from_db()
        self.assertEqual(self.student_member.name, 'Student One Updated')
        self.assertEqual(self.student_member.address, 'Kathmandu')
        self.assertEqual(self.student_member.guardian_name, 'Guardian One')
        self.assertEqual(another_member.name, 'Another Student')
        self.assertEqual(self.student_member.org, self.org)

    def test_staff_profile_hides_student_guardian_fields(self):
        self.client.force_login(self.staff_user)

        response = self.client.get(reverse('staff:profile'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Staff Profile')
        self.assertNotContains(response, 'Guardian name')
        self.assertContains(response, 'Change Password')

    def test_password_change_keeps_portal_session_authenticated(self):
        self.client.force_login(self.staff_user)

        response = self.client.post(
            reverse('handle:changePassword'),
            {
                'old_password': self.password,
                'new_password1': 'NewPortalPassword-2026!',
                'new_password2': 'NewPortalPassword-2026!',
            },
        )

        self.assertRedirects(
            response,
            reverse('handle:changePassword'),
            fetch_redirect_response=False,
        )
        self.staff_user.refresh_from_db()
        self.assertTrue(
            self.staff_user.check_password('NewPortalPassword-2026!')
        )
        self.assertEqual(
            self.client.get(reverse('staff:profile')).status_code,
            200,
        )

    def test_profile_requires_authentication(self):
        response = self.client.get(reverse('staff:profile'))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, '/')

    def _create_teacher_mobile_fixture(self):
        fixture = self._create_student_academic_fixture()
        today = timezone.localdate()
        self.staff_member.member_type = 'teacher'
        self.staff_member.save(update_fields=['member_type'])
        scope = SubjectTeacherAssignment.objects.create(
            org=self.org,
            academic_year=fixture['academic_year'],
            course=fixture['course'],
            classification=fixture['classification'],
            section=fixture['section'],
            subject=fixture['subject'],
            teacher=self.staff_user,
            is_primary=True,
            start_date=today - timedelta(days=10),
            assigned_by=self.staff_user,
        )
        fixture['routine'].teacher_assignment = scope
        fixture['routine'].save(update_fields=['teacher_assignment'])
        fixture['assignment'].teacher_assignment = scope
        fixture['assignment'].save(update_fields=['teacher_assignment'])
        fixture['homework'].teacher_assignment = scope
        fixture['homework'].save(update_fields=['teacher_assignment'])
        fixture['scope'] = scope
        return fixture

    def _teacher_token(self):
        return RefreshToken.for_user(self.staff_user).access_token

    def test_mobile_teacher_dashboard_and_routine_use_assignment_scope(self):
        fixture = self._create_teacher_mobile_fixture()
        assignment_branch = Branch.objects.create(
            org=self.org,
            name='Academic Block',
            code='ACADEMIC-BLOCK',
        )
        SubjectTeacherAssignment.objects.filter(
            pk=fixture['scope'].pk,
        ).update(branch=assignment_branch)
        fixture['scope'].refresh_from_db()
        self.assertIsNone(self.staff_member.branch_id)
        self.org.feature_events = True
        self.org.nepali_date = True
        self.org.allowed_features = sorted(set(
            self.org.allowed_features + ['events']
        ))
        self.org.save(update_fields=[
            'feature_events', 'nepali_date', 'allowed_features',
        ])
        Event.objects.create(
            org=self.org,
            title='Teacher planning day',
            start_date=timezone.localdate() + timedelta(days=2),
            end_date=timezone.localdate() + timedelta(days=2),
        )
        token = self._teacher_token()

        dashboard = self.client.get(
            reverse('staff:api_teacher_dashboard'),
            HTTP_AUTHORIZATION=f'Bearer {token}',
        )
        routine = self.client.get(
            reverse('staff:api_teacher_routine'),
            HTTP_AUTHORIZATION=f'Bearer {token}',
        )
        student_denied = self.client.get(
            reverse('staff:api_teacher_dashboard'),
            HTTP_AUTHORIZATION=(
                f'Bearer {RefreshToken.for_user(self.student_user).access_token}'
            ),
        )

        self.assertEqual(dashboard.status_code, 200)
        payload = dashboard.json()
        self.assertEqual(payload['summary']['assigned_subjects'], 1)
        self.assertEqual(payload['summary']['assigned_students'], 1)
        self.assertEqual(
            payload['assignments'][0]['id'],
            fixture['scope'].id,
        )
        self.assertEqual(payload['students'][0]['id'], self.student_member.id)
        self.assertEqual(payload['events']['upcoming'][0]['title'], 'Teacher planning day')
        self.assertTrue(payload['date_np'])
        self.assertEqual(routine.status_code, 200)
        self.assertEqual(routine.json()['periods'][0]['id'], fixture['routine'].id)
        self.assertEqual(student_denied.status_code, 403)

    def test_mobile_teacher_attendance_is_server_scoped_and_idempotent(self):
        fixture = self._create_teacher_mobile_fixture()
        token = self._teacher_token()
        context_url = reverse(
            'staff:api_teacher_attendance_context',
            kwargs={'period_id': fixture['routine'].id},
        )
        context = self.client.get(
            context_url,
            HTTP_AUTHORIZATION=f'Bearer {token}',
        )
        payload = {
            'routine_period': fixture['routine'].id,
            'date': timezone.localdate().isoformat(),
            'topic_covered': 'Quadratic equations',
            'save_as_draft': True,
            'attendance': [
                {
                    'student_id': self.student_member.id,
                    'status': 'late',
                    'remarks': 'Arrived after the bell.',
                },
                {
                    'student_id': self.staff_member.id,
                    'status': 'present',
                },
            ],
        }
        first = self.client.post(
            reverse('staff:api_submit_subject_attendance'),
            data=payload,
            content_type='application/json',
            HTTP_AUTHORIZATION=f'Bearer {token}',
        )
        payload['save_as_draft'] = False
        payload['topic_covered'] = 'Quadratic equation exercises'
        second = self.client.post(
            reverse('staff:api_submit_subject_attendance'),
            data=payload,
            content_type='application/json',
            HTTP_AUTHORIZATION=f'Bearer {token}',
        )

        self.assertEqual(context.status_code, 200)
        self.assertEqual(
            [item['id'] for item in context.json()['students']],
            [self.student_member.id],
        )
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.json()['status'], 'draft')
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.json()['status'], 'submitted')
        self.assertEqual(
            TeachingLog.objects.filter(
                teacher=self.staff_user,
                routine_period=fixture['routine'],
            ).count(),
            1,
        )
        log = TeachingLog.objects.get(routine_period=fixture['routine'])
        self.assertEqual(log.topic_covered, 'Quadratic equation exercises')
        self.assertEqual(
            SubjectAttendanceRecord.objects.filter(teaching_log=log).count(),
            1,
        )
        self.assertEqual(
            SubjectAttendanceRecord.objects.get(teaching_log=log).status,
            'late',
        )
        sessions = self.client.get(
            reverse('staff:api_teacher_sessions'),
            {'status': 'submitted'},
            HTTP_AUTHORIZATION=f'Bearer {token}',
        )
        self.assertEqual(sessions.status_code, 200)
        self.assertEqual(len(sessions.json()['results']), 1)
        self.assertEqual(
            sessions.json()['results'][0]['routine_period_id'],
            fixture['routine'].id,
        )

    def test_driver_trip_and_student_bus_location_are_org_scoped(self):
        driver_member, driver_user, _ = self._make_portal_user(
            'driver', 'Driver One',
        )
        bus = SchoolBus.objects.create(
            org=self.org,
            name='Bus One',
            registration_number='BA-1-KHA-1001',
            route_name='Ring Road',
            driver=driver_member,
        )
        assignment = StudentBusAssignment.objects.create(
            org=self.org,
            student=self.student_member,
            bus=bus,
            stop_name='Academy Gate',
            stop_latitude=27.7172,
            stop_longitude=85.3240,
        )
        driver_token = RefreshToken.for_user(driver_user).access_token
        student_token = RefreshToken.for_user(self.student_user).access_token
        driver_url = reverse('staff:api_driver_bus_tracking')

        started = self.client.post(
            driver_url,
            data={'action': 'start'},
            content_type='application/json',
            HTTP_AUTHORIZATION=f'Bearer {driver_token}',
        )
        pinged = self.client.post(
            driver_url,
            data={
                'action': 'ping',
                'latitude': 27.7173,
                'longitude': 85.3241,
                'accuracy': 8,
            },
            content_type='application/json',
            HTTP_AUTHORIZATION=f'Bearer {driver_token}',
        )
        picked_up = self.client.post(
            driver_url,
            data={
                'action': 'student_pickup',
                'assignment_id': assignment.id,
            },
            content_type='application/json',
            HTTP_AUTHORIZATION=f'Bearer {driver_token}',
        )
        tracked = self.client.get(
            reverse('staff:api_student_bus_tracking'),
            HTTP_AUTHORIZATION=f'Bearer {student_token}',
        )

        self.assertEqual(started.status_code, 200)
        self.assertEqual(pinged.status_code, 200)
        self.assertEqual(picked_up.status_code, 200)
        self.assertEqual(picked_up.json()['students'][0]['trip_status'], 'picked_up')
        self.assertEqual(tracked.status_code, 200)
        self.assertTrue(tracked.json()['assigned'])
        self.assertTrue(tracked.json()['is_live'])
        self.assertEqual(tracked.json()['bus']['id'], bus.id)
        self.assertEqual(tracked.json()['pickup_status'], 'picked_up')
        self.assertIsNotNone(tracked.json()['estimated_arrival_minutes'])
        self.assertEqual(BusTrackingSession.objects.count(), 1)
        self.assertEqual(BusLocationPing.objects.count(), 1)
        self.assertEqual(BusStudentTripStatus.objects.count(), 1)

    def test_mobile_teacher_work_and_exam_marks_reject_forged_scope(self):
        fixture = self._create_teacher_mobile_fixture()
        token = self._teacher_token()
        work_url = reverse('staff:api_teacher_academic_work')
        due_date = (timezone.localdate() + timedelta(days=7)).isoformat()

        assignment = self.client.post(
            work_url,
            data={
                'action': 'create_assignment',
                'scope_id': fixture['scope'].id,
                'title': 'Mobile algebra task',
                'description': 'Complete the worksheet.',
                'due_date': due_date,
                'total_marks': '20',
                'passing_marks': '8',
            },
            content_type='application/json',
            HTTP_AUTHORIZATION=f'Bearer {token}',
        )
        invalid_homework = self.client.post(
            work_url,
            data={
                'action': 'create_homework',
                'scope_id': fixture['scope'].id,
                'description': 'Invalid choice test.',
                'due_date': due_date,
                'priority': 'forged',
            },
            content_type='application/json',
            HTTP_AUTHORIZATION=f'Bearer {token}',
        )
        forged_scope = self.client.post(
            work_url,
            data={
                'action': 'create_assignment',
                'scope_id': fixture['scope'].id + 99999,
                'title': 'Forged',
                'due_date': due_date,
            },
            content_type='application/json',
            HTTP_AUTHORIZATION=f'Bearer {token}',
        )
        fixture['exam'].status = 'draft'
        fixture['exam'].is_published = False
        fixture['exam'].save(update_fields=['status', 'is_published'])
        marks_url = reverse(
            'staff:api_teacher_exam_marks',
            kwargs={
                'exam_id': fixture['exam'].id,
                'scope_id': fixture['scope'].id,
            },
        )
        marks_context = self.client.get(
            marks_url,
            HTTP_AUTHORIZATION=f'Bearer {token}',
        )
        forged_student = self.client.post(
            marks_url,
            data={
                'marks': [{
                    'student_id': self.staff_member.id,
                    'obtained_marks': '60',
                }],
            },
            content_type='application/json',
            HTTP_AUTHORIZATION=f'Bearer {token}',
        )
        saved = self.client.post(
            marks_url,
            data={
                'marks': [{
                    'student_id': self.student_member.id,
                    'obtained_marks': '88',
                    'remarks': 'Strong work',
                }],
            },
            content_type='application/json',
            HTTP_AUTHORIZATION=f'Bearer {token}',
        )

        self.assertEqual(assignment.status_code, 201)
        self.assertEqual(invalid_homework.status_code, 400)
        self.assertEqual(forged_scope.status_code, 404)
        self.assertEqual(marks_context.status_code, 200)
        self.assertEqual(
            [item['id'] for item in marks_context.json()['students']],
            [self.student_member.id],
        )
        self.assertEqual(forged_student.status_code, 403)
        self.assertEqual(saved.status_code, 200)
        result = ResultRecord.objects.get(
            exam=fixture['exam'],
            subject=fixture['subject'],
            student=self.student_member,
        )
        self.assertEqual(result.obtained_marks, 88)


class TeacherAttendancePageTests(TestCase):
    """Regression test: staff/attendance.html used {% with is_logged=course.id
    in logged_course_ids %} — Django's {% with %} tag only accepts a single
    filter expression, not an `in` boolean expression, so this raised
    TemplateSyntaxError on every single load. No existing test rendered this
    page (only its JSON API siblings were covered), so it went unnoticed.
    Also covers the adjacent unscoped `Classification.objects.get(id=id)`
    IDOR fix in staff.views.attendanceView."""

    def setUp(self):
        self.org = Organization.objects.create(
            name='Attendance Page Org', expire_on=timezone.now() + timedelta(days=30),
        )
        self.classification = Classification.objects.create(org=self.org, name='Grade 5')
        self.teacher_member = member.objects.create(
            org=self.org, name='Teacher One', member_type='staff', gender='Male',
        )
        self.teacher_user = CustomUser.objects.create_user(
            username='attendance-page-teacher', email='attendance-page-teacher@example.com',
            password='testpass123', user_type='3',
        )
        Staff.objects.create(admin=self.teacher_user, org=self.org, member=self.teacher_member)
        self.client.force_login(self.teacher_user)

    def test_page_renders_successfully(self):
        response = self.client.get(
            reverse('staff:attendance', args=[self.classification.id, self.classification.name]),
        )
        self.assertEqual(response.status_code, 200)

    def test_other_orgs_classification_returns_404(self):
        other_org = Organization.objects.create(
            name='Other Attendance Org', expire_on=timezone.now() + timedelta(days=30),
        )
        foreign_classification = Classification.objects.create(org=other_org, name='Secret Class')
        response = self.client.get(
            reverse('staff:attendance', args=[foreign_classification.id, foreign_classification.name]),
        )
        self.assertEqual(response.status_code, 404)
