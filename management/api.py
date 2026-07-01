from django.db.models import query
from rest_framework import generics, serializers

from handle.models import Classification, Device
from .serializers import ClassificationSerializer, DeviceSerializer, MemberSerializer, OrganizationSerializer, AttendanceSerializer
from handle.models import member, AttendanceRecord
from .models import Organization
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework.reverse import reverse
import pytz

class MemberList(generics.ListCreateAPIView):
    queryset = member.objects.all().order_by('-id')
    serializer_class = MemberSerializer


class MemberDetail(generics.RetrieveUpdateDestroyAPIView):
    queryset = member.objects.all()
    serializer_class = MemberSerializer


class OraganizationList(generics.ListAPIView):
    queryset = Organization.objects.all()
    serializer_class = OrganizationSerializer

class ClassificationList(generics.ListCreateAPIView):
    queryset = Classification.objects.all()
    serializer_class = ClassificationSerializer

class DeviceList(generics.ListCreateAPIView):
    queryset = Device.objects.all()
    serializer_class = DeviceSerializer

class MemberDetails(generics.RetrieveDestroyAPIView):
    queryset = member.objects.all()
    serializer_class = MemberSerializer


class AttendanceRecordAdd(generics.CreateAPIView):
    queryset = AttendanceRecord.objects.all()
    serializer_class = AttendanceSerializer
    
    def perform_create(self, serializer):
        # 1. Get the time DRF parsed from the ZKTeco device
        wrong_time = serializer.validated_data.get('scanned_time')
        
        if wrong_time:
            # 2. Strip away the incorrect UTC timezone DRF assigned to it
            naive_time = wrong_time.replace(tzinfo=None)
            
            # 3. Explicitly tell Django this time is from Kathmandu
            ktm_tz = pytz.timezone('Asia/Kathmandu')
            correct_aware_time = ktm_tz.localize(naive_time)
            
            # 4. Save the record with the correctly localized time
            serializer.save(scanned_time=correct_aware_time)
        else:
            serializer.save()