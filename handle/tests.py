import json
from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from management.models import Organization
from .models import AttendanceRecord, member


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
