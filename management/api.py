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