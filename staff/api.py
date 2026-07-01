from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from rest_framework_simplejwt.authentication import JWTAuthentication
from django.core.exceptions import ObjectDoesNotExist
import datetime
from handle.models import AttendingClassification, Classification, member, AttendanceRecord, Organization

# 1. API to get the classes and organization features for the dashboard
@api_view(['GET'])
@permission_classes([IsAuthenticated])
@authentication_classes([JWTAuthentication])
def api_staff_classes(request):
    try:
        # 1. Safely determine the organization without crashing
        if hasattr(request.user, 'schooladmin') and request.user.schooladmin:
            org = request.user.schooladmin.org
            staff_classes = [] # Admins usually don't have attending classes
        elif hasattr(request.user, 'staff') and request.user.staff:
            org = request.user.staff.org
            staff_classes = AttendingClassification.objects.filter(staff=request.user)
        else:
            return Response({"error": "No valid staff or admin profile found."}, status=status.HTTP_404_NOT_FOUND)
        
        # 2. Format the classes
        classes_data = [
            {"id": sc.classification.id, "name": sc.classification.name} 
            for sc in staff_classes
        ]
        
        # 3. Use getattr() so it won't crash if a boolean field is missing in your model
        return Response({
            "org_id": org.id,
            "org_name": org.name,
            "location_based": getattr(org, 'location_based', False), 
            "wifi_based": getattr(org, 'wifi_based', False),
            "qr_based": getattr(org, 'qr_based', False),
            "auto_checkin": getattr(org, 'auto_checkin', False),
            "classes": classes_data
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        # If ANYTHING goes wrong, return the exact error as JSON so Flutter can read it!
        print(f"DASHBOARD CRASH: {str(e)}")
        return Response({"error": f"Server crash: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        


# 2. API to get members of a specific class and their attendance status today
@api_view(['GET'])
@permission_classes([IsAuthenticated])
@authentication_classes([JWTAuthentication])
def api_class_members(request, class_id):
    try:
        clas = Classification.objects.get(id=class_id)
        org = request.user.staff.org
        
        # Get all members in this classification and organization
        members = member.objects.filter(classification=clas, org=org)
        
        # Fetch today's attendance records
        today = datetime.datetime.today().date()
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
    member_id = request.data.get('member_id')
    
    if not member_id:
        return Response({"error": "Missing member_id."}, status=status.HTTP_400_BAD_REQUEST)
        
    try:
        memb = member.objects.get(id=member_id)
        org = request.user.staff.org  # Securely get org from logged-in user
        
        # Check if already marked today to avoid duplicates
        today = datetime.datetime.today().date()
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
            scanned_time=datetime.datetime.now()
        )
        return Response(
            {"status": "success", "message": f"{memb.name} marked present."},
            status=status.HTTP_201_CREATED
        )
        
    except member.DoesNotExist:
        return Response({"error": "Member not found."}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)