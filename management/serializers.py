from django.db.models import fields
from rest_framework import serializers
from handle.models import member
from handle.models import Classification, Device
from .models import Organization
from handle.models import AttendanceRecord
class MemberSerializer(serializers.ModelSerializer):
    class Meta:
        model = member
        fields = ('__all__')

class OrganizationSerializer(serializers.ModelSerializer):
    class Meta:
        model= Organization
        fields = ("__all__")

class AttendanceSerializer(serializers.ModelSerializer):
    class Meta:
        model = AttendanceRecord
        fields = ("__all__")

class ClassificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Classification
        fields = ('__all__')

class DeviceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Device
        fields = ("__all__")