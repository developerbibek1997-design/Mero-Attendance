import json
import re
import xml.etree.ElementTree as ET

from django.http import JsonResponse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.decorators.csrf import csrf_exempt

from management.models import Organization
from .models import AttendanceRecord, member


HIKVISION_USER_KEYS = (
    "employeeNoString",
    "employeeNo",
    "employee_no",
    "personNo",
    "personId",
    "userId",
    "userID",
    "user_id",
    "deviceUserId",
    "pin",
)

HIKVISION_CARD_KEYS = ("cardNo", "cardNumber", "card", "card_no")
HIKVISION_TIME_KEYS = ("dateTime", "time", "eventTime", "attendanceTime", "verifyTime")


def _find_first(payload, keys):
    if isinstance(payload, dict):
        for key in keys:
            value = payload.get(key)
            if value not in (None, ""):
                return str(value).strip()
        for value in payload.values():
            found = _find_first(value, keys)
            if found:
                return found
    elif isinstance(payload, list):
        for item in payload:
            found = _find_first(item, keys)
            if found:
                return found
    return None


def _strip_xml_namespace(tag):
    return tag.rsplit("}", 1)[-1]


def _xml_to_dict(raw_body):
    root = ET.fromstring(raw_body)

    def convert(node):
        children = list(node)
        if not children:
            return (node.text or "").strip()

        data = {}
        for child in children:
            key = _strip_xml_namespace(child.tag)
            value = convert(child)
            if key in data:
                if not isinstance(data[key], list):
                    data[key] = [data[key]]
                data[key].append(value)
            else:
                data[key] = value
        return data

    return {_strip_xml_namespace(root.tag): convert(root)}


def parse_hikvision_payload(request):
    raw_body = request.body.decode("utf-8", errors="ignore").strip()

    if request.POST:
        for field in ("event_log", "EventNotificationAlert", "data", "payload"):
            if request.POST.get(field):
                raw_body = request.POST[field].strip()
                break
        else:
            return request.POST.dict()

    if not raw_body:
        return {}

    content_type = request.META.get("CONTENT_TYPE", "").lower()
    if "xml" in content_type or raw_body.startswith("<"):
        return _xml_to_dict(raw_body)

    try:
        return json.loads(raw_body)
    except json.JSONDecodeError:
        return {"raw": raw_body}


def parse_hikvision_datetime(value):
    if not value:
        return timezone.now()

    parsed = parse_datetime(str(value).strip())
    if parsed is None:
        return timezone.now()
    if timezone.is_naive(parsed):
        return timezone.make_aware(parsed, timezone.get_current_timezone())
    return parsed


def find_hikvision_member(org, payload):
    device_user_id = _find_first(payload, HIKVISION_USER_KEYS)
    card_no = _find_first(payload, HIKVISION_CARD_KEYS)

    if device_user_id:
        digits = re.sub(r"\D", "", device_user_id)
        if digits:
            found = member.objects.filter(org=org, device_id=int(digits)).first()
            if found:
                return found, device_user_id, card_no

    if card_no:
        found = member.objects.filter(org=org, card=str(card_no).strip()).first()
        if found:
            return found, device_user_id, card_no

    return None, device_user_id, card_no


@csrf_exempt
def hikvision_attendance_event(request, org_serial_key, token):
    """
    Receives Hikvision ISUP/ISAPI event callbacks and stores them as Mero Attendance records.

    Configure the device/server callback URL like:
    /handle/api/hikvision/attendance/<organization_serial_key>/<hikvision_webhook_token>/
    """
    if request.method != "POST":
        return JsonResponse({"error": "POST required."}, status=405)

    try:
        org = Organization.objects.get(serial_key=org_serial_key, activate=True)
    except Organization.DoesNotExist:
        return JsonResponse({"error": "Organization not found or inactive."}, status=404)

    if token != org.new_serial_key:
        return JsonResponse({"error": "Invalid Hikvision token."}, status=403)

    try:
        payload = parse_hikvision_payload(request)
    except ET.ParseError:
        return JsonResponse({"error": "Invalid XML payload."}, status=400)

    memb, device_user_id, card_no = find_hikvision_member(org, payload)
    if not memb:
        return JsonResponse(
            {
                "status": "unmatched_member",
                "message": "No member matched this Hikvision user/card.",
                "device_user_id": device_user_id,
                "card_no": card_no,
            },
            status=404,
        )

    event_time = parse_hikvision_datetime(_find_first(payload, HIKVISION_TIME_KEYS))
    attendance, created = AttendanceRecord.objects.get_or_create(
        mem=memb,
        org=org,
        scanned_time=event_time,
    )

    return JsonResponse(
        {
            "status": "stored" if created else "duplicate",
            "attendance_id": attendance.id,
            "member_id": memb.id,
            "member_name": memb.name,
            "device_user_id": device_user_id,
            "card_no": card_no,
            "scanned_time": attendance.scanned_time.isoformat(),
        },
        status=201 if created else 200,
    )
