
from django.forms import ModelForm
from django import forms
from handle.models import member
from management.models import Organization



from django import forms
from management.models import LocationBased, QRCode, AutoCheckin

class LocationForm(forms.ModelForm):
    class Meta:
        model = LocationBased
        fields = '__all__'
        exclude = ('org',)

        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control col-6',
                'placeholder': 'Enter location name'
            }),
            'latitude': forms.NumberInput(attrs={
                'class': 'form-control col-6',
                'placeholder': 'Enter latitude (e.g. 37.7749)'
            }),
            'longitude': forms.NumberInput(attrs={
                'class': 'form-control col-6',
                'placeholder': 'Enter longitude (e.g. -122.4194)'
            }),
            'radius': forms.NumberInput(attrs={
                'class': 'form-control col-6',
                'placeholder': 'Enter radius in meters'
            }),
        }

class QRCodeForm(forms.ModelForm):
    class Meta:
        model = QRCode
        fields = '__all__'
        exclude = ('org',)

        widgets = {
            'org': forms.Select(attrs={
                'class': 'form-control col-6',
                'placeholder': 'Select organization'
            }),
            'member': forms.Select(attrs={
                'class': 'form-control col-6',
                'placeholder': 'Select member'
            }),
            'auto_checked_in_by': forms.Select(attrs={
                'class': 'form-control col-6',
                'placeholder': 'Select user (optional)'
            }),
            'name': forms.TextInput(attrs={
                'class': 'form-control col-6',
                'placeholder': 'Enter check-in name'
            }),
            'checkin_time': forms.DateTimeInput(attrs={
                'class': 'form-control col-6',
                'type': 'datetime-local',
                'placeholder': 'Select check-in time'
            }),
            'checkout_time': forms.DateTimeInput(attrs={
                'class': 'form-control col-6',
                'type': 'datetime-local',
                'placeholder': 'Select check-out time'
            }),
        }

class AutoCheckinForm(forms.ModelForm):

    def __init__(self, *args, **kwargs):
            org = kwargs.pop('org', None)  # Pop the org from kwargs
            super().__init__(*args, **kwargs)

            if org:
                # Assuming Member model has a ForeignKey to Org
                self.fields['member'].queryset = member.objects.filter(org=org)

    class Meta:
        model = AutoCheckin
        fields = '__all__'
        exclude = ('org','auto_checked_in_by',)

        widgets = {
            'checkin_time':forms.DateTimeInput(attrs={'type':'datetime-local','class':'form-control'}),
            'checkout_time':forms.DateTimeInput(attrs={'type':'datetime-local', 'class':'form-control'})
        }

       
        widgets = {
            'org': forms.Select(attrs={
                'class': 'form-control col-12',
                'placeholder': 'Select organization'
            }),
            'member': forms.Select(attrs={
                'class': 'form-control col-12',
                'placeholder': 'Select member'
            }),
            'auto_checked_in_by': forms.Select(attrs={
                'class': 'form-control col-12',
                'placeholder': 'Select user (optional)'
            }),
            'name': forms.TextInput(attrs={
                'class': 'form-control col-12',
                'placeholder': 'Enter check-in name'
            }),
            'checkin_time': forms.DateTimeInput(attrs={
                'class': 'form-control col-12',
                'type': 'datetime-local',
                'placeholder': 'Select check-in time'
            }),
            'checkout_time': forms.DateTimeInput(attrs={
                'class': 'form-control col-12',
                'type': 'datetime-local',
                'placeholder': 'Select check-out time'
            }),
        }



class OrgFormSchool(ModelForm):
    class Meta:
        model = Organization
        fields = ('name', 'address', 'serial_key', 'image', 'nepali_date')

        labels = {
            'name': "Name",
            'expire_on': "Date of Expire",
            'serial_key': "Organization Key",
            'new_serial_key': 'Activation Number',
            'activate': 'Activated',
            'nepali_date': 'Use Nepali Calendar (BS)',
        }
        widgets = {
            'image': forms.FileInput(attrs={'class': 'form-control col-6 mb-3 mt-3'}),
            'name': forms.TextInput(attrs={'class': 'form-control col-6 mb-3 mt-3', 'placeholder': 'Name'}),
            'address': forms.TextInput(attrs={'class': 'form-control col-6 mb-3 mt-3', 'placeholder': 'Full Address'}),
            'serial_key': forms.TextInput(attrs={'class': 'form-control col-6 mb-3 mt-3', 'placeholder': 'Puller key'}),
            'expire_on': forms.DateInput(attrs={'class': 'date-picker col-6 form-control mb-3 mt-3', 'type': 'date'}),
            'new_serial_key': forms.TextInput(attrs={'class': 'form-control col-6 mb-3 mt-3', 'placeholder': 'Activation Key'}),
            'activate': forms.CheckboxInput(),
            'nepali_date': forms.CheckboxInput(attrs={'class': 'form-check-input', 'role': 'switch'}),
        }

