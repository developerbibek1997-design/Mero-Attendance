from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from rest_framework_simplejwt.authentication import JWTAuthentication
from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Q
import datetime
from handle.models import AttendingClassification, Classification, member, AttendanceRecord, Organization


def _mobile_date_fields(org, value, prefix='date'):
    """Return dual AD/BS date strings without trusting a client conversion."""
    result = {
        f'{prefix}_ad': value.isoformat() if value else None,
        f'{prefix}_np': None,
    }
    if value and getattr(org, 'nepali_date', False):
        try:
            import nepali_datetime
            nepali = nepali_datetime.date.from_datetime_date(value)
            result[f'{prefix}_np'] = (
                f'{nepali.year:04d}-{nepali.month:02d}-{nepali.day:02d}'
            )
        except (AttributeError, OverflowError, ValueError):
            pass
    return result

# 1. API to get the classes and organization features for the dashboard
@api_view(['GET'])
@permission_classes([IsAuthenticated])
@authentication_classes([JWTAuthentication])
def api_staff_classes(request):
    try:
        from school.features import get_org_for_user, has_feature

        # 1. Safely determine the organization without crashing
        org = get_org_for_user(request.user)
        if org is None:
            return Response(
                {"error": "No valid staff or admin profile found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        if getattr(request.user, 'user_type', '') == '2':
            staff_classes = [] # Admins usually don't have attending classes
        else:
            staff_classes = (
                AttendingClassification.objects.filter(
                    staff=request.user,
                    classification__org=org,
                )
                .select_related('classification')
                .order_by('classification__name')
            )
        
        # 2. Format the classes
        classes_data = [
            {"id": sc.classification.id, "name": sc.classification.name} 
            for sc in staff_classes
        ]
        
        # 3. Use getattr() so it won't crash if a boolean field is missing in your model
        return Response({
            "org_id": org.id,
            "org_name": org.name,
            "location_based": has_feature(org, 'gps'),
            "wifi_based": has_feature(org, 'wifi'),
            "qr_based": has_feature(org, 'qr'),
            "auto_checkin": getattr(org, 'auto_checkin', False),
            "classes": classes_data
        }, status=status.HTTP_200_OK)
        
    except Exception:
        return Response(
            {"error": "Unable to load the dashboard."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
        


# 2. API to get members of a specific class and their attendance status today
@api_view(['GET'])
@permission_classes([IsAuthenticated])
@authentication_classes([JWTAuthentication])
def api_class_members(request, class_id):
    try:
        from school.features import get_org_for_user, has_perm
        from django.utils import timezone

        org = get_org_for_user(request.user)
        if org is None:
            return Response(
                {"error": "No organization found for this user."},
                status=status.HTTP_404_NOT_FOUND,
            )
        clas = Classification.objects.get(id=class_id, org=org)
        if getattr(request.user, 'user_type', '') == '3':
            assigned = AttendingClassification.objects.filter(
                staff=request.user,
                classification=clas,
                classification__org=org,
            ).exists()
            if not assigned and not has_perm(request.user, 'can_view_members'):
                return Response(
                    {"error": "You are not assigned to this classification."},
                    status=status.HTTP_403_FORBIDDEN,
                )
        
        # Get all members in this classification and organization
        members = member.objects.filter(
            classification=clas,
            org=org,
            status='active',
        ).order_by('name')
        
        # Fetch today's attendance records
        today = timezone.localdate()
        attended_members = AttendanceRecord.objects.filter(
            mem__in=members, 
            org=org,
            scanned_time__date=today
        ).values_list('mem_id', flat=True)
        
        attended_set = set(attended_members)
        
        # Format data for Flutter
        members_data = []
        for m in members:
            members_data.append({
                "id": m.id,
                "name": m.name,
                "phone": m.phone,
                "is_present": m.id in attended_set
            })
            
        return Response({
            "class_name": clas.name,
            "date": today.strftime("%Y-%m-%d"),
            "org_id": org.id,
            "members": members_data
        }, status=status.HTTP_200_OK)
        
    except Classification.DoesNotExist:
        return Response({"error": "Class not found."}, status=status.HTTP_404_NOT_FOUND)


# 3. API to mark a member as present
@api_view(['POST'])
@permission_classes([IsAuthenticated])
@authentication_classes([JWTAuthentication])
def api_mark_present(request):
    from school.features import get_org_for_user, has_perm
    from django.utils import timezone

    member_id = request.data.get('member_id')
    
    if not member_id:
        return Response({"error": "Missing member_id."}, status=status.HTTP_400_BAD_REQUEST)
        
    try:
        org = get_org_for_user(request.user)
        if org is None:
            return Response(
                {"error": "No organization found for this user."},
                status=status.HTTP_404_NOT_FOUND,
            )
        if not has_perm(request.user, 'can_add_attendance'):
            return Response(
                {"error": "You do not have permission to mark attendance."},
                status=status.HTTP_403_FORBIDDEN,
            )
        memb = member.objects.get(id=member_id, org=org)

        if getattr(request.user, 'user_type', '') == '3':
            assigned = AttendingClassification.objects.filter(
                staff=request.user,
                classification_id=memb.classification_id,
                classification__org=org,
            ).exists()
            if not assigned and not has_perm(request.user, 'can_view_members'):
                return Response(
                    {"error": "This member is outside your assigned roster."},
                    status=status.HTTP_403_FORBIDDEN,
                )
        
        # Check if already marked today to avoid duplicates
        today = timezone.localdate()
        already_marked = AttendanceRecord.objects.filter(
            mem=memb,
            org=org,
            scanned_time__date=today
        ).exists()
        
        if already_marked:
            return Response(
                {"status": "already_marked", "message": f"{memb.name} already marked present today."},
                status=status.HTTP_200_OK
            )
        
        # Create the attendance record
        AttendanceRecord.objects.create(
            mem=memb,
            org=org,
            scanned_time=timezone.now(),
        )
        return Response(
            {"status": "success", "message": f"{memb.name} marked present."},
            status=status.HTTP_201_CREATED
        )
        
    except member.DoesNotExist:
        return Response({"error": "Member not found."}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


# 4. API for a mobile client to build its own dynamic menus — merges the legacy
# hardcoded features/permissions with anything superadmin has defined via the
# Dynamic Feature Registry. Reads through the exact same has_feature()/has_perm()
# chokepoint the web UI enforces with, so this payload can never drift from
# what's actually allowed.
@api_view(['GET'])
@permission_classes([IsAuthenticated])
@authentication_classes([JWTAuthentication])
def api_my_permissions(request):
    from school.features import get_org_for_user, has_feature, has_perm, FEATURE_MAP
    from school.navigation import build_portal_navigation
    from handle.models import (
        AttendingClassification,
        DynamicFeature,
        DynamicPermission,
        StaffPermission,
        SubjectTeacherAssignment,
    )
    from django.db.models import Q
    from django.utils import timezone
    from django.utils.text import slugify

    org = get_org_for_user(request.user)
    if org is None and getattr(request.user, 'user_type', '') != '1':
        return Response({"error": "No organization found for this user."}, status=status.HTTP_404_NOT_FOUND)

    feature_keys = sorted(set(list(FEATURE_MAP.keys()) + list(
        DynamicFeature.objects.filter(is_active=True).values_list('key', flat=True)
    )))
    features = {key: has_feature(org, key) for key in feature_keys}

    perm_flags = [f.name for f in StaffPermission._meta.get_fields() if f.name.startswith('can_')]
    perm_flags += list(DynamicPermission.objects.values_list('flag', flat=True))
    permissions = {flag: has_perm(request.user, flag) for flag in sorted(set(perm_flags))}

    profile = getattr(request.user, 'staff', None)
    member_profile = getattr(profile, 'member', None)
    if getattr(request.user, 'user_type', '') == '2':
        navigation, role, role_label = [], 'admin', 'Administrator Workspace'
    elif member_profile is not None:
        navigation, role, role_label = build_portal_navigation(request.user, org)
    else:
        navigation, role, role_label = [], 'staff', 'Staff Workspace'

    member_data = None
    branch_data = None
    classification_data = None
    section_data = None
    courses_data = []
    if member_profile is not None:
        branch = member_profile.branch
        classification = member_profile.classification
        section = member_profile.section
        branch_data = (
            {"id": branch.id, "name": branch.name, "code": branch.code}
            if branch and branch.org_id == org.id else None
        )
        classification_data = (
            {"id": classification.id, "name": classification.name}
            if classification and classification.org_id == org.id else None
        )
        section_data = (
            {"id": section.id, "name": section.name}
            if section and section.org_id == org.id else None
        )
        courses_data = list(
            member_profile.courses.filter(org=org)
            .order_by('name')
            .values('id', 'name')
        )
        member_data = {
            "id": member_profile.id,
            "name": member_profile.name,
            "member_type": member_profile.member_type,
            "status": member_profile.status,
            "branch": branch_data,
            "classification": classification_data,
            "section": section_data,
            "courses": courses_data,
            "live_tracking_enabled": bool(member_profile.live_tracking_enabled),
        }

    assigned_classes = []
    subject_assignments = []
    if org is not None and getattr(request.user, 'user_type', '') == '3':
        assigned_classes = list(
            AttendingClassification.objects.filter(
                staff=request.user,
                classification__org=org,
            )
            .order_by('classification__name')
            .values(
                'classification_id',
                'classification__name',
            )
        )
        assigned_classes = [
            {"id": item["classification_id"], "name": item["classification__name"]}
            for item in assigned_classes
        ]

        today = timezone.localdate()
        assignment_qs = (
            SubjectTeacherAssignment.objects.filter(
                teacher=request.user,
                org=org,
                status='active',
                start_date__lte=today,
            )
            .filter(Q(end_date__isnull=True) | Q(end_date__gte=today))
            .select_related(
                'academic_year', 'branch', 'course',
                'classification', 'section', 'subject',
            )
            .order_by(
                'course__name', 'classification__name',
                'section__name', 'subject__name',
            )
        )
        subject_assignments = [{
            "id": assignment.id,
            "subject": {
                "id": assignment.subject_id,
                "name": assignment.subject.name,
            },
            "course": (
                {"id": assignment.course_id, "name": assignment.course.name}
                if assignment.course_id else None
            ),
            "classification": (
                {
                    "id": assignment.classification_id,
                    "name": assignment.classification.name,
                }
                if assignment.classification_id else None
            ),
            "section": (
                {"id": assignment.section_id, "name": assignment.section.name}
                if assignment.section_id else None
            ),
            "branch": (
                {"id": assignment.branch_id, "name": assignment.branch.name}
                if assignment.branch_id else None
            ),
            "academic_year": (
                {
                    "id": assignment.academic_year_id,
                    "name": assignment.academic_year.name,
                }
                if assignment.academic_year_id else None
            ),
            "is_primary": assignment.is_primary,
        } for assignment in assignment_qs]

    mobile_navigation = [{
        "key": section["key"],
        "label": section["label"],
        "icon": section["icon"],
        "items": [{
            "key": slugify(item["label"]).replace('-', '_'),
            "label": item["label"],
            "icon": item["icon"],
            "feature": item.get("feature") or None,
        } for item in section["links"] if item["label"] != "Log out"],
    } for section in navigation]

    return Response({
        "schema_version": 1,
        "user": {
            "id": request.user.id,
            "email": request.user.email,
            "user_type": request.user.user_type,
        },
        "role": role,
        "role_label": role_label,
        "organization": {
            "id": org.id if org else None,
            "name": org.name if org else None,
            "category": org.category if org else None,
            "nepali_date": bool(getattr(org, 'nepali_date', False)) if org else False,
        },
        # Retained for older mobile clients.
        "org_id": org.id if org else None,
        "member": member_data,
        "features": features,
        "permissions": permissions,
        "attendance_methods": {
            "gps": features.get("gps", False),
            "wifi": features.get("wifi", False),
            "qr": features.get("qr", False),
            "dynamic_qr": features.get("qr_attendance", False),
            "manual": features.get("manual", False),
            "auto_checkin": bool(getattr(org, 'auto_checkin', False)) if org else False,
        },
        "assignments": {
            "classifications": assigned_classes,
            "subjects": subject_assignments,
        },
        "navigation": mobile_navigation,
    }, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
@authentication_classes([JWTAuthentication])
def api_my_attendance_status(request):
    """Server-authoritative working-day, shift, punch, and reminder state.

    The mobile client intentionally receives concrete reminder timestamps so it
    never has to recreate leave, holiday, overnight-shift, or split-shift rules.
    """
    from management.models import Holiday, LeaveReport, Occasion
    from handle.models import AttendanceReminderPolicy
    from school.features import get_org_for_user
    from django.utils import timezone

    org = get_org_for_user(request.user)
    profile = getattr(request.user, 'staff', None)
    memb = getattr(profile, 'member', None)
    if org is None or memb is None or memb.org_id != org.id:
        return Response(
            {"error": "No valid staff member profile was found."},
            status=status.HTTP_404_NOT_FOUND,
        )
    if memb.member_type in {'student', 'trainee'}:
        return Response(
            {"error": "Shift attendance status is available to staff accounts."},
            status=status.HTTP_403_FORBIDDEN,
        )
    if memb.status != 'active' or memb.black_list:
        return Response(
            {"error": "This staff account is not active."},
            status=status.HTTP_403_FORBIDDEN,
        )

    now = timezone.localtime()
    today = now.date()
    current_tz = timezone.get_current_timezone()

    def aware(value):
        return timezone.make_aware(value, current_tz)

    shift_names = [shift.name for shift in memb.active_shifts()]
    window_rows = []
    for order, (start_time, end_time) in enumerate(memb.shift_windows(), start=1):
        start_at = aware(datetime.datetime.combine(today, start_time))
        end_at = aware(datetime.datetime.combine(today, end_time))
        if end_at <= start_at:
            end_at += datetime.timedelta(days=1)
        window_rows.append({
            'order': order,
            'start_at': start_at,
            'end_at': end_at,
            'overnight': end_at.date() != start_at.date(),
        })

    weekday_name = today.strftime('%A')
    weekend = Holiday.objects.filter(
        org=org, holiday__iexact=weekday_name,
    ).exists()
    occasion = (
        Occasion.objects.filter(org=org, date__lte=today)
        .filter(Q(end_date__isnull=True, date=today) | Q(end_date__gte=today))
        .order_by('date')
        .first()
    )
    approved_leave = (
        LeaveReport.objects.filter(
            org=org,
            member=memb,
            approved=True,
            rejected=False,
            gap_start__lte=today,
        )
        .filter(Q(gap_end__gte=today) | Q(gap_end__isnull=True, gap_start=today))
        .select_related('leave_type')
        .order_by('gap_start')
        .first()
    )

    if approved_leave:
        day_reason = 'approved_leave'
        day_reason_label = (
            approved_leave.leave_type.name
            if approved_leave.leave_type else 'Approved leave'
        )
    elif occasion:
        day_reason = 'occasion'
        day_reason_label = occasion.name
    elif weekend:
        day_reason = 'weekend'
        day_reason_label = weekday_name
    else:
        day_reason = 'working_day'
        day_reason_label = 'Working day'
    working_day = day_reason == 'working_day'

    records = list(
        AttendanceRecord.objects.filter(
            mem=memb,
            org=org,
            scanned_time__date=today,
        ).order_by('scanned_time')
    )
    punch_count = len(records)
    expected_punches = max(2, len(window_rows) * 2)
    checked_in = punch_count > 0
    complete = punch_count >= expected_punches and punch_count % 2 == 0
    next_action = 'complete' if complete else (
        'check_out' if punch_count % 2 else 'check_in'
    )

    policy = (
        AttendanceReminderPolicy.objects.filter(org=org).first()
        or AttendanceReminderPolicy(org=org)
    )
    checkin_offsets = policy.normalize_offsets(policy.checkin_offsets)
    checkout_offsets = policy.normalize_offsets(policy.checkout_offsets)
    reminders_enabled = bool(policy.enabled and working_day and window_rows)
    checkin_times = []
    checkout_times = []
    if reminders_enabled and policy.checkin_enabled and not checked_in:
        checkin_times = [
            window_rows[0]['start_at'] + datetime.timedelta(minutes=offset)
            for offset in checkin_offsets
        ]
    if reminders_enabled and policy.checkout_enabled and checked_in and not complete:
        checkout_times = [
            window_rows[-1]['end_at'] + datetime.timedelta(minutes=offset)
            for offset in checkout_offsets
        ]

    first_record = records[0] if records else None
    last_record = records[-1] if len(records) > 1 else None
    late_minutes = None
    if first_record and window_rows:
        first_local = timezone.localtime(first_record.scanned_time)
        late_minutes = max(
            0,
            int((first_local - window_rows[0]['start_at']).total_seconds() // 60),
        )

    return Response({
        'schema_version': 1,
        'server_time': now.isoformat(),
        'date': today.isoformat(),
        'working_day': working_day,
        'day_reason': day_reason,
        'day_reason_label': day_reason_label,
        'shift': {
            'names': shift_names or ['Default shift'],
            'expected_punches': expected_punches,
            'windows': [{
                'order': item['order'],
                'start_at': item['start_at'].isoformat(),
                'end_at': item['end_at'].isoformat(),
                'overnight': item['overnight'],
            } for item in window_rows],
        },
        'attendance': {
            'punch_count': punch_count,
            'checked_in': checked_in,
            'complete': complete,
            'next_action': next_action,
            'check_in_at': (
                timezone.localtime(first_record.scanned_time).isoformat()
                if first_record else None
            ),
            'check_out_at': (
                timezone.localtime(last_record.scanned_time).isoformat()
                if last_record else None
            ),
            'last_method': records[-1].attendance_method if records else None,
            'late_minutes': late_minutes,
        },
        'reminders': {
            'enabled': reminders_enabled,
            'checkin_times': [value.isoformat() for value in checkin_times],
            'checkout_times': [value.isoformat() for value in checkout_times],
        },
    }, status=status.HTTP_200_OK)


def _mobile_staff_context(request):
    from school.features import get_org_for_user

    org = get_org_for_user(request.user)
    profile = getattr(request.user, 'staff', None)
    memb = getattr(profile, 'member', None)
    if org is None or memb is None or memb.org_id != org.id:
        return None, None
    return org, memb


def _validated_coordinates(data):
    try:
        latitude = float(data.get('latitude'))
        longitude = float(data.get('longitude'))
    except (TypeError, ValueError):
        raise ValueError('Valid latitude and longitude are required.')
    if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
        raise ValueError('Coordinates are outside the valid range.')
    accuracy = data.get('accuracy')
    try:
        accuracy = float(accuracy) if accuracy not in (None, '') else None
    except (TypeError, ValueError):
        raise ValueError('Accuracy must be a number.')
    if accuracy is not None and (accuracy < 0 or accuracy > 500):
        raise ValueError('Location accuracy must be within 500 metres.')
    return latitude, longitude, accuracy


def _page_payload(request, queryset, serializer):
    from django.core.paginator import Paginator

    try:
        page_size = min(max(int(request.GET.get('page_size', 20)), 1), 50)
        page_number = max(int(request.GET.get('page', 1)), 1)
    except (TypeError, ValueError):
        page_size, page_number = 20, 1
    page = Paginator(queryset, page_size).get_page(page_number)
    return {
        'results': [serializer(item) for item in page.object_list],
        'page': page.number,
        'page_size': page_size,
        'total': page.paginator.count,
        'pages': page.paginator.num_pages,
        'has_next': page.has_next(),
    }


def _field_visit_payload(visit):
    try:
        report = visit.report
    except ObjectDoesNotExist:
        report = None
    return {
        'id': visit.id,
        'purpose': visit.purpose,
        'destination': visit.destination or visit.area_name,
        'client': (
            {
                'id': visit.client_id,
                'number': visit.client.client_number,
                'name': visit.client.client_org_name,
                'priority': visit.client.priority,
            }
            if visit.client_id else None
        ),
        'created_by': (
            {
                'id': visit.created_by_id,
                'name': (
                    visit.created_by.get_full_name()
                    or visit.created_by.username
                ),
            }
            if visit.created_by_id else None
        ),
        'follow_ups': [{
            'id': follow_up.id,
            'feedback': follow_up.feedback,
            'priority': follow_up.priority,
            'follow_up_date': follow_up.follow_up_date.isoformat(),
            'next_follow_up_date': (
                follow_up.next_follow_up_date.isoformat()
                if follow_up.next_follow_up_date else None
            ),
            'added_by': (
                follow_up.created_by.get_full_name()
                or follow_up.created_by.username
                if follow_up.created_by_id else ''
            ),
        } for follow_up in visit.follow_ups.all()],
        'visit_state': visit.visit_state,
        'approval_status': visit.status,
        'visited_at': visit.visited_at.isoformat(),
        'started_at': visit.started_at.isoformat() if visit.started_at else None,
        'ended_at': visit.ended_at.isoformat() if visit.ended_at else None,
        'latitude': visit.latitude,
        'longitude': visit.longitude,
        'end_latitude': visit.end_latitude,
        'end_longitude': visit.end_longitude,
        'accuracy_meters': visit.accuracy_meters,
        'review_note': visit.review_note,
        'report_note': report.note if report else '',
        'attachment_url': (
            report.attachment.url if report and report.attachment else None
        ),
    }


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
@authentication_classes([JWTAuthentication])
def api_my_field_visits(request):
    from handle.models import Client, ClientFollowUp, FieldVisit, FieldVisitReport
    from school.features import has_feature, has_perm
    from django.db import transaction
    from django.utils import timezone

    org, memb = _mobile_staff_context(request)
    if org is None:
        return Response({'error': 'No valid staff profile was found.'}, status=404)
    if not has_feature(org, 'field_visits'):
        return Response({'error': 'Field visits are not enabled.'}, status=403)

    can_view = has_perm(request.user, 'can_view_field_visits')
    can_send = has_perm(request.user, 'can_send_location')
    if request.method == 'GET':
        if not (can_view or can_send):
            return Response({'error': 'You do not have field visit access.'}, status=403)
        queryset = (
            FieldVisit.objects.filter(org=org, member=memb)
            .select_related('client', 'report', 'created_by')
            .prefetch_related('follow_ups__created_by')
            .order_by('-visited_at')
        )
        visit_state = request.GET.get('visit_state', '').strip()
        if visit_state:
            queryset = queryset.filter(visit_state=visit_state)
        payload = _page_payload(request, queryset, _field_visit_payload)
        can_manage_clients = (
            has_feature(org, 'clients')
            and has_perm(request.user, 'can_manage_clients')
        )
        can_view_clients = (
            has_feature(org, 'clients')
            and has_perm(request.user, 'can_view_clients')
        )
        payload['can_manage_clients'] = can_manage_clients
        payload['client_options'] = list(
            Client.objects.filter(
                org=org,
                is_active=True,
                created_by=request.user,
            ).order_by('-priority', 'client_org_name').values(
                'id', 'client_number', 'client_org_name', 'priority',
            )
        ) if (can_manage_clients or can_view_clients) else []
        return Response(payload)

    if not can_send:
        return Response({'error': 'You cannot start field visits.'}, status=403)
    if memb.status != 'active' or memb.black_list:
        return Response({'error': 'This staff account is not active.'}, status=403)

    purpose = (request.data.get('purpose') or '').strip()
    destination = (request.data.get('destination') or '').strip()
    if not purpose or not destination:
        return Response(
            {'error': 'Purpose and destination are required.'},
            status=status.HTTP_400_BAD_REQUEST,
        )
    try:
        latitude, longitude, accuracy = _validated_coordinates(request.data)
    except ValueError as exc:
        return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    can_manage_clients = (
        has_feature(org, 'clients')
        and has_perm(request.user, 'can_manage_clients')
    )
    client = None
    client_id = request.data.get('client_id')
    if client_id not in (None, ''):
        client = Client.objects.filter(pk=client_id, org=org).first()
        if client is None:
            return Response({'error': 'Client not found.'}, status=404)
    new_client_name = (request.data.get('client_org_name') or '').strip()
    new_client_priority = (request.data.get('client_priority') or 'medium').strip()
    new_client_phone = ''.join(
        char for char in str(request.data.get('client_phone') or '')
        if char.isdigit()
    )
    if client is None and new_client_name:
        if not can_manage_clients:
            return Response(
                {'error': 'You cannot create clients from a field visit.'},
                status=403,
            )
        if new_client_priority not in dict(Client.PRIORITY_CHOICES):
            return Response({'error': 'Invalid client priority.'}, status=400)
        if request.data.get('client_phone') and not new_client_phone:
            return Response({'error': 'Client phone must contain digits.'}, status=400)

    log_follow_up = str(request.data.get('log_follow_up', '')).lower() in (
        '1', 'true', 'yes', 'on',
    )
    feedback = (request.data.get('feedback') or '').strip()
    if log_follow_up and (
        (client is None and not new_client_name) or not feedback
    ):
        return Response(
            {'error': 'Choose or create a client and add feedback to log a follow-up.'},
            status=400,
        )
    follow_up_priority = (request.data.get('follow_up_priority') or 'medium').strip()
    if follow_up_priority not in dict(ClientFollowUp.PRIORITY_CHOICES):
        return Response({'error': 'Invalid follow-up priority.'}, status=400)

    attachment = request.FILES.get('attachment')
    if attachment and attachment.size > 10 * 1024 * 1024:
        return Response({'error': 'Attachment must be 10 MB or smaller.'}, status=400)
    note = (request.data.get('note') or '').strip()

    with transaction.atomic():
        if client is None and new_client_name:
            client = Client.create_for_org(
                org=org,
                client_number=(request.data.get('client_number') or '').strip(),
                client_org_name=new_client_name,
                contact_person=(request.data.get('contact_person') or '').strip(),
                phone=int(new_client_phone) if new_client_phone else None,
                address=(request.data.get('client_address') or '').strip(),
                priority=new_client_priority,
                created_by=request.user,
            )
        visit = FieldVisit.objects.create(
            org=org,
            member=memb,
            latitude=latitude,
            longitude=longitude,
            area_name=destination,
            accuracy_meters=accuracy,
            client=client,
            purpose=purpose,
            destination=destination,
            visit_state='in_progress',
            started_at=timezone.now(),
            created_by=request.user,
        )
        if note or attachment:
            FieldVisitReport.objects.create(
                visit=visit, note=note, attachment=attachment,
            )
        if log_follow_up:
            ClientFollowUp.objects.create(
                client=client,
                org=org,
                visited_by=memb,
                feedback=feedback,
                priority=follow_up_priority,
                follow_up_date=request.data.get('follow_up_date') or timezone.localdate(),
                next_follow_up_date=request.data.get('next_follow_up_date') or None,
                field_visit=visit,
                created_by=request.user,
            )
    visit = (
        FieldVisit.objects.select_related('client', 'report', 'created_by')
        .prefetch_related('follow_ups__created_by')
        .get(pk=visit.pk)
    )
    return Response(_field_visit_payload(visit), status=status.HTTP_201_CREATED)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@authentication_classes([JWTAuthentication])
def api_my_field_visit_action(request, visit_id):
    from handle.models import FieldVisit, FieldVisitReport
    from school.features import has_feature, has_perm
    from django.db import transaction
    from django.utils import timezone

    org, memb = _mobile_staff_context(request)
    if org is None:
        return Response({'error': 'No valid staff profile was found.'}, status=404)
    if not has_feature(org, 'field_visits') or not has_perm(
        request.user, 'can_send_location'
    ):
        return Response({'error': 'You cannot update field visits.'}, status=403)
    try:
        latitude, longitude, accuracy = _validated_coordinates(request.data)
    except ValueError as exc:
        return Response({'error': str(exc)}, status=400)

    with transaction.atomic():
        visit = (
            FieldVisit.objects.select_for_update()
            .select_related('client', 'report')
            .filter(pk=visit_id, org=org, member=memb)
            .first()
        )
        if visit is None:
            return Response({'error': 'Field visit not found.'}, status=404)
        action = (request.data.get('action') or '').strip()
        if action != 'end':
            return Response({'error': 'Unsupported field visit action.'}, status=400)
        if visit.visit_state == 'completed':
            return Response(_field_visit_payload(visit), status=200)
        if visit.visit_state != 'in_progress':
            return Response({'error': 'Only an active visit can be ended.'}, status=409)
        visit.visit_state = 'completed'
        visit.end_latitude = latitude
        visit.end_longitude = longitude
        visit.ended_at = timezone.now()
        visit.accuracy_meters = accuracy or visit.accuracy_meters
        visit.save(update_fields=[
            'visit_state', 'end_latitude', 'end_longitude',
            'ended_at', 'accuracy_meters',
        ])
        note = (request.data.get('note') or '').strip()
        if note:
            report, _ = FieldVisitReport.objects.get_or_create(visit=visit)
            report.note = '\n'.join(filter(None, [report.note, note]))
            report.save(update_fields=['note'])
    return Response(_field_visit_payload(visit), status=200)


def _tracking_time_allowed(memb, now):
    local_time = now.timetz().replace(tzinfo=None)
    for start, end in memb.shift_windows():
        if end <= start:
            if local_time >= start or local_time <= end:
                return True
        elif start <= local_time <= end:
            return True
    return False


def _tracking_session_payload(session):
    return {
        'id': session.id,
        'status': session.status,
        'started_at': session.started_at.isoformat(),
        'stopped_at': session.stopped_at.isoformat() if session.stopped_at else None,
        'break_started_at': (
            session.break_started_at.isoformat()
            if session.break_started_at else None
        ),
        'last_ping_at': (
            session.last_ping_at.isoformat() if session.last_ping_at else None
        ),
        'last_latitude': session.last_latitude,
        'last_longitude': session.last_longitude,
        'ping_count': getattr(session, 'ping_count', None),
    }


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
@authentication_classes([JWTAuthentication])
def api_live_tracking(request):
    from handle.models import LiveTrackingSession, LocationPing, member
    from school.features import has_feature, has_perm
    from django.db import transaction
    from django.db.models import Count
    from django.utils import timezone

    org, memb = _mobile_staff_context(request)
    if org is None:
        return Response({'error': 'No valid staff profile was found.'}, status=404)
    if not has_feature(org, 'field_visits') or not has_perm(
        request.user, 'can_send_location'
    ):
        return Response({'error': 'Live tracking is not available.'}, status=403)
    if not memb.live_tracking_enabled:
        return Response(
            {'error': 'Live tracking is not enabled for this staff member.'},
            status=403,
        )

    sessions = LiveTrackingSession.objects.filter(
        org=org, member=memb,
    ).annotate(ping_count=Count('pings'))
    if request.method == 'GET':
        active = sessions.filter(status='active').first()
        history = sessions.exclude(status='active')[:10]
        return Response({
            'enabled': True,
            'active': _tracking_session_payload(active) if active else None,
            'history': [_tracking_session_payload(item) for item in history],
            'policy': {
                'minimum_ping_interval_seconds': 20,
                'maximum_accuracy_meters': 500,
                'shift_restricted': True,
            },
        })

    action = (request.data.get('action') or '').strip()
    now = timezone.localtime()
    if action not in {'stop'} and not _tracking_time_allowed(memb, now):
        return Response(
            {'error': 'Tracking is allowed only during your assigned shift.'},
            status=409,
        )

    if action == 'start':
        with transaction.atomic():
            member.objects.select_for_update().get(pk=memb.pk, org=org)
            active = LiveTrackingSession.objects.filter(
                org=org, member=memb, status='active',
            ).first()
            if active is None:
                active = LiveTrackingSession.objects.create(
                    org=org, member=memb, started_by=request.user,
                )
        active.ping_count = active.pings.count()
        return Response(_tracking_session_payload(active), status=200)

    active = LiveTrackingSession.objects.filter(
        org=org, member=memb, status='active',
    ).first()
    if active is None:
        return Response({'error': 'No live tracking session is active.'}, status=409)

    if action == 'stop':
        active.status = 'stopped'
        active.stopped_at = timezone.now()
        active.break_started_at = None
        active.save(update_fields=['status', 'stopped_at', 'break_started_at'])
        active.ping_count = active.pings.count()
        return Response(_tracking_session_payload(active), status=200)

    if action not in {'ping', 'break_start', 'break_end', 'checkpoint'}:
        return Response({'error': 'Unsupported tracking action.'}, status=400)
    try:
        latitude, longitude, accuracy = _validated_coordinates(request.data)
    except ValueError as exc:
        return Response({'error': str(exc)}, status=400)
    battery = request.data.get('battery_percentage')
    try:
        battery = int(battery) if battery not in (None, '') else None
    except (TypeError, ValueError):
        return Response({'error': 'Battery percentage must be a number.'}, status=400)
    if battery is not None and not 0 <= battery <= 100:
        return Response({'error': 'Battery percentage must be between 0 and 100.'}, status=400)
    if (
        active.last_ping_at
        and action == 'ping'
        and timezone.now() - active.last_ping_at < datetime.timedelta(seconds=20)
    ):
        return Response({'error': 'Location update received too soon.'}, status=429)

    ping_type = action if action != 'ping' else 'regular'
    with transaction.atomic():
        LocationPing.objects.create(
            member=memb,
            org=org,
            session=active,
            latitude=latitude,
            longitude=longitude,
            accuracy_meters=accuracy,
            ping_type=ping_type,
            battery_percentage=battery,
        )
        active.last_ping_at = timezone.now()
        active.last_latitude = latitude
        active.last_longitude = longitude
        if action == 'break_start':
            active.break_started_at = timezone.now()
        elif action == 'break_end':
            active.break_started_at = None
        active.save(update_fields=[
            'last_ping_at', 'last_latitude', 'last_longitude',
            'break_started_at',
        ])
    active.ping_count = active.pings.count()
    return Response(_tracking_session_payload(active), status=201)


def _task_payload(instance, include_detail=False):
    task = instance.task
    payload = {
        'id': instance.id,
        'task_id': task.id,
        'title': task.title,
        'description': task.description,
        'priority': task.priority,
        'task_type': task.task_type,
        'due_date': instance.due_date.isoformat(),
        'due_time': instance.due_time.isoformat() if instance.due_time else None,
        'status': instance.status,
        'approval_status': instance.approval_status,
        'requires_approval': task.requires_approval,
        'completion_note': instance.completion_note,
        'rejection_reason': instance.rejection_reason,
        'updated_at': instance.updated_at.isoformat(),
    }
    if include_detail:
        payload['history'] = [{
            'id': log.id,
            'old_status': log.old_status,
            'new_status': log.new_status,
            'note': log.note,
            'changed_at': log.changed_at.isoformat(),
        } for log in instance.update_logs.select_related('changed_by').all()[:50]]
        payload['attachments'] = [{
            'id': attachment.id,
            'label': attachment.label,
            'url': attachment.file.url,
            'uploaded_at': attachment.uploaded_at.isoformat(),
        } for attachment in instance.attachments.all()]
        if instance.proof_attachment:
            payload['proof_url'] = instance.proof_attachment.url
        elif task.attachment:
            payload['proof_url'] = task.attachment.url
        else:
            payload['proof_url'] = None
    return payload


@api_view(['GET'])
@permission_classes([IsAuthenticated])
@authentication_classes([JWTAuthentication])
def api_my_tasks(request):
    from handle.models import TaskInstance
    from school.features import has_feature, has_perm
    from django.utils import timezone

    org, memb = _mobile_staff_context(request)
    if org is None:
        return Response({'error': 'No valid staff profile was found.'}, status=404)
    if not has_feature(org, 'tasks') or not has_perm(request.user, 'can_view_tasks'):
        return Response({'error': 'Task access is not available.'}, status=403)
    queryset = (
        TaskInstance.objects.filter(assigned_member=memb, task__org=org)
        .select_related('task')
        .order_by('due_date', 'due_time', '-task__priority')
    )
    for stale in queryset.filter(
        due_date__lt=timezone.localdate(),
        status__in=['pending', 'in_progress'],
    )[:100]:
        stale.refresh_overdue_status()
    summary_queryset = TaskInstance.objects.filter(
        assigned_member=memb, task__org=org,
    )
    status_filter = request.GET.get('status', '').strip()
    if status_filter:
        queryset = queryset.filter(status=status_filter)
    search = request.GET.get('search', '').strip()
    if search:
        queryset = queryset.filter(
            Q(task__title__icontains=search) |
            Q(task__description__icontains=search)
        )
    payload = _page_payload(request, queryset, _task_payload)
    payload['summary'] = {
        'pending': summary_queryset.filter(status='pending').count(),
        'in_progress': summary_queryset.filter(status='in_progress').count(),
        'overdue': summary_queryset.filter(
            status__in=['overdue', 'missed_absence'],
        ).count(),
        'completed': summary_queryset.filter(status='completed').count(),
    }
    return Response(payload)


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
@authentication_classes([JWTAuthentication])
def api_my_task_detail(request, instance_id):
    from handle.models import TaskInstance, TaskUpdateLog
    from school.features import has_feature, has_perm
    from django.db import transaction
    from django.utils import timezone

    org, memb = _mobile_staff_context(request)
    if org is None:
        return Response({'error': 'No valid staff profile was found.'}, status=404)
    if not has_feature(org, 'tasks') or not has_perm(request.user, 'can_view_tasks'):
        return Response({'error': 'Task access is not available.'}, status=403)
    instance = (
        TaskInstance.objects.filter(
            pk=instance_id, assigned_member=memb, task__org=org,
        )
        .select_related('task')
        .prefetch_related('update_logs', 'attachments')
        .first()
    )
    if instance is None:
        return Response({'error': 'Task not found.'}, status=404)
    if request.method == 'GET':
        return Response(_task_payload(instance, include_detail=True))

    action = (request.data.get('action') or '').strip()
    note = (request.data.get('note') or '').strip()
    transitions = {
        'start': ({'pending', 'rework_required'}, 'in_progress'),
        'complete': (
            {'pending', 'in_progress', 'rework_required', 'overdue'},
            'completed',
        ),
        'not_completed': (
            {'pending', 'in_progress', 'rework_required', 'overdue'},
            'not_completed',
        ),
    }
    if action == 'comment':
        if not note:
            return Response({'error': 'Comment cannot be empty.'}, status=400)
        TaskUpdateLog.objects.create(
            instance=instance,
            changed_by=request.user,
            old_status=instance.status,
            new_status=instance.status,
            note=note,
        )
        return Response(_task_payload(instance, include_detail=True), status=201)
    if action not in transitions:
        return Response({'error': 'Unsupported task action.'}, status=400)

    allowed_states, next_status = transitions[action]
    if instance.status == next_status:
        return Response(_task_payload(instance, include_detail=True), status=200)
    if instance.status not in allowed_states:
        return Response(
            {'error': f'Task cannot move from {instance.status} to {next_status}.'},
            status=409,
        )
    if action == 'not_completed' and not note:
        return Response({'error': 'Explain why the task was not completed.'}, status=400)

    proof = request.FILES.get('proof')
    if proof and proof.size > 10 * 1024 * 1024:
        return Response({'error': 'Proof attachment must be 10 MB or smaller.'}, status=400)
    with transaction.atomic():
        locked = TaskInstance.objects.select_for_update().get(pk=instance.pk)
        old_status = locked.status
        locked.status = next_status
        update_fields = ['status', 'updated_at']
        if action == 'complete':
            locked.completion_note = note
            locked.completed_at = timezone.now()
            locked.approval_status = (
                'pending_approval'
                if locked.task.requires_approval else 'not_required'
            )
            update_fields += [
                'completion_note', 'completed_at', 'approval_status',
            ]
            if proof:
                locked.proof_attachment = proof
                update_fields.append('proof_attachment')
        elif action == 'not_completed':
            locked.not_done_reason = 'other'
            locked.not_done_detail = note
            update_fields += ['not_done_reason', 'not_done_detail']
        locked.save(update_fields=update_fields)
        TaskUpdateLog.objects.create(
            instance=locked,
            changed_by=request.user,
            old_status=old_status,
            new_status=next_status,
            note=note,
        )
    instance = (
        TaskInstance.objects.filter(pk=instance.pk)
        .select_related('task')
        .prefetch_related('update_logs', 'attachments')
        .get()
    )
    return Response(_task_payload(instance, include_detail=True), status=200)


def _notice_payload(notice, read_ids):
    return {
        'id': notice.id,
        'title': notice.title,
        'body': notice.body,
        'priority': notice.priority,
        'audience': notice.audience,
        'audience_label': notice.audience_label(),
        'publish_at': notice.publish_at.isoformat(),
        'expires_at': (
            notice.expires_at.isoformat() if notice.expires_at else None
        ),
        'attachment_url': notice.attachment.url if notice.attachment else None,
        'is_read': notice.id in read_ids,
    }


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
@authentication_classes([JWTAuthentication])
def api_my_notices(request):
    from handle.models import Notice, NoticeRead
    from school.features import has_feature, has_perm
    from django.utils import timezone

    org, memb = _mobile_staff_context(request)
    if org is None:
        return Response({'error': 'No valid portal profile was found.'}, status=404)
    is_student = memb.member_type in ('student', 'trainee')
    if not has_feature(org, 'notices') or (
        not is_student and not has_perm(request.user, 'can_view_notices')
    ):
        return Response({'error': 'Notice access is not available.'}, status=403)

    now = timezone.now()
    candidates = (
        Notice.objects.filter(org=org, publish_at__lte=now)
        .filter(Q(expires_at__isnull=True) | Q(expires_at__gt=now))
        .select_related(
            'branch', 'classification', 'section', 'course',
            'shift', 'target_member',
        )
        .order_by('-publish_at', '-id')
    )
    available = [
        notice for notice in candidates if notice.is_for_member(memb)
    ]
    if request.method == 'POST':
        action = (request.data.get('action') or '').strip()
        if action == 'mark_all_read':
            existing_ids = set(NoticeRead.objects.filter(
                member=memb,
                notice_id__in=[item.id for item in available],
            ).values_list('notice_id', flat=True))
            NoticeRead.objects.bulk_create([
                NoticeRead(notice=item, member=memb)
                for item in available if item.id not in existing_ids
            ])
            return Response({'status': 'success'})
        notice_id = request.data.get('notice_id')
        notice = next(
            (item for item in available if str(item.id) == str(notice_id)),
            None,
        )
        if notice is None:
            return Response({'error': 'Notice not found.'}, status=404)
        if action == 'mark_unread':
            NoticeRead.objects.filter(notice=notice, member=memb).delete()
        elif action == 'mark_read':
            NoticeRead.objects.get_or_create(notice=notice, member=memb)
        else:
            return Response({'error': 'Unsupported notice action.'}, status=400)
        return Response({'status': 'success'})

    read_ids = set(NoticeRead.objects.filter(
        member=memb,
        notice_id__in=[item.id for item in available],
    ).values_list('notice_id', flat=True))
    show = request.GET.get('show', '').strip()
    if show == 'unread':
        available = [item for item in available if item.id not in read_ids]
    page = _page_payload(
        request,
        available,
        lambda item: _notice_payload(item, read_ids),
    )
    page['unread_count'] = sum(
        1 for item in available if item.id not in read_ids
    )
    return Response(page)


def _event_payload(event, org=None):
    payload = {
        'id': event.id,
        'title': event.title,
        'event_type': event.event_type,
        'start_date': event.start_date.isoformat(),
        'end_date': event.end_date.isoformat(),
        'location': event.location or '',
        'description': event.description or '',
        'status': event.status,
        'branch': (
            {'id': event.branch_id, 'name': event.branch.name}
            if event.branch_id else None
        ),
    }
    if org is not None:
        payload.update(_mobile_date_fields(org, event.start_date, 'start_date'))
        payload.update(_mobile_date_fields(org, event.end_date, 'end_date'))
    return payload


@api_view(['GET'])
@permission_classes([IsAuthenticated])
@authentication_classes([JWTAuthentication])
def api_my_events(request):
    from handle.models import Event
    from school.features import has_feature, has_perm

    org, memb = _mobile_staff_context(request)
    if org is None:
        return Response({'error': 'No valid portal profile was found.'}, status=404)
    is_student = memb.member_type in ('student', 'trainee')
    if not has_feature(org, 'events') or (
        not is_student and not has_perm(request.user, 'can_view_events')
    ):
        return Response({'error': 'Event access is not available.'}, status=403)
    queryset = (
        Event.objects.filter(org=org)
        .filter(Q(branch__isnull=True) | Q(branch_id=memb.branch_id))
        .select_related('branch')
        .order_by('start_date', 'id')
    )
    status_filter = request.GET.get('status', '').strip()
    if status_filter:
        queryset = queryset.filter(status=status_filter)
    return Response(_page_payload(
        request,
        queryset,
        lambda event: _event_payload(event, org),
    ))


@api_view(['GET'])
@permission_classes([IsAuthenticated])
@authentication_classes([JWTAuthentication])
def api_my_calendar(request):
    from handle.models import Event, TaskInstance
    from management.models import Holiday, LeaveReport, Occasion
    from school.features import has_feature, has_perm
    from django.utils import timezone

    org, memb = _mobile_staff_context(request)
    if org is None:
        return Response({'error': 'No valid portal profile was found.'}, status=404)
    today = timezone.localdate()

    def parse_date(value, default):
        try:
            return datetime.date.fromisoformat(value)
        except (TypeError, ValueError):
            return default

    date_from = parse_date(request.GET.get('from_date'), today)
    date_to = parse_date(
        request.GET.get('to_date'),
        today + datetime.timedelta(days=60),
    )
    if date_from > date_to:
        date_from, date_to = date_to, date_from
    if (date_to - date_from).days > 120:
        return Response(
            {'error': 'Calendar range cannot exceed 120 days.'},
            status=400,
        )
    items = []
    is_student = memb.member_type in ('student', 'trainee')
    if has_feature(org, 'events') and (
        is_student or has_perm(request.user, 'can_view_events')
    ):
        events = (
            Event.objects.filter(
                org=org,
                start_date__lte=date_to,
                end_date__gte=date_from,
            )
            .filter(Q(branch__isnull=True) | Q(branch_id=memb.branch_id))
            .select_related('branch')
        )
        items.extend({
            'id': f'event-{event.id}',
            'type': 'event',
            'title': event.title,
            'start_date': event.start_date.isoformat(),
            'end_date': event.end_date.isoformat(),
            'color': '#2563EB',
        } for event in events)
    occasions = Occasion.objects.filter(
        org=org,
        date__lte=date_to,
    ).filter(Q(end_date__isnull=True) | Q(end_date__gte=date_from))
    items.extend({
        'id': f'occasion-{item.id}',
        'type': 'holiday',
        'title': item.name,
        'start_date': item.date.isoformat(),
        'end_date': (item.end_date or item.date).isoformat(),
        'color': '#DC2626',
    } for item in occasions)
    if has_feature(org, 'tasks') and has_perm(
        request.user, 'can_view_tasks'
    ):
        tasks = TaskInstance.objects.filter(
            assigned_member=memb,
            task__org=org,
            due_date__range=(date_from, date_to),
        ).select_related('task')
        items.extend({
            'id': f'task-{item.id}',
            'type': 'task',
            'title': item.task.title,
            'start_date': item.due_date.isoformat(),
            'end_date': item.due_date.isoformat(),
            'color': '#EA580C',
        } for item in tasks)
    leaves = LeaveReport.objects.filter(
        org=org,
        member=memb,
        approved=True,
        gap_start__lte=date_to,
        gap_end__gte=date_from,
    ).select_related('leave_type')
    items.extend({
        'id': f'leave-{item.id}',
        'type': 'leave',
        'title': item.leave_type.name if item.leave_type else 'Approved leave',
        'start_date': item.gap_start.isoformat(),
        'end_date': item.gap_end.isoformat(),
        'color': '#7C3AED',
    } for item in leaves)
    for item in items:
        start = datetime.date.fromisoformat(item['start_date'])
        end = datetime.date.fromisoformat(item['end_date'])
        item.update(_mobile_date_fields(org, start, 'start_date'))
        item.update(_mobile_date_fields(org, end, 'end_date'))
    return Response({
        'from_date': date_from.isoformat(),
        'to_date': date_to.isoformat(),
        'nepali_date': bool(getattr(org, 'nepali_date', False)),
        **_mobile_date_fields(org, date_from, 'from_date'),
        **_mobile_date_fields(org, date_to, 'to_date'),
        'weekend_days': list(
            Holiday.objects.filter(org=org).values_list('holiday', flat=True)
        ),
        'items': sorted(items, key=lambda item: (
            item['start_date'], item['title'],
        )),
    })


def _complaint_payload(complaint, include_messages=False):
    payload = {
        'id': complaint.id,
        'complaint_type': complaint.complaint_type,
        'subject': complaint.subject,
        'description': complaint.description,
        'priority': complaint.priority,
        'status': complaint.status,
        'admin_remarks': complaint.admin_remarks or '',
        'resolution_date': (
            complaint.resolution_date.isoformat()
            if complaint.resolution_date else None
        ),
        'created_at': complaint.created_at.isoformat(),
        'updated_at': complaint.updated_at.isoformat(),
    }
    if include_messages:
        payload['messages'] = [{
            'id': message.id,
            'message': message.message,
            'is_staff_reply': message.is_staff_reply,
            'created_at': message.created_at.isoformat(),
            'attachment_url': (
                message.attachment.url if message.attachment else None
            ),
        } for message in complaint.messages.all()]
    return payload


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
@authentication_classes([JWTAuthentication])
def api_my_complaints(request):
    from handle.models import Complaint, ComplaintMessage
    from school.features import has_feature, has_perm
    from django.db import transaction

    org, memb = _mobile_staff_context(request)
    if org is None:
        return Response({'error': 'No valid portal profile was found.'}, status=404)
    is_student = memb.member_type in ('student', 'trainee')
    if not has_feature(org, 'complaints') or (
        not is_student and not has_perm(request.user, 'can_view_complaints')
    ):
        return Response({'error': 'Complaint access is not available.'}, status=403)
    queryset = Complaint.objects.filter(
        org=org, filed_by=memb,
    ).order_by('-created_at')
    if request.method == 'GET':
        return Response(_page_payload(request, queryset, _complaint_payload))

    subject = (request.data.get('subject') or '').strip()
    description = (request.data.get('description') or '').strip()
    complaint_type = (request.data.get('complaint_type') or '').strip()
    priority = (request.data.get('priority') or 'medium').strip()
    if not subject or not description or not complaint_type:
        return Response(
            {'error': 'Category, subject, and description are required.'},
            status=400,
        )
    if priority not in dict(Complaint.PRIORITY_CHOICES):
        return Response({'error': 'Invalid complaint priority.'}, status=400)
    attachment = request.FILES.get('attachment')
    if attachment and attachment.size > 10 * 1024 * 1024:
        return Response({'error': 'Evidence must be 10 MB or smaller.'}, status=400)
    with transaction.atomic():
        complaint = Complaint.objects.create(
            org=org,
            branch=memb.branch,
            filed_by=memb,
            complaint_type=complaint_type[:100],
            subject=subject[:255],
            description=description,
            priority=priority,
        )
        if attachment:
            ComplaintMessage.objects.create(
                complaint=complaint,
                author=request.user,
                message='Evidence attached with complaint.',
                attachment=attachment,
            )
    return Response(_complaint_payload(complaint), status=201)


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
@authentication_classes([JWTAuthentication])
def api_my_complaint_detail(request, complaint_id):
    from handle.models import Complaint, ComplaintMessage
    from school.features import has_feature, has_perm
    from django.db import transaction

    org, memb = _mobile_staff_context(request)
    if org is None:
        return Response({'error': 'No valid portal profile was found.'}, status=404)
    is_student = memb.member_type in ('student', 'trainee')
    if not has_feature(org, 'complaints') or (
        not is_student and not has_perm(request.user, 'can_view_complaints')
    ):
        return Response({'error': 'Complaint access is not available.'}, status=403)
    complaint = (
        Complaint.objects.filter(
            pk=complaint_id, org=org, filed_by=memb,
        )
        .prefetch_related('messages')
        .first()
    )
    if complaint is None:
        return Response({'error': 'Complaint not found.'}, status=404)
    if request.method == 'GET':
        return Response(_complaint_payload(complaint, include_messages=True))
    action = (request.data.get('action') or '').strip()
    if action == 'message':
        message_text = (request.data.get('message') or '').strip()
        if not message_text:
            return Response({'error': 'Message cannot be empty.'}, status=400)
        if complaint.status == 'closed':
            return Response({'error': 'A closed complaint cannot be updated.'}, status=409)
        ComplaintMessage.objects.create(
            complaint=complaint,
            author=request.user,
            message=message_text,
        )
    elif action == 'close':
        if complaint.status not in {'resolved', 'rejected'}:
            return Response(
                {'error': 'Only a resolved or rejected complaint can be closed.'},
                status=409,
            )
        with transaction.atomic():
            complaint.status = 'closed'
            complaint.save(update_fields=['status', 'updated_at'])
    else:
        return Response({'error': 'Unsupported complaint action.'}, status=400)
    complaint = Complaint.objects.prefetch_related('messages').get(
        pk=complaint.pk,
    )
    return Response(_complaint_payload(complaint, include_messages=True))


def _mobile_student_context(request):
    org, memb = _mobile_staff_context(request)
    if (
        org is None
        or memb is None
        or memb.member_type not in ('student', 'trainee')
    ):
        return None, None
    return org, memb


def _student_mobile_scope(
    org, memb, *, course_path, classification_path, section_path,
):
    from handle.models import StudentCourseEnrollment
    from django.utils import timezone

    today = timezone.localdate()
    enrollments = list(
        StudentCourseEnrollment.objects.filter(
            org=org,
            student=memb,
            start_date__lte=today,
        )
        .exclude(status='cancelled')
        .filter(Q(end_date__isnull=True) | Q(end_date__gte=today))
        .select_related(
            'academic_year', 'branch', 'course', 'classification', 'section',
        )
    )
    scope = Q(pk__in=[])
    for enrollment in enrollments:
        exact = (
            (
                Q(**{f'{course_path}_id': enrollment.course_id})
                | Q(**{f'{course_path}__isnull': True})
            )
            & Q(**{
                f'{classification_path}_id': enrollment.classification_id,
            })
        )
        section_scope = Q(**{f'{section_path}__isnull': True})
        if enrollment.section_id:
            section_scope |= Q(**{
                f'{section_path}_id': enrollment.section_id,
            })
        scope |= exact & section_scope

    if not enrollments and memb.classification_id:
        course_ids = list(
            memb.courses.filter(org=org).values_list('pk', flat=True)
        )
        scope = (
            (
                Q(**{f'{course_path}_id__in': course_ids})
                | Q(**{f'{course_path}__isnull': True})
            )
            & Q(**{
                f'{classification_path}_id': memb.classification_id,
            })
        )
        section_scope = Q(**{f'{section_path}__isnull': True})
        if memb.section_id:
            section_scope |= Q(**{
                f'{section_path}_id': memb.section_id,
            })
        scope &= section_scope
    return scope, enrollments


def _routine_payload(period):
    teacher_profile = getattr(period.teacher, 'staff', None)
    teacher_member = getattr(teacher_profile, 'member', None)
    return {
        'id': period.id,
        'day_of_week': period.day_of_week,
        'day_label': period.get_day_of_week_display(),
        'period_number': period.period_number,
        'start_time': period.start_time.isoformat(timespec='minutes'),
        'end_time': period.end_time.isoformat(timespec='minutes'),
        'room': period.room or '',
        'shift': period.shift,
        'subject': {
            'id': period.subject_id,
            'name': period.subject.name,
        },
        'teacher': {
            'id': period.teacher_id,
            'name': (
                teacher_member.name
                if teacher_member else period.teacher.get_full_name()
                or period.teacher.username
            ),
        },
        'course': (
            {
                'id': period.subject.course_id,
                'name': period.subject.course.name,
            }
            if period.subject.course_id else None
        ),
        'classification': {
            'id': period.classification_id,
            'name': period.classification.name,
        },
        'section': (
            {'id': period.section_id, 'name': period.section.name}
            if period.section_id else None
        ),
        'academic_year': (
            {'id': period.academic_year_id, 'name': period.academic_year.name}
            if period.academic_year_id else None
        ),
        'state': getattr(period, 'reminder_state', ''),
        'state_label': getattr(period, 'reminder_label', ''),
    }


def _student_routine_queryset(org, memb):
    from handle.models import RoutinePeriod

    scope, enrollments = _student_mobile_scope(
        org,
        memb,
        course_path='subject__course',
        classification_path='classification',
        section_path='section',
    )
    queryset = (
        RoutinePeriod.objects.filter(scope, org=org, is_active=True)
        .filter(Q(branch__isnull=True) | Q(branch_id=memb.branch_id))
        .select_related(
            'academic_year',
            'subject__course',
            'teacher',
            'classification',
            'section',
        )
        .order_by('day_of_week', 'period_number', 'start_time')
    )
    return queryset, enrollments


def _student_enrollment_payload(enrollment):
    return {
        'id': enrollment.id,
        'course': {
            'id': enrollment.course_id,
            'name': enrollment.course.name,
        },
        'classification': {
            'id': enrollment.classification_id,
            'name': enrollment.classification.name,
        },
        'section': (
            {'id': enrollment.section_id, 'name': enrollment.section.name}
            if enrollment.section_id else None
        ),
        'academic_year': (
            {
                'id': enrollment.academic_year_id,
                'name': enrollment.academic_year.name,
            }
            if enrollment.academic_year_id else None
        ),
        'status': enrollment.status,
        'start_date': enrollment.start_date.isoformat(),
        'end_date': (
            enrollment.end_date.isoformat() if enrollment.end_date else None
        ),
    }


@api_view(['GET'])
@permission_classes([IsAuthenticated])
@authentication_classes([JWTAuthentication])
def api_student_dashboard(request):
    from django.db.models import Count, Sum
    from django.utils import timezone
    from handle.academics import student_routine_reminders
    from handle.models import (
        Assignment,
        AssignmentSubmission,
        Bill,
        BookIssue,
        ExamTerm,
        Event,
        HomeworkStatus,
        Notice,
        NoticeRead,
        ResultRecord,
        SubjectAttendanceRecord,
        StudentBusAssignment,
        TeachingLog,
    )
    from school.features import has_feature

    org, memb = _mobile_student_context(request)
    if org is None:
        return Response(
            {'error': 'This endpoint is available only to student accounts.'},
            status=403,
        )
    today = timezone.localdate()
    periods, enrollments = _student_routine_queryset(org, memb)
    routine = student_routine_reminders(periods, on_date=today)

    billing = {
        'enabled': has_feature(org, 'billing'),
        'total_due': '0.00',
        'unpaid_count': 0,
        'recent': [],
    }
    if billing['enabled']:
        bills = Bill.objects.filter(org=org, member=memb).exclude(
            status='Cancelled',
        )
        due_bills = bills.exclude(status='Paid')
        total_due = sum((bill.balance_due for bill in due_bills), 0)
        billing.update({
            'total_due': str(total_due),
            'unpaid_count': due_bills.count(),
            'recent': [
                _bill_payload(item) for item in bills.prefetch_related(
                    'items',
                ).order_by('-issue_date')[:3]
            ],
        })

    academic_enabled = has_feature(org, 'academic_management')
    homework_pending = 0
    assignments_pending = 0
    teaching_logs = []
    if academic_enabled:
        homework_pending = HomeworkStatus.objects.filter(
            student=memb,
            homework__org=org,
            homework__status='active',
            status='pending',
        ).filter(
            Q(homework__branch__isnull=True)
            | Q(homework__branch_id=memb.branch_id)
        ).count()
        assignment_scope, _ = _student_mobile_scope(
            org,
            memb,
            course_path='course',
            classification_path='classification',
            section_path='section',
        )
        assignments = Assignment.objects.filter(
            assignment_scope,
            org=org,
            visibility='published',
            due_date__gte=today,
        ).filter(Q(branch__isnull=True) | Q(branch_id=memb.branch_id))
        submitted = AssignmentSubmission.objects.filter(
            student=memb,
            assignment__in=assignments,
        ).values_list('assignment_id', flat=True)
        assignments_pending = assignments.exclude(pk__in=submitted).count()
        log_scope, _ = _student_mobile_scope(
            org,
            memb,
            course_path='subject__course',
            classification_path='classification',
            section_path='section',
        )
        teaching_logs = [
            _teaching_log_payload(item, memb)
            for item in TeachingLog.objects.filter(
                log_scope,
                org=org,
                date=today,
                status='approved',
            )
            .filter(Q(branch__isnull=True) | Q(branch_id=memb.branch_id))
            .select_related('subject', 'teacher', 'homework_given')
            .prefetch_related('attachments', 'attendance_records')
            .order_by('period', 'start_time')[:8]
        ]

    results = {
        'enabled': has_feature(org, 'results'),
        'published_exam_count': 0,
        'recent': [],
    }
    if results['enabled']:
        published_exams = ExamTerm.objects.filter(
            org=org,
            is_published=True,
        )
        recent_records = (
            ResultRecord.objects.filter(
                student=memb,
                exam__in=published_exams,
            )
            .select_related('exam', 'subject')
            .order_by('-exam__start_date', 'subject__name')[:5]
        )
        results.update({
            'published_exam_count': published_exams.filter(
                exam_records__student=memb,
            ).distinct().count(),
            'recent': [_result_record_payload(item) for item in recent_records],
        })

    month_start = today.replace(day=1)
    attendance_rows = SubjectAttendanceRecord.objects.filter(
        org=org,
        member=memb,
        teaching_log__date__range=(month_start, today),
    )
    attendance_counts = {
        row['status']: row['total']
        for row in attendance_rows.values('status').annotate(
            total=Count('pk'),
        )
    }
    attendance_total = sum(attendance_counts.values())
    present_like = (
        attendance_counts.get('present', 0)
        + attendance_counts.get('late', 0)
    )

    notice_items = []
    unread_notice_count = 0
    if has_feature(org, 'notices'):
        now = timezone.now()
        candidate_notices = (
            Notice.objects.filter(org=org, publish_at__lte=now)
            .filter(Q(expires_at__isnull=True) | Q(expires_at__gt=now))
            .order_by('-publish_at', '-id')[:30]
        )
        targeted = [
            notice for notice in candidate_notices
            if notice.is_for_member(memb)
        ]
        read_ids = set(NoticeRead.objects.filter(
            member=memb,
            notice_id__in=[notice.id for notice in targeted],
        ).values_list('notice_id', flat=True))
        unread_notice_count = sum(
            1 for notice in targeted if notice.id not in read_ids
        )
        notice_items = [
            _notice_payload(notice, read_ids) for notice in targeted[:3]
        ]

    active_issues = 0
    if has_feature(org, 'library'):
        active_issues = BookIssue.objects.filter(
            org=org,
            member=memb,
            status__in=('issued', 'overdue'),
        ).count()

    event_items = []
    if has_feature(org, 'events'):
        event_items = [
            _event_payload(item, org)
            for item in Event.objects.filter(
                org=org,
                end_date__gte=today,
            ).filter(
                Q(branch__isnull=True) | Q(branch_id=memb.branch_id)
            ).select_related('branch').order_by('start_date', 'id')[:4]
        ]
    bus_assignment = StudentBusAssignment.objects.filter(
        org=org,
        student=memb,
        status='active',
        bus__org=org,
        bus__is_active=True,
    ).select_related('bus__branch', 'bus__driver').first()

    return Response({
        'date': today.isoformat(),
        'nepali_date': bool(getattr(org, 'nepali_date', False)),
        **_mobile_date_fields(org, today),
        'student': {
            'id': memb.id,
            'name': memb.name,
            'branch': (
                {'id': memb.branch_id, 'name': memb.branch.name}
                if memb.branch_id else None
            ),
            'classification': (
                {
                    'id': memb.classification_id,
                    'name': memb.classification.name,
                }
                if memb.classification_id else None
            ),
            'section': (
                {'id': memb.section_id, 'name': memb.section.name}
                if memb.section_id else None
            ),
            'enrollments': [
                _student_enrollment_payload(item) for item in enrollments
            ],
        },
        'routine': {
            'today': [_routine_payload(item) for item in routine['today_periods']],
            'active': (
                _routine_payload(routine['active'])
                if routine['active'] else None
            ),
            'next': (
                _routine_payload(routine['next_period'])
                if routine['next_period'] else None
            ),
        },
        'attendance': {
            'month_total': attendance_total,
            'present_like': present_like,
            'percentage': (
                round(present_like / attendance_total * 100, 1)
                if attendance_total else 0
            ),
            'counts': attendance_counts,
        },
        'billing': billing,
        'academic_work': {
            'enabled': academic_enabled,
            'homework_pending': homework_pending,
            'assignments_pending': assignments_pending,
            'today_logs': teaching_logs,
        },
        'results': results,
        'notices': {
            'enabled': has_feature(org, 'notices'),
            'unread_count': unread_notice_count,
            'recent': notice_items,
        },
        'events': {
            'enabled': has_feature(org, 'events'),
            'upcoming': event_items,
        },
        'transport': {
            'assigned': bus_assignment is not None,
            'bus': (
                _bus_payload(bus_assignment.bus)
                if bus_assignment else None
            ),
            'stop_name': (
                bus_assignment.stop_name if bus_assignment else ''
            ),
        },
        'library': {
            'enabled': has_feature(org, 'library'),
            'active_issues': active_issues,
        },
    })


def _bill_payload(bill):
    return {
        'id': bill.id,
        'invoice_number': bill.invoice_number,
        'issue_date': bill.issue_date.isoformat(),
        'due_date': bill.due_date.isoformat(),
        'status': bill.status,
        'billing_type': bill.billing_type or '',
        'total_amount': str(bill.total_amount),
        'amount_paid': str(bill.amount_paid),
        'balance_due': str(bill.balance_due),
        'discount_amount': str(bill.discount_amount),
        'scholarship_amount': str(bill.scholarship_amount),
        'fine_amount': str(bill.fine_amount),
        'remarks': bill.remarks or '',
        'items': [{
            'id': item.id,
            'description': item.description,
            'fee_type': item.fee_type,
            'amount': str(item.amount),
            'discount': str(item.discount),
            'final_amount': str(item.final_amount),
        } for item in bill.items.all()],
    }


@api_view(['GET'])
@permission_classes([IsAuthenticated])
@authentication_classes([JWTAuthentication])
def api_student_bills(request):
    from handle.models import Bill
    from school.features import has_feature

    org, memb = _mobile_student_context(request)
    if org is None:
        return Response({'error': 'Student access is required.'}, status=403)
    if not has_feature(org, 'billing'):
        return Response({'error': 'Billing is not enabled.'}, status=403)
    queryset = Bill.objects.filter(
        org=org,
        member=memb,
    ).prefetch_related('items').order_by('-issue_date', '-id')
    status_filter = request.GET.get('status', '').strip()
    if status_filter:
        queryset = queryset.filter(status=status_filter)
    return Response(_page_payload(request, queryset, _bill_payload))


@api_view(['GET'])
@permission_classes([IsAuthenticated])
@authentication_classes([JWTAuthentication])
def api_student_routine(request):
    from handle.academics import student_routine_reminders
    from django.utils import timezone
    from school.features import has_feature

    org, memb = _mobile_student_context(request)
    if org is None:
        return Response({'error': 'Student access is required.'}, status=403)
    if not has_feature(org, 'academic_management'):
        return Response(
            {'error': 'Academic management is not enabled.'},
            status=403,
        )
    periods, enrollments = _student_routine_queryset(org, memb)
    routine = student_routine_reminders(
        periods,
        on_date=timezone.localdate(),
    )
    return Response({
        'current_day': routine['current_day'],
        'periods': [_routine_payload(item) for item in routine['periods']],
        'active_id': routine['active'].id if routine['active'] else None,
        'next_id': (
            routine['next_period'].id if routine['next_period'] else None
        ),
        'enrollments': [
            _student_enrollment_payload(item) for item in enrollments
        ],
    })


def _homework_payload(status_obj):
    homework = status_obj.homework
    return {
        'id': status_obj.id,
        'homework_id': homework.id,
        'subject': {
            'id': homework.subject_id,
            'name': homework.subject.name,
        },
        'teacher': (
            homework.assigned_by.get_full_name()
            or homework.assigned_by.username
            if homework.assigned_by else ''
        ),
        'description': homework.description,
        'due_date': homework.due_date.isoformat(),
        'priority': homework.priority,
        'estimated_time_minutes': homework.estimated_time_minutes,
        'status': status_obj.status,
        'verified_by_teacher': status_obj.verified_by_teacher,
        'completed_at': (
            status_obj.completed_at.isoformat()
            if status_obj.completed_at else None
        ),
        'attachments': [
            item.file.url for item in homework.attachments.all()
        ],
    }


def _assignment_payload(assignment, submission=None):
    return {
        'id': assignment.id,
        'title': assignment.title,
        'description': assignment.description or '',
        'instructions': assignment.instructions or '',
        'subject': {
            'id': assignment.subject_id,
            'name': assignment.subject.name,
        },
        'teacher': (
            assignment.assigned_by.get_full_name()
            or assignment.assigned_by.username
            if assignment.assigned_by else ''
        ),
        'start_date': assignment.start_date.isoformat(),
        'due_date': assignment.due_date.isoformat(),
        'total_marks': str(assignment.total_marks),
        'passing_marks': str(assignment.passing_marks),
        'status': assignment.status,
        'attachments': [
            item.file.url for item in assignment.attachments.all()
        ],
        'submission': ({
            'id': submission.id,
            'status': submission.status,
            'submitted_at': (
                submission.submitted_at.isoformat()
                if submission.submitted_at else None
            ),
            'is_late': submission.is_late,
            'student_comments': submission.student_comments or '',
            'obtained_marks': (
                str(submission.obtained_marks)
                if submission.obtained_marks is not None else None
            ),
            'teacher_remarks': submission.teacher_remarks or '',
        } if submission else None),
    }


def _teaching_log_payload(log, memb):
    attendance = next(
        (
            item for item in log.attendance_records.all()
            if item.member_id == memb.id
        ),
        None,
    )
    return {
        'id': log.id,
        'date': log.date.isoformat(),
        'period': log.period,
        'routine_period_id': log.routine_period_id,
        'start_time': (
            log.start_time.isoformat(timespec='minutes')
            if log.start_time else None
        ),
        'end_time': (
            log.end_time.isoformat(timespec='minutes')
            if log.end_time else None
        ),
        'room': log.room or '',
        'subject': {'id': log.subject_id, 'name': log.subject.name},
        'teacher': log.teacher.get_full_name() or log.teacher.username,
        'topic_covered': log.topic_covered,
        'chapter': log.chapter or '',
        'learning_objectives': log.learning_objectives or '',
        'homework': (
            log.homework_given.description
            if log.homework_given_id else ''
        ),
        'remarks': log.remarks or '',
        'attendance_status': attendance.status if attendance else None,
        'attachments': [item.file.url for item in log.attachments.all()],
    }


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
@authentication_classes([JWTAuthentication])
def api_student_academic_work(request):
    from django.db import transaction
    from django.utils import timezone
    from handle.models import (
        Assignment,
        AssignmentSubmission,
        AssignmentSubmissionHistory,
        HomeworkStatus,
        TeachingLog,
    )
    from school.features import has_feature

    org, memb = _mobile_student_context(request)
    if org is None:
        return Response({'error': 'Student access is required.'}, status=403)
    if not has_feature(org, 'academic_management'):
        return Response(
            {'error': 'Academic management is not enabled.'},
            status=403,
        )
    assignment_scope, enrollments = _student_mobile_scope(
        org,
        memb,
        course_path='course',
        classification_path='classification',
        section_path='section',
    )
    assignments = (
        Assignment.objects.filter(
            assignment_scope,
            org=org,
            visibility='published',
        )
        .filter(Q(branch__isnull=True) | Q(branch_id=memb.branch_id))
        .select_related('subject', 'assigned_by')
        .prefetch_related('attachments')
        .order_by('-due_date', '-id')
    )

    if request.method == 'POST':
        action = (request.data.get('action') or '').strip()
        if action == 'homework_toggle':
            status_obj = (
                HomeworkStatus.objects.filter(
                    pk=request.data.get('status_id'),
                    student=memb,
                    homework__org=org,
                )
                .select_related('homework')
                .first()
            )
            if status_obj is None:
                return Response({'error': 'Homework not found.'}, status=404)
            if status_obj.verified_by_teacher:
                return Response(
                    {'error': 'Verified homework cannot be changed.'},
                    status=409,
                )
            status_obj.status = (
                'completed'
                if status_obj.status == 'pending' else 'pending'
            )
            status_obj.completed_at = (
                timezone.now() if status_obj.status == 'completed' else None
            )
            status_obj.save(update_fields=['status', 'completed_at'])
            return Response({'status': 'success'})
        if action == 'assignment_submit':
            assignment = assignments.filter(
                pk=request.data.get('assignment_id'),
                status='open',
            ).first()
            if assignment is None:
                return Response({'error': 'Assignment not found.'}, status=404)
            comments = (request.data.get('student_comments') or '').strip()
            with transaction.atomic():
                submission, created = (
                    AssignmentSubmission.objects.select_for_update()
                    .get_or_create(
                        assignment=assignment,
                        student=memb,
                    )
                )
                if not created and submission.status == 'graded':
                    return Response(
                        {
                            'error':
                            'A graded assignment cannot be resubmitted.',
                        },
                        status=409,
                    )
                submission.student_comments = comments
                submission.submitted_at = timezone.now()
                submission.status = 'submitted'
                submission.save()
                AssignmentSubmissionHistory.objects.create(
                    submission=submission,
                    action='submitted' if created else 'resubmitted',
                    status=submission.status,
                    performed_by=request.user,
                )
            return Response(
                _assignment_payload(assignment, submission),
                status=201 if created else 200,
            )
        return Response({'error': 'Unsupported academic action.'}, status=400)

    homework = (
        HomeworkStatus.objects.filter(
            student=memb,
            homework__org=org,
        )
        .filter(
            Q(homework__branch__isnull=True)
            | Q(homework__branch_id=memb.branch_id)
        )
        .select_related('homework__subject', 'homework__assigned_by')
        .prefetch_related('homework__attachments')
        .order_by('-homework__due_date', '-id')
    )
    submissions = {
        item.assignment_id: item
        for item in AssignmentSubmission.objects.filter(
            student=memb,
            assignment__in=assignments,
        )
    }
    log_scope, _ = _student_mobile_scope(
        org,
        memb,
        course_path='subject__course',
        classification_path='classification',
        section_path='section',
    )
    teaching_logs = (
        TeachingLog.objects.filter(
            log_scope,
            org=org,
            status='approved',
        )
        .filter(Q(branch__isnull=True) | Q(branch_id=memb.branch_id))
        .select_related('subject', 'teacher', 'homework_given')
        .prefetch_related('attachments', 'attendance_records')
        .order_by('-date', '-period', '-id')[:50]
    )
    return Response({
        'homework': [_homework_payload(item) for item in homework[:50]],
        'assignments': [
            _assignment_payload(item, submissions.get(item.id))
            for item in assignments[:50]
        ],
        'teaching_logs': [
            _teaching_log_payload(item, memb) for item in teaching_logs
        ],
        'enrollments': [
            _student_enrollment_payload(item) for item in enrollments
        ],
    })


def _result_record_payload(record):
    return {
        'id': record.id,
        'exam': {'id': record.exam_id, 'name': record.exam.name},
        'subject': {'id': record.subject_id, 'name': record.subject.name},
        'full_marks': str(record.subject.full_marks),
        'pass_marks': str(record.subject.pass_marks),
        'obtained_marks': str(record.obtained_marks),
        'percentage': record.percentage,
        'grade': record.grade or '',
        'is_absent': record.is_absent,
        'is_passed': record.is_passed,
        'remarks': record.remarks or '',
    }


@api_view(['GET'])
@permission_classes([IsAuthenticated])
@authentication_classes([JWTAuthentication])
def api_student_results(request):
    from handle.models import ExamTerm, ResultRecord
    from school.features import has_feature

    org, memb = _mobile_student_context(request)
    if org is None:
        return Response({'error': 'Student access is required.'}, status=403)
    if not has_feature(org, 'results'):
        return Response({'error': 'Results are not enabled.'}, status=403)
    exams = (
        ExamTerm.objects.filter(
            org=org,
            is_published=True,
            exam_records__student=memb,
        )
        .distinct()
        .order_by('-start_date', '-id')
    )
    selected_id = request.GET.get('exam')
    selected = (
        exams.filter(pk=selected_id).first()
        if selected_id else exams.first()
    )
    records = []
    if selected:
        records = list(
            ResultRecord.objects.filter(
                student=memb,
                exam=selected,
            ).select_related('exam', 'subject').order_by('subject__name')
        )
    total_obtained = sum(
        float(item.obtained_marks) for item in records if not item.is_absent
    )
    total_full = sum(
        float(item.subject.full_marks) for item in records if not item.is_absent
    )
    return Response({
        'exams': [{
            'id': item.id,
            'name': item.name,
            'academic_year': item.academic_year or '',
            'start_date': (
                item.start_date.isoformat() if item.start_date else None
            ),
            'end_date': (
                item.end_date.isoformat() if item.end_date else None
            ),
        } for item in exams],
        'selected_exam_id': selected.id if selected else None,
        'records': [_result_record_payload(item) for item in records],
        'summary': {
            'total_obtained': total_obtained,
            'total_full': total_full,
            'percentage': (
                round(total_obtained / total_full * 100, 1)
                if total_full else 0
            ),
            'pass_count': sum(item.is_passed for item in records),
            'fail_count': sum(
                not item.is_passed and not item.is_absent
                for item in records
            ),
            'absent_count': sum(item.is_absent for item in records),
            'overall_pass': bool(records) and all(
                item.is_passed for item in records
            ),
        },
    })


def _teacher_mobile_context(request, feature='academic_management'):
    from handle.academics import active_subject_assignments_for_teacher
    from school.features import has_feature

    org, memb = _mobile_staff_context(request)
    if (
        org is None
        or memb is None
        or memb.member_type in ('student', 'trainee')
    ):
        return None, None, None, Response(
            {'error': 'Teaching staff access is required.'},
            status=403,
        )
    if feature and not has_feature(org, feature):
        return None, None, None, Response(
            {'error': f'{feature.replace("_", " ").title()} is not enabled.'},
            status=403,
        )
    scopes = active_subject_assignments_for_teacher(
        org,
        request.user,
    ).filter(
        classification__isnull=False,
    )
    # The assignment itself is explicit teacher authority. When the teacher
    # profile has a branch, keep the normal global/current-branch boundary;
    # when it has no branch, do not hide a branch-specific assignment that an
    # administrator deliberately granted to this exact teacher.
    if memb.branch_id:
        scopes = scopes.filter(
            Q(branch__isnull=True) | Q(branch_id=memb.branch_id)
        )
    if not scopes.exists():
        return None, None, None, Response(
            {'error': 'No active subject assignment is available.'},
            status=403,
        )
    return org, memb, scopes, None


def _teacher_scope_payload(scope):
    return {
        'id': scope.id,
        'subject': {'id': scope.subject_id, 'name': scope.subject.name},
        'course': (
            {'id': scope.course_id, 'name': scope.course.name}
            if scope.course_id else None
        ),
        'classification': {
            'id': scope.classification_id,
            'name': scope.classification.name,
        },
        'section': (
            {'id': scope.section_id, 'name': scope.section.name}
            if scope.section_id else None
        ),
        'academic_year': (
            {'id': scope.academic_year_id, 'name': scope.academic_year.name}
            if scope.academic_year_id else None
        ),
        'branch': (
            {'id': scope.branch_id, 'name': scope.branch.name}
            if scope.branch_id else None
        ),
        'is_primary': scope.is_primary,
        'start_date': scope.start_date.isoformat(),
        'end_date': scope.end_date.isoformat() if scope.end_date else None,
    }


def _teacher_log_payload(log):
    return {
        'id': log.id,
        'routine_period_id': log.routine_period_id,
        'date': log.date.isoformat(),
        'period': log.period,
        'status': log.status,
        'subject': {'id': log.subject_id, 'name': log.subject.name},
        'course': (
            {'id': log.course_id, 'name': log.course.name}
            if log.course_id else None
        ),
        'classification': {
            'id': log.classification_id,
            'name': log.classification.name,
        },
        'section': (
            {'id': log.section_id, 'name': log.section.name}
            if log.section_id else None
        ),
        'topic_covered': log.topic_covered,
        'chapter': log.chapter or '',
        'learning_objectives': log.learning_objectives or '',
        'remarks': log.remarks or '',
        'rejection_reason': log.rejection_reason or '',
        'attendance': {
            'present': log.attendance_present or 0,
            'absent': log.attendance_absent or 0,
            'late': log.attendance_late or 0,
            'excused': log.attendance_excused or 0,
            'leave': log.attendance_leave or 0,
        },
    }


def _teacher_period_payload(period):
    payload = _routine_payload(period)
    log = getattr(period, 'attendance_log', None)
    payload['session'] = _teacher_log_payload(log) if log else None
    payload['action_required'] = bool(
        getattr(period, 'attendance_action_required', False)
    )
    return payload


@api_view(['GET'])
@permission_classes([IsAuthenticated])
@authentication_classes([JWTAuthentication])
def api_teacher_dashboard(request):
    from handle.academics import (
        roster_for_subject,
        teacher_routine_reminders,
    )
    from handle.models import (
        Assignment,
        AssignmentSubmission,
        ExamTerm,
        Event,
        Homework,
        TeachingLog,
    )
    from django.utils import timezone

    org, memb, scopes, error = _teacher_mobile_context(request)
    if error:
        return error
    scopes = scopes.select_related(
        'academic_year',
        'branch',
        'course',
        'classification',
        'section',
        'subject',
    ).order_by(
        'course__name',
        'classification__name',
        'section__name',
        'subject__name',
    )
    scope_list = list(scopes)
    scope_ids = [item.id for item in scope_list]
    subject_ids = {item.subject_id for item in scope_list}
    today = timezone.localdate()
    routine = teacher_routine_reminders(
        org,
        request.user,
        subject_ids,
        assignment_ids=set(scope_ids),
        on_date=today,
    )
    roster_members = {}
    for scope in scope_list:
        for student in roster_for_subject(
            org,
            scope.subject,
            scope.classification,
            scope.section,
            attendance_date=today,
            academic_year=scope.academic_year,
        ).select_related('classification', 'section'):
            roster_members.setdefault(student.pk, student)
    logs = TeachingLog.objects.filter(
        org=org,
        teacher=request.user,
        teacher_assignment_id__in=scope_ids,
    )
    assignments = Assignment.objects.filter(
        org=org,
        teacher_assignment_id__in=scope_ids,
    )
    homework = Homework.objects.filter(
        org=org,
        teacher_assignment_id__in=scope_ids,
    )
    exam_count = ExamTerm.objects.filter(
        org=org,
        classification_id__in={
            item.classification_id for item in scope_list
        },
        status__in=('draft', 'marks_entry'),
        is_published=False,
    ).filter(
        Q(section__isnull=True)
        | Q(section_id__in={
            item.section_id for item in scope_list if item.section_id
        })
    ).distinct().count()
    from school.features import has_feature, has_perm
    event_items = []
    if has_feature(org, 'events') and has_perm(
        request.user, 'can_view_events'
    ):
        event_items = [
            _event_payload(item, org)
            for item in Event.objects.filter(
                org=org,
                end_date__gte=today,
            ).filter(
                Q(branch__isnull=True) | Q(branch_id=memb.branch_id)
            ).select_related('branch').order_by('start_date', 'id')[:4]
        ]
    return Response({
        'date': today.isoformat(),
        'nepali_date': bool(getattr(org, 'nepali_date', False)),
        **_mobile_date_fields(org, today),
        'teacher': {
            'id': memb.id,
            'name': memb.name,
            'branch': (
                {'id': memb.branch_id, 'name': memb.branch.name}
                if memb.branch_id else None
            ),
        },
        'summary': {
            'assigned_subjects': len(subject_ids),
            'assigned_courses': len({
                item.course_id for item in scope_list if item.course_id
            }),
            'assigned_students': len(roster_members),
            'draft_sessions': logs.filter(status='draft').count(),
            'submitted_sessions': logs.filter(status='submitted').count(),
            'rejected_sessions': logs.filter(status='rejected').count(),
            'open_assignments': assignments.filter(status='open').count(),
            'ungraded_submissions': (
                AssignmentSubmission.objects.filter(
                    assignment__in=assignments,
                ).exclude(status='graded').count()
            ),
            'active_homework': homework.filter(status='active').count(),
            'editable_exams': exam_count,
        },
        'routine': {
            'today': [
                _teacher_period_payload(item)
                for item in routine['today_periods']
            ],
            'attention': (
                _teacher_period_payload(routine['attention'])
                if routine['attention'] else None
            ),
            'next': (
                _teacher_period_payload(routine['next_period'])
                if routine['next_period'] else None
            ),
        },
        'assignments': [_teacher_scope_payload(item) for item in scope_list],
        'students': [{
            'id': student.id,
            'name': student.name,
            'roll_number': student.roll_number or '',
            'classification': (
                student.classification.name
                if student.classification_id else ''
            ),
            'section': student.section.name if student.section_id else '',
        } for student in sorted(
            roster_members.values(),
            key=lambda item: (item.name.lower(), item.pk),
        )],
        'events': {
            'enabled': bool(event_items) or has_feature(org, 'events'),
            'upcoming': event_items,
        },
        'recent_sessions': [
            _teacher_log_payload(item)
            for item in logs.select_related(
                'course',
                'subject',
                'classification',
                'section',
            ).order_by('-date', '-id')[:6]
        ],
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
@authentication_classes([JWTAuthentication])
def api_teacher_sessions(request):
    from handle.models import TeachingLog

    org, memb, scopes, error = _teacher_mobile_context(request)
    if error:
        return error
    scope_ids = list(scopes.values_list('pk', flat=True))
    logs = TeachingLog.objects.filter(
        org=org,
        teacher=request.user,
        teacher_assignment_id__in=scope_ids,
    ).select_related(
        'course', 'subject', 'classification', 'section',
    ).order_by('-date', '-id')
    selected_status = request.GET.get('status', '').strip()
    if selected_status:
        if selected_status not in dict(TeachingLog.STATUS_CHOICES):
            return Response({'error': 'Invalid session status.'}, status=400)
        logs = logs.filter(status=selected_status)
    return Response({
        'status': selected_status,
        'results': [_teacher_log_payload(item) for item in logs[:100]],
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
@authentication_classes([JWTAuthentication])
def api_teacher_routine(request):
    from handle.academics import teacher_routine_reminders
    from django.utils import timezone

    org, memb, scopes, error = _teacher_mobile_context(request)
    if error:
        return error
    scope_list = list(scopes.select_related('subject'))
    routine = teacher_routine_reminders(
        org,
        request.user,
        {item.subject_id for item in scope_list},
        assignment_ids={item.id for item in scope_list},
        on_date=timezone.localdate(),
    )
    return Response({
        'current_day': (timezone.localdate().weekday() + 1) % 7,
        'periods': [_teacher_period_payload(item) for item in routine['periods']],
        'attention_id': (
            routine['attention'].id if routine['attention'] else None
        ),
        'next_id': (
            routine['next_period'].id if routine['next_period'] else None
        ),
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
@authentication_classes([JWTAuthentication])
def api_teacher_attendance_context(request, period_id):
    from handle.academics import roster_for_subject
    from handle.models import RoutinePeriod, TeachingLog
    from django.utils import timezone

    org, memb, scopes, error = _teacher_mobile_context(request)
    if error:
        return error
    scope_ids = list(scopes.values_list('id', flat=True))
    subject_ids = list(scopes.values_list('subject_id', flat=True))
    period = (
        RoutinePeriod.objects.filter(
            pk=period_id,
            org=org,
            teacher=request.user,
            is_active=True,
            subject_id__in=subject_ids,
        )
        .filter(
            Q(teacher_assignment_id__in=scope_ids)
            | Q(teacher_assignment__isnull=True)
        )
        .select_related(
            'academic_year',
            'teacher_assignment',
            'subject__course',
            'classification',
            'section',
            'teacher',
        )
        .first()
    )
    if period is None:
        return Response({'error': 'Routine period not found.'}, status=404)
    try:
        attendance_date = datetime.date.fromisoformat(
            request.GET.get('date', ''),
        )
    except (TypeError, ValueError):
        attendance_date = timezone.localdate()
    roster = roster_for_subject(
        org,
        period.subject,
        period.classification,
        period.section,
        attendance_date=attendance_date,
        academic_year=period.academic_year,
    )
    log = (
        TeachingLog.objects.filter(
            org=org,
            teacher=request.user,
            subject=period.subject,
            classification=period.classification,
            section=period.section,
            date=attendance_date,
            period=period.period_number,
        )
        .prefetch_related('attendance_records')
        .select_related('course', 'subject', 'classification', 'section')
        .first()
    )
    existing = {
        item.member_id: item for item in (
            log.attendance_records.all() if log else []
        )
    }
    return Response({
        'period': _teacher_period_payload(period),
        'date': attendance_date.isoformat(),
        'session': _teacher_log_payload(log) if log else None,
        'locked': bool(log and log.status == 'approved'),
        'students': [{
            'id': student.id,
            'name': student.name,
            'roll_number': student.roll_number or '',
            'status': (
                existing[student.id].status
                if student.id in existing else 'present'
            ),
            'remarks': (
                existing[student.id].remarks or ''
                if student.id in existing else ''
            ),
        } for student in roster],
    })


def _teacher_assignment_payload(assignment):
    return {
        'id': assignment.id,
        'title': assignment.title,
        'subject': {
            'id': assignment.subject_id,
            'name': assignment.subject.name,
        },
        'classification': assignment.classification.name,
        'section': assignment.section.name if assignment.section_id else '',
        'description': assignment.description or '',
        'instructions': assignment.instructions or '',
        'start_date': assignment.start_date.isoformat(),
        'due_date': assignment.due_date.isoformat(),
        'total_marks': str(assignment.total_marks),
        'passing_marks': str(assignment.passing_marks),
        'visibility': assignment.visibility,
        'status': assignment.status,
        'submission_count': assignment.submissions.count(),
        'ungraded_count': assignment.submissions.exclude(
            status='graded',
        ).count(),
        'submissions': [{
            'id': item.id,
            'student': {'id': item.student_id, 'name': item.student.name},
            'submitted_at': (
                item.submitted_at.isoformat() if item.submitted_at else None
            ),
            'status': item.status,
            'is_late': item.is_late,
            'student_comments': item.student_comments or '',
            'obtained_marks': (
                str(item.obtained_marks)
                if item.obtained_marks is not None else None
            ),
            'teacher_remarks': item.teacher_remarks or '',
        } for item in assignment.submissions.all()],
    }


def _teacher_homework_payload(homework):
    return {
        'id': homework.id,
        'subject': {'id': homework.subject_id, 'name': homework.subject.name},
        'classification': homework.classification.name,
        'section': homework.section.name if homework.section_id else '',
        'description': homework.description,
        'due_date': homework.due_date.isoformat(),
        'priority': homework.priority,
        'estimated_time_minutes': homework.estimated_time_minutes,
        'frequency': homework.frequency,
        'status': homework.status,
        'student_count': homework.statuses.count(),
        'completed_count': homework.statuses.filter(
            status='completed',
        ).count(),
        'verified_count': homework.statuses.filter(
            verified_by_teacher=True,
        ).count(),
        'students': [{
            'id': item.id,
            'student': {'id': item.student_id, 'name': item.student.name},
            'status': item.status,
            'verified': item.verified_by_teacher,
            'completed_at': (
                item.completed_at.isoformat() if item.completed_at else None
            ),
        } for item in homework.statuses.all()],
    }


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
@authentication_classes([JWTAuthentication])
def api_teacher_academic_work(request):
    from decimal import Decimal, InvalidOperation
    from django.db import transaction
    from django.utils import timezone
    from handle.academics import roster_for_subject
    from handle.models import (
        Assignment,
        AssignmentSubmission,
        AssignmentSubmissionHistory,
        Homework,
        HomeworkStatus,
    )

    org, memb, scopes, error = _teacher_mobile_context(request)
    if error:
        return error
    scopes = scopes.select_related(
        'academic_year',
        'branch',
        'course',
        'classification',
        'section',
        'subject',
    )
    scope_ids = list(scopes.values_list('id', flat=True))
    assignments = (
        Assignment.objects.filter(
            org=org,
            teacher_assignment_id__in=scope_ids,
        )
        .select_related('subject', 'classification', 'section')
        .prefetch_related('submissions__student')
        .order_by('-due_date', '-id')
    )
    homework = (
        Homework.objects.filter(
            org=org,
            teacher_assignment_id__in=scope_ids,
        )
        .select_related('subject', 'classification', 'section')
        .prefetch_related('statuses__student')
        .order_by('-due_date', '-id')
    )
    if request.method == 'POST':
        action = (request.data.get('action') or '').strip()
        if action in {'create_assignment', 'create_homework'}:
            scope = scopes.filter(
                pk=request.data.get('scope_id'),
            ).first()
            if scope is None:
                return Response(
                    {'error': 'Teaching assignment not found.'},
                    status=404,
                )
            try:
                due_date = datetime.date.fromisoformat(
                    request.data.get('due_date', ''),
                )
            except (TypeError, ValueError):
                return Response(
                    {'error': 'A valid due date is required.'},
                    status=400,
                )
            if due_date < timezone.localdate():
                return Response(
                    {'error': 'Due date cannot be in the past.'},
                    status=400,
                )
            if action == 'create_assignment':
                title = (request.data.get('title') or '').strip()
                if not title:
                    return Response(
                        {'error': 'Assignment title is required.'},
                        status=400,
                    )
                try:
                    total_marks = Decimal(
                        str(request.data.get('total_marks', 100)),
                    )
                    passing_marks = Decimal(
                        str(request.data.get('passing_marks', 40)),
                    )
                except InvalidOperation:
                    return Response(
                        {'error': 'Enter valid assignment marks.'},
                        status=400,
                    )
                if (
                    total_marks <= 0
                    or passing_marks < 0
                    or passing_marks > total_marks
                ):
                    return Response(
                        {'error': 'Passing marks must fit within total marks.'},
                        status=400,
                    )
                assignment = Assignment.objects.create(
                    org=org,
                    branch=scope.branch,
                    classification=scope.classification,
                    section=scope.section,
                    subject=scope.subject,
                    teacher_assignment=scope,
                    course=scope.course,
                    title=title[:250],
                    description=(
                        request.data.get('description') or ''
                    ).strip(),
                    instructions=(
                        request.data.get('instructions') or ''
                    ).strip(),
                    assigned_by=request.user,
                    start_date=timezone.localdate(),
                    due_date=due_date,
                    total_marks=total_marks,
                    passing_marks=passing_marks,
                    visibility='published',
                    status='open',
                )
                return Response(
                    _teacher_assignment_payload(assignment),
                    status=201,
                )
            description = (request.data.get('description') or '').strip()
            if not description:
                return Response(
                    {'error': 'Homework description is required.'},
                    status=400,
                )
            priority = request.data.get('priority', 'medium')
            frequency = request.data.get('frequency', 'one_time')
            if priority not in dict(Homework.PRIORITY_CHOICES):
                return Response(
                    {'error': 'Choose a valid homework priority.'},
                    status=400,
                )
            if frequency not in dict(Homework.FREQUENCY_CHOICES):
                return Response(
                    {'error': 'Choose a valid homework frequency.'},
                    status=400,
                )
            estimated_time = request.data.get('estimated_time_minutes')
            if estimated_time in (None, ''):
                estimated_time = None
            else:
                try:
                    estimated_time = int(estimated_time)
                except (TypeError, ValueError):
                    return Response(
                        {'error': 'Estimated time must be a whole number.'},
                        status=400,
                    )
                if not 1 <= estimated_time <= 1440:
                    return Response(
                        {
                            'error':
                            'Estimated time must be between 1 and 1440 minutes.'
                        },
                        status=400,
                    )
            with transaction.atomic():
                item = Homework.objects.create(
                    org=org,
                    branch=scope.branch,
                    classification=scope.classification,
                    section=scope.section,
                    subject=scope.subject,
                    teacher_assignment=scope,
                    assigned_by=request.user,
                    description=description,
                    due_date=due_date,
                    priority=priority,
                    estimated_time_minutes=estimated_time,
                    frequency=frequency,
                    status='active',
                )
                roster = roster_for_subject(
                    org,
                    scope.subject,
                    scope.classification,
                    scope.section,
                    academic_year=scope.academic_year,
                )
                HomeworkStatus.objects.bulk_create([
                    HomeworkStatus(homework=item, student=student)
                    for student in roster
                ], ignore_conflicts=True)
            item = homework.filter(pk=item.pk).first() or item
            return Response(_teacher_homework_payload(item), status=201)
        if action == 'grade_submission':
            submission = (
                AssignmentSubmission.objects.filter(
                    pk=request.data.get('submission_id'),
                    assignment__org=org,
                    assignment__teacher_assignment_id__in=scope_ids,
                )
                .select_related('assignment', 'student')
                .first()
            )
            if submission is None:
                return Response({'error': 'Submission not found.'}, status=404)
            try:
                marks = Decimal(str(request.data.get('obtained_marks', '')))
            except InvalidOperation:
                return Response({'error': 'Valid marks are required.'}, status=400)
            if marks < 0 or marks > submission.assignment.total_marks:
                return Response(
                    {'error': 'Marks are outside the valid range.'},
                    status=400,
                )
            with transaction.atomic():
                submission.obtained_marks = marks
                submission.teacher_remarks = (
                    request.data.get('teacher_remarks') or ''
                ).strip()
                submission.status = request.data.get('status', 'graded')
                if submission.status not in dict(
                    AssignmentSubmission.STATUS_CHOICES,
                ):
                    submission.status = 'graded'
                submission.graded_by = request.user
                submission.graded_at = timezone.now()
                submission.save()
                AssignmentSubmissionHistory.objects.create(
                    submission=submission,
                    action='graded',
                    status=submission.status,
                    obtained_marks=marks,
                    remarks=submission.teacher_remarks,
                    performed_by=request.user,
                )
            return Response({'status': 'success'})
        if action == 'verify_homework':
            status_obj = (
                HomeworkStatus.objects.filter(
                    pk=request.data.get('status_id'),
                    homework__org=org,
                    homework__teacher_assignment_id__in=scope_ids,
                    status='completed',
                )
                .select_related('student')
                .first()
            )
            if status_obj is None:
                return Response(
                    {'error': 'Completed homework record not found.'},
                    status=404,
                )
            status_obj.verified_by_teacher = True
            status_obj.verified_at = timezone.now()
            status_obj.save(update_fields=[
                'verified_by_teacher',
                'verified_at',
            ])
            return Response({'status': 'success'})
        return Response({'error': 'Unsupported teacher action.'}, status=400)
    return Response({
        'scopes': [_teacher_scope_payload(item) for item in scopes],
        'assignments': [
            _teacher_assignment_payload(item) for item in assignments[:50]
        ],
        'homework': [
            _teacher_homework_payload(item) for item in homework[:50]
        ],
    })


def _teacher_exam_payload(exam, scopes):
    return {
        'id': exam.id,
        'name': exam.name,
        'classification': (
            exam.classification.name if exam.classification_id else ''
        ),
        'section': exam.section.name if exam.section_id else '',
        'start_date': exam.start_date.isoformat() if exam.start_date else None,
        'end_date': exam.end_date.isoformat() if exam.end_date else None,
        'status': exam.status,
        'is_published': exam.is_published,
        'scopes': [_teacher_scope_payload(item) for item in scopes],
    }


@api_view(['GET'])
@permission_classes([IsAuthenticated])
@authentication_classes([JWTAuthentication])
def api_teacher_exams(request):
    from handle.models import ExamTerm

    org, memb, scopes, error = _teacher_mobile_context(
        request,
        feature='results',
    )
    if error:
        return error
    scope_list = list(scopes.select_related(
        'academic_year',
        'branch',
        'course',
        'classification',
        'section',
        'subject',
    ))
    exams = ExamTerm.objects.filter(
        org=org,
        classification_id__in={
            item.classification_id for item in scope_list
        },
    ).select_related('classification', 'section').order_by(
        '-start_date',
        '-id',
    )
    result = []
    for exam in exams:
        matching = [
            scope for scope in scope_list
            if scope.classification_id == exam.classification_id
            and (
                not exam.section_id
                or not scope.section_id
                or scope.section_id == exam.section_id
            )
        ]
        if matching:
            result.append(_teacher_exam_payload(exam, matching))
    return Response({'results': result})


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
@authentication_classes([JWTAuthentication])
def api_teacher_exam_marks(request, exam_id, scope_id):
    from decimal import Decimal, InvalidOperation
    from django.db import transaction
    from handle.academics import roster_for_subject
    from handle.models import ExamTerm, ResultRecord

    org, memb, scopes, error = _teacher_mobile_context(
        request,
        feature='results',
    )
    if error:
        return error
    scope = scopes.select_related(
        'academic_year',
        'course',
        'classification',
        'section',
        'subject',
    ).filter(pk=scope_id).first()
    if scope is None:
        return Response({'error': 'Teaching assignment not found.'}, status=404)
    exam = ExamTerm.objects.filter(
        pk=exam_id,
        org=org,
        classification_id=scope.classification_id,
    ).first()
    if exam is None or (
        exam.section_id
        and scope.section_id
        and exam.section_id != scope.section_id
    ):
        return Response({'error': 'Exam scope not found.'}, status=404)
    roster = list(roster_for_subject(
        org,
        scope.subject,
        scope.classification,
        exam.section or scope.section,
        academic_year=scope.academic_year,
    ))
    roster_by_id = {item.id: item for item in roster}
    if request.method == 'POST':
        if exam.is_published or exam.status == 'archived':
            return Response(
                {'error': 'Published or archived marks are read-only.'},
                status=409,
            )
        rows = request.data.get('marks', [])
        if not isinstance(rows, list):
            return Response({'error': 'Marks must be a list.'}, status=400)
        pending = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            try:
                student_id = int(row.get('student_id'))
            except (TypeError, ValueError):
                return Response({'error': 'Invalid student.'}, status=400)
            student = roster_by_id.get(student_id)
            if student is None:
                return Response(
                    {'error': 'A student is outside this exam roster.'},
                    status=403,
                )
            is_absent = row.get('is_absent') is True
            try:
                marks = (
                    Decimal('0')
                    if is_absent
                    else Decimal(str(row.get('obtained_marks', '')))
                )
            except InvalidOperation:
                return Response(
                    {'error': f'Enter valid marks for {student.name}.'},
                    status=400,
                )
            if marks < 0 or marks > scope.subject.full_marks:
                return Response(
                    {
                        'error':
                        f'Marks for {student.name} must be between 0 and '
                        f'{scope.subject.full_marks}.',
                    },
                    status=400,
                )
            pending.append((
                student,
                marks,
                is_absent,
                (row.get('remarks') or '').strip(),
            ))
        with transaction.atomic():
            locked_exam = ExamTerm.objects.select_for_update().get(pk=exam.pk)
            if locked_exam.is_published or locked_exam.status == 'archived':
                return Response(
                    {'error': 'This exam became read-only.'},
                    status=409,
                )
            for student, marks, is_absent, remarks in pending:
                record, created = ResultRecord.objects.update_or_create(
                    student=student,
                    exam=locked_exam,
                    subject=scope.subject,
                    defaults={
                        'obtained_marks': marks,
                        'is_absent': is_absent,
                        'remarks': remarks or (
                            'Absent' if is_absent else None
                        ),
                        'updated_by': request.user,
                    },
                )
                if created:
                    record.created_by = request.user
                    record.save(update_fields=['created_by'])
            if pending and locked_exam.status == 'draft':
                locked_exam.status = 'marks_entry'
                locked_exam.save(update_fields=['status'])
        return Response({'status': 'success', 'saved': len(pending)})
    existing = {
        item.student_id: item
        for item in ResultRecord.objects.filter(
            exam=exam,
            subject=scope.subject,
            student_id__in=roster_by_id,
        )
    }
    return Response({
        'exam': _teacher_exam_payload(exam, [scope]),
        'scope': _teacher_scope_payload(scope),
        'can_edit': not exam.is_published and exam.status != 'archived',
        'full_marks': str(scope.subject.full_marks),
        'pass_marks': str(scope.subject.pass_marks),
        'students': [{
            'id': student.id,
            'name': student.name,
            'roll_number': student.roll_number or '',
            'obtained_marks': (
                str(existing[student.id].obtained_marks)
                if student.id in existing else ''
            ),
            'is_absent': (
                existing[student.id].is_absent
                if student.id in existing else False
            ),
            'grade': (
                existing[student.id].grade or ''
                if student.id in existing else ''
            ),
            'remarks': (
                existing[student.id].remarks or ''
                if student.id in existing else ''
            ),
        } for student in roster],
    })


def _bus_payload(bus):
    return {
        'id': bus.id,
        'name': bus.name,
        'registration_number': bus.registration_number,
        'route_name': bus.route_name or '',
        'capacity': bus.capacity,
        'branch': (
            {'id': bus.branch_id, 'name': bus.branch.name}
            if bus.branch_id else None
        ),
        'driver': (
            {'id': bus.driver_id, 'name': bus.driver.name}
            if bus.driver_id else None
        ),
    }


def _bus_tracking_payload(session):
    if session is None:
        return None
    return {
        'id': session.id,
        'status': session.status,
        'started_at': session.started_at.isoformat(),
        'stopped_at': (
            session.stopped_at.isoformat() if session.stopped_at else None
        ),
        'last_ping_at': (
            session.last_ping_at.isoformat() if session.last_ping_at else None
        ),
        'latitude': session.last_latitude,
        'longitude': session.last_longitude,
        'accuracy_meters': session.last_accuracy_meters,
    }


def _distance_meters(latitude, longitude, target_latitude, target_longitude):
    import math

    if None in (latitude, longitude, target_latitude, target_longitude):
        return None
    lat1, lon1, lat2, lon2 = map(math.radians, (
        latitude, longitude, target_latitude, target_longitude,
    ))
    delta_lat = lat2 - lat1
    delta_lon = lon2 - lon1
    value = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2)
        * math.sin(delta_lon / 2) ** 2
    )
    value = min(max(value, 0), 1)
    return round(6371000 * 2 * math.atan2(math.sqrt(value), math.sqrt(1 - value)))


def _bus_student_payload(assignment, trip_status=None, tracking=None):
    distance = _distance_meters(
        tracking.last_latitude if tracking else None,
        tracking.last_longitude if tracking else None,
        assignment.stop_latitude,
        assignment.stop_longitude,
    )
    student = assignment.student
    return {
        'assignment_id': assignment.id,
        'student': {
            'id': student.id,
            'name': student.name,
            'roll_number': student.roll_number or '',
            'classification': (
                student.classification.name if student.classification_id else ''
            ),
            'section': student.section.name if student.section_id else '',
        },
        'stop': {
            'name': assignment.stop_name,
            'latitude': assignment.stop_latitude,
            'longitude': assignment.stop_longitude,
            'configured': (
                assignment.stop_latitude is not None
                and assignment.stop_longitude is not None
            ),
        },
        'trip_status': trip_status.status if trip_status else 'waiting',
        'trip_status_label': (
            trip_status.get_status_display() if trip_status else 'Waiting'
        ),
        'note': trip_status.note if trip_status else '',
        'picked_up_at': (
            trip_status.picked_up_at.isoformat()
            if trip_status and trip_status.picked_up_at else None
        ),
        'dropped_off_at': (
            trip_status.dropped_off_at.isoformat()
            if trip_status and trip_status.dropped_off_at else None
        ),
        'distance_from_bus_meters': distance,
        'estimated_arrival_minutes': (
            max(1, round(distance / 333)) if distance is not None else None
        ),
    }


def _driver_bus_data(bus, session):
    from handle.models import BusStudentTripStatus

    assignments = list(
        bus.student_assignments.filter(status='active', org=bus.org)
        .select_related('student__classification', 'student__section')
        .order_by('stop_name', 'student__name')
    )
    states = {}
    if session:
        states = {
            item.assignment_id: item
            for item in BusStudentTripStatus.objects.filter(
                session=session,
                assignment_id__in=[assignment.id for assignment in assignments],
            )
        }
    students = [
        _bus_student_payload(
            assignment,
            states.get(assignment.id),
            session,
        )
        for assignment in assignments
    ]
    return {
        'bus': _bus_payload(bus),
        'tracking': _bus_tracking_payload(session),
        'student_count': len(students),
        'students': students,
        'pickup_summary': {
            'waiting': sum(item['trip_status'] == 'waiting' for item in students),
            'picked_up': sum(item['trip_status'] == 'picked_up' for item in students),
            'dropped_off': sum(item['trip_status'] == 'dropped_off' for item in students),
            'skipped': sum(item['trip_status'] == 'skipped' for item in students),
        },
        'poll_after_seconds': 10,
    }


def _parse_mobile_coordinates(data):
    import math

    try:
        latitude = float(data.get('latitude'))
        longitude = float(data.get('longitude'))
        accuracy = (
            float(data.get('accuracy'))
            if data.get('accuracy') not in (None, '') else None
        )
    except (TypeError, ValueError):
        return None, None, None, 'Valid GPS coordinates are required.'
    if (
        not math.isfinite(latitude)
        or not math.isfinite(longitude)
        or not -90 <= latitude <= 90
        or not -180 <= longitude <= 180
    ):
        return None, None, None, 'GPS coordinates are out of range.'
    if accuracy is not None and (
        not math.isfinite(accuracy) or accuracy < 0 or accuracy > 5000
    ):
        return None, None, None, 'GPS accuracy is invalid.'
    return latitude, longitude, accuracy, None


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
@authentication_classes([JWTAuthentication])
def api_driver_bus_tracking(request):
    from django.db import IntegrityError, transaction
    from django.utils import timezone
    from handle.models import (
        BusLocationPing,
        BusStudentTripStatus,
        BusTrackingSession,
        SchoolBus,
        StudentBusAssignment,
    )

    org, memb = _mobile_staff_context(request)
    if org is None or memb is None or memb.member_type != 'driver':
        return Response({'error': 'Driver access is required.'}, status=403)
    bus = SchoolBus.objects.filter(
        org=org,
        driver=memb,
        is_active=True,
    ).select_related('branch', 'driver').first()
    if bus is None:
        return Response(
            {'error': 'No active bus is assigned to this driver.'},
            status=404,
        )
    if bus.branch_id and bus.branch_id != memb.branch_id:
        return Response({'error': 'Bus branch does not match driver branch.'}, status=403)
    session = BusTrackingSession.objects.filter(
        org=org, bus=bus, status='active',
    ).order_by('-started_at').first()
    if request.method == 'POST':
        action = (request.data.get('action') or '').strip()
        if action == 'start':
            if session and session.driver_id != memb.id:
                return Response(
                    {'error': 'This bus is already being tracked by another driver.'},
                    status=409,
                )
            if session is None:
                try:
                    with transaction.atomic():
                        session = BusTrackingSession.objects.create(
                            org=org,
                            bus=bus,
                            driver=memb,
                        )
                except IntegrityError:
                    session = BusTrackingSession.objects.filter(
                        org=org, bus=bus, status='active',
                    ).first()
            return Response(_driver_bus_data(bus, session))
        if session is None or session.driver_id != memb.id:
            return Response({'error': 'No active driver trip was found.'}, status=409)
        student_actions = {
            'student_waiting': 'waiting',
            'student_pickup': 'picked_up',
            'student_dropoff': 'dropped_off',
            'student_skip': 'skipped',
        }
        if action in student_actions:
            assignment = StudentBusAssignment.objects.filter(
                pk=request.data.get('assignment_id'),
                org=org,
                bus=bus,
                status='active',
                student__org=org,
            ).first()
            if assignment is None:
                return Response({'error': 'Assigned student was not found.'}, status=404)
            requested_status = student_actions[action]
            with transaction.atomic():
                trip_status, _ = BusStudentTripStatus.objects.select_for_update().get_or_create(
                    session=session,
                    assignment=assignment,
                    defaults={
                        'org': org,
                        'bus': bus,
                        'student': assignment.student,
                        'marked_by': memb,
                    },
                )
                if requested_status == 'dropped_off' and trip_status.status != 'picked_up':
                    return Response(
                        {'error': 'Mark the student picked up before drop-off.'},
                        status=409,
                    )
                trip_status.status = requested_status
                trip_status.note = (request.data.get('note') or '').strip()[:250]
                trip_status.marked_by = memb
                if requested_status == 'picked_up':
                    trip_status.picked_up_at = timezone.now()
                    trip_status.dropped_off_at = None
                elif requested_status == 'dropped_off':
                    trip_status.dropped_off_at = timezone.now()
                elif requested_status == 'waiting':
                    trip_status.picked_up_at = None
                    trip_status.dropped_off_at = None
                trip_status.save()
            return Response(_driver_bus_data(bus, session))
        if action == 'stop':
            with transaction.atomic():
                locked = BusTrackingSession.objects.select_for_update().get(
                    pk=session.pk,
                    status='active',
                )
                locked.status = 'stopped'
                locked.stopped_at = timezone.now()
                locked.save(update_fields=['status', 'stopped_at'])
            return Response(_driver_bus_data(bus, locked))
        if action != 'ping':
            return Response({'error': 'Unsupported driver action.'}, status=400)
        latitude, longitude, accuracy, coordinate_error = (
            _parse_mobile_coordinates(request.data)
        )
        if coordinate_error:
            return Response({'error': coordinate_error}, status=400)
        now = timezone.now()
        if (
            session.last_ping_at
            and (now - session.last_ping_at).total_seconds() < 8
        ):
            return Response(
                {'error': 'Location update received too soon.'},
                status=429,
            )
        with transaction.atomic():
            locked = BusTrackingSession.objects.select_for_update().get(
                pk=session.pk,
                status='active',
                driver=memb,
            )
            BusLocationPing.objects.create(
                session=locked,
                org=org,
                bus=bus,
                driver=memb,
                latitude=latitude,
                longitude=longitude,
                accuracy_meters=accuracy,
            )
            locked.last_ping_at = now
            locked.last_latitude = latitude
            locked.last_longitude = longitude
            locked.last_accuracy_meters = accuracy
            locked.save(update_fields=[
                'last_ping_at',
                'last_latitude',
                'last_longitude',
                'last_accuracy_meters',
            ])
        session = locked
    return Response(_driver_bus_data(bus, session))


@api_view(['GET'])
@permission_classes([IsAuthenticated])
@authentication_classes([JWTAuthentication])
def api_student_bus_tracking(request):
    from django.utils import timezone
    from handle.models import BusStudentTripStatus, StudentBusAssignment

    org, memb = _mobile_student_context(request)
    if org is None:
        return Response({'error': 'Student access is required.'}, status=403)
    assignment = StudentBusAssignment.objects.filter(
        org=org,
        student=memb,
        status='active',
        bus__org=org,
        bus__is_active=True,
    ).select_related('bus__branch', 'bus__driver').first()
    if assignment is None:
        return Response({
            'assigned': False,
            'message': 'No active bus is assigned to this student.',
        })
    bus = assignment.bus
    session = bus.tracking_sessions.filter(
        org=org,
        status='active',
    ).order_by('-started_at').first()
    is_live = bool(
        session
        and session.last_ping_at
        and (timezone.now() - session.last_ping_at).total_seconds() <= 300
    )
    trip_status = (
        BusStudentTripStatus.objects.filter(
            session=session,
            assignment=assignment,
            student=memb,
            org=org,
        ).first()
        if session else None
    )
    student_trip = _bus_student_payload(assignment, trip_status, session)
    return Response({
        'assigned': True,
        'bus': _bus_payload(bus),
        'stop': {
            'name': assignment.stop_name,
            'latitude': assignment.stop_latitude,
            'longitude': assignment.stop_longitude,
        },
        'tracking': _bus_tracking_payload(session),
        'is_live': is_live,
        'distance_to_stop_meters': student_trip['distance_from_bus_meters'],
        'estimated_arrival_minutes': student_trip['estimated_arrival_minutes'],
        'pickup_status': student_trip['trip_status'],
        'pickup_status_label': student_trip['trip_status_label'],
        'picked_up_at': student_trip['picked_up_at'],
        'dropped_off_at': student_trip['dropped_off_at'],
        'poll_after_seconds': 10,
    })


# 5. Library — mobile support. Gated by the 'library' DynamicFeature exactly
# like the web views (FeatureRequiredMixin / has_feature), so a disabled org
# gets a clean 403 rather than leaking data through the API.
@api_view(['GET'])
@permission_classes([IsAuthenticated])
@authentication_classes([JWTAuthentication])
def api_library_books(request):
    from school.features import get_org_for_user, has_feature
    from handle.models import Book

    org = get_org_for_user(request.user)
    if org is None:
        return Response({"error": "No organization found for this user."}, status=status.HTTP_404_NOT_FOUND)
    if not has_feature(org, 'library'):
        return Response({"error": "Library is not enabled for your organization."}, status=status.HTTP_403_FORBIDDEN)

    qs = Book.objects.filter(org=org, status='active').select_related('category', 'author')
    search = request.GET.get('search', '').strip()
    if search:
        qs = qs.filter(title__icontains=search)

    books = [{
        "id": b.id,
        "book_code": b.book_code,
        "title": b.title,
        "author": b.author.name if b.author else None,
        "category": b.category.name if b.category else None,
        "available_quantity": b.available_quantity,
        "quantity": b.quantity,
        "cover_image": b.cover_image.url if b.cover_image else None,
    } for b in qs]

    return Response({"org_id": org.id, "books": books}, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
@authentication_classes([JWTAuthentication])
def api_my_book_issues(request):
    """The logged-in staff/student's own borrowing history."""
    from school.features import get_org_for_user, has_feature

    org = get_org_for_user(request.user)
    if org is None:
        return Response({"error": "No organization found for this user."}, status=status.HTTP_404_NOT_FOUND)
    if not has_feature(org, 'library'):
        return Response({"error": "Library is not enabled for your organization."}, status=status.HTTP_403_FORBIDDEN)

    try:
        mem = request.user.staff.member
    except Exception:
        return Response({"error": "No member profile linked to this account."}, status=status.HTTP_404_NOT_FOUND)

    issues = mem.book_issues.select_related('book').order_by('-issue_date')[:50]
    data = [{
        "id": i.id,
        "book_title": i.book.title,
        "issue_date": i.issue_date,
        "due_date": i.due_date,
        "return_date": i.return_date,
        "status": i.status,
        "is_overdue": i.is_overdue,
        "fine": str(i.fine),
    } for i in issues]

    return Response({"org_id": org.id, "issues": data}, status=status.HTTP_200_OK)
