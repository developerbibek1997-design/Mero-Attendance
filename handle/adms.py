"""Minimal, tenant-safe ZKTeco ADMS/Push receiver.

The public endpoints intentionally use plain-text responses because ZKTeco
firmware does not speak JSON. A device must be registered by serial number in
Mero Attendance before it can post data; unknown serial numbers are rejected.
"""

import datetime
import hashlib
import re

from django.db import transaction
from django.http import HttpResponse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .models import ADMSAttendanceEvent, AttendanceRecord, Device, member


MAX_ADMS_BODY_BYTES = 1024 * 1024
# ZKTeco Push represents non-whole-hour zones as signed minute offsets.
# The HTTP Date header is GMT and compatible devices use this value to convert
# the server time before synchronising their display clock.
ADMS_TIMEZONE_MINUTES = 345  # Asia/Kathmandu (UTC+05:45)
INACTIVE_MEMBER_STATUSES = {
    'inactive', 'passed_out', 'dropped', 'transferred',
    'suspended', 'restricted', 'resigned',
}


def _plain(message, status=200):
    return HttpResponse(
        message,
        status=status,
        content_type='text/plain; charset=utf-8',
    )


def _client_ip(request):
    forwarded = request.META.get('HTTP_X_FORWARDED_FOR', '')
    value = forwarded.split(',', 1)[0].strip() if forwarded else (
        request.META.get('REMOTE_ADDR') or ''
    )
    return value or None


def _registered_device(request):
    serial_number = (
        request.GET.get('SN')
        or request.GET.get('sn')
        or ''
    ).strip().upper()
    if not serial_number:
        return None, _plain('ERROR: SN REQUIRED', status=400)

    device = (
        Device.objects.select_related('org')
        .filter(
            serial_number__iexact=serial_number,
            connection_mode='adms',
            org__activate=True,
        )
        .first()
    )
    if device is None:
        return None, _plain('ERROR: DEVICE NOT REGISTERED', status=403)

    now = timezone.now()
    device.last_seen_at = now
    device.last_ip_address = _client_ip(request)
    device.push_version = (
        request.GET.get('pushver')
        or request.GET.get('PushVersion')
        or device.push_version
        or ''
    )[:50]
    device.save(update_fields=[
        'last_seen_at', 'last_ip_address', 'push_version',
    ])
    return device, None


def _options_response(device):
    # Conservative Push SDK options supported by common TA/ADMS firmware.
    return '\n'.join((
        f'GET OPTION FROM: {device.serial_number}',
        'Stamp=0',
        'OpStamp=0',
        'PhotoStamp=0',
        'ErrorDelay=60',
        'Delay=10',
        'TransTimes=00:00;14:05',
        'TransInterval=1',
        'TransFlag=1111000000',
        f'TimeZone={ADMS_TIMEZONE_MINUTES}',
        'Realtime=1',
        'Encrypt=0',
    ))


def _parse_event_time(value):
    value = (value or '').strip()
    parsed = parse_datetime(value)
    if parsed is None:
        for pattern in ('%Y-%m-%d %H:%M:%S', '%Y/%m/%d %H:%M:%S'):
            try:
                parsed = datetime.datetime.strptime(value, pattern)
                break
            except ValueError:
                continue
    if parsed is None:
        return None
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
    return parsed


def _parse_attlog_line(raw_line):
    line = raw_line.strip().replace('\x00', '')
    if line.upper().startswith('ATTLOG:'):
        line = line.split(':', 1)[1].strip()
    fields = [item.strip() for item in line.split('\t')]
    if len(fields) < 2 and ',' in line:
        fields = [item.strip() for item in line.split(',')]
    if len(fields) < 2:
        return None
    return {
        'device_user_id': fields[0][:50],
        'event_time': _parse_event_time(fields[1]),
        'punch_state': fields[2][:20] if len(fields) > 2 else '',
        'verify_mode': fields[3][:20] if len(fields) > 3 else '',
        'work_code': fields[4][:50] if len(fields) > 4 else '',
        'raw': line[:1000],
    }


def _event_hash(device, parsed):
    canonical = '|'.join((
        str(device.pk),
        parsed.get('device_user_id') or '',
        parsed['event_time'].isoformat() if parsed.get('event_time') else '',
        parsed.get('punch_state') or '',
        parsed.get('verify_mode') or '',
        parsed.get('work_code') or '',
        parsed.get('raw') or '',
    ))
    return hashlib.sha256(canonical.encode('utf-8')).hexdigest()


def _resolve_member(org, device_user_id):
    value = (device_user_id or '').strip()
    if not value:
        return None, 'unmatched'

    candidates = []
    if re.fullmatch(r'\d+', value):
        candidates = list(
            member.objects.filter(org=org, device_id=int(value))
            .order_by('pk')[:2]
        )
    if not candidates:
        candidates = list(
            member.objects.filter(org=org, card=value)
            .order_by('pk')[:2]
        )
    if len(candidates) > 1:
        return None, 'ambiguous'
    if not candidates:
        return None, 'unmatched'
    matched = candidates[0]
    if matched.status in INACTIVE_MEMBER_STATUSES or matched.black_list:
        return matched, 'inactive'
    return matched, 'stored'


def _store_attendance_line(device, raw_line):
    parsed = _parse_attlog_line(raw_line)
    if parsed is None:
        parsed = {
            'device_user_id': '',
            'event_time': None,
            'punch_state': '',
            'verify_mode': '',
            'work_code': '',
            'raw': raw_line.strip()[:1000],
        }
    event_hash = _event_hash(device, parsed)

    with transaction.atomic():
        receipt, created = ADMSAttendanceEvent.objects.get_or_create(
            device=device,
            event_hash=event_hash,
            defaults={
                'org': device.org,
                'device_user_id': parsed['device_user_id'],
                'event_time': parsed['event_time'],
                'punch_state': parsed['punch_state'],
                'verify_mode': parsed['verify_mode'],
                'work_code': parsed['work_code'],
                'status': 'invalid',
                'raw_payload': parsed['raw'],
            },
        )
        if not created:
            return 'duplicate'
        if not parsed['device_user_id'] or parsed['event_time'] is None:
            return 'invalid'

        matched, receipt_status = _resolve_member(
            device.org,
            parsed['device_user_id'],
        )
        receipt.member = matched
        receipt.status = receipt_status
        if receipt_status == 'stored':
            # Serialize simultaneous pushes for one member. AttendanceRecord is
            # legacy production data without a database uniqueness constraint.
            matched = member.objects.select_for_update().get(
                pk=matched.pk,
                org=device.org,
            )
            attendance, _ = AttendanceRecord.objects.get_or_create(
                mem=matched,
                org=device.org,
                scanned_time=parsed['event_time'],
                defaults={'attendance_method': 'biometric'},
            )
            if not attendance.attendance_method:
                attendance.attendance_method = 'biometric'
                attendance.save(update_fields=['attendance_method'])
            receipt.attendance_record = attendance
        receipt.save(update_fields=[
            'member', 'status', 'attendance_record',
        ])
        return receipt_status


@csrf_exempt
@require_http_methods(['GET', 'POST'])
def adms_cdata(request):
    """Receive ZKTeco ADMS device registration and ATTLOG pushes."""
    device, error = _registered_device(request)
    if error:
        return error

    if request.method == 'GET':
        return _plain(_options_response(device))

    try:
        content_length = int(request.META.get('CONTENT_LENGTH') or 0)
    except (TypeError, ValueError):
        content_length = 0
    if content_length > MAX_ADMS_BODY_BYTES:
        return _plain('ERROR: PAYLOAD TOO LARGE', status=413)

    raw_body = request.body.decode('utf-8', errors='replace')
    table = (request.GET.get('table') or '').strip().upper()
    lines = [line for line in raw_body.splitlines() if line.strip()]
    # OPERLOG/USER/PERSONNEL payloads are acknowledged for protocol
    # compatibility, but this first phase intentionally imports attendance only.
    is_attendance = table in ('', 'ATTLOG') or any(
        line.lstrip().upper().startswith('ATTLOG:') for line in lines
    )
    processed = 0
    if is_attendance:
        for line in lines:
            result = _store_attendance_line(device, line)
            if result in {'stored', 'duplicate'}:
                processed += 1

    Device.objects.filter(pk=device.pk).update(
        last_push_at=timezone.now(),
    )
    return _plain(f'OK: {processed}')


@csrf_exempt
@require_http_methods(['GET'])
def adms_getrequest(request):
    """Keep the device command-poll channel healthy; commands come later."""
    _, error = _registered_device(request)
    return error or _plain('OK')


@csrf_exempt
@require_http_methods(['POST'])
def adms_devicecmd(request):
    """Acknowledge device command results without exposing a command queue."""
    _, error = _registered_device(request)
    return error or _plain('OK')
