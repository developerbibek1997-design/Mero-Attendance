import datetime

from django.forms import ModelForm
from django import forms
from django.utils import timezone
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
    # The model stores checkin_time/checkout_time as combined datetimes, but
    # a single native `datetime-local` input can't get the app-wide BS/AD
    # calendar treatment (static/assets/js/global-date-picker.js only
    # upgrades `type="date"` inputs). Splitting each into a date + time pair
    # gives every org the same "nice" calendar here as everywhere else, and
    # the Nepali calendar automatically once `org.nepali_date` is on -
    # clean() below recombines them into the model's datetime fields.
    checkin_date = forms.DateField(
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
        label='Check-in Date',
    )
    checkin_time_only = forms.TimeField(
        widget=forms.TimeInput(attrs={'class': 'form-control', 'type': 'time'}),
        label='Check-in Time',
    )
    checkout_date = forms.DateField(
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
        label='Check-out Date',
    )
    checkout_time_only = forms.TimeField(
        widget=forms.TimeInput(attrs={'class': 'form-control', 'type': 'time'}),
        label='Check-out Time',
    )

    def __init__(self, *args, **kwargs):
        org = kwargs.pop('org', None)  # Pop the org from kwargs
        super().__init__(*args, **kwargs)

        if org:
            # Assuming Member model has a ForeignKey to Org
            self.fields['member'].queryset = member.objects.filter(org=org)

        if self.instance and self.instance.pk:
            if self.instance.checkin_time:
                local_in = timezone.localtime(self.instance.checkin_time)
                self.fields['checkin_date'].initial = local_in.date()
                self.fields['checkin_time_only'].initial = local_in.time()
            if self.instance.checkout_time:
                local_out = timezone.localtime(self.instance.checkout_time)
                self.fields['checkout_date'].initial = local_out.date()
                self.fields['checkout_time_only'].initial = local_out.time()

    class Meta:
        model = AutoCheckin
        fields = ('member', 'name')

        widgets = {
            'member': forms.Select(attrs={'class': 'form-control'}),
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter check-in name',
            }),
        }

    def clean(self):
        cleaned = super().clean()
        checkin_date = cleaned.get('checkin_date')
        checkin_time_only = cleaned.get('checkin_time_only')
        checkout_date = cleaned.get('checkout_date')
        checkout_time_only = cleaned.get('checkout_time_only')

        if checkin_date and checkin_time_only:
            self.instance.checkin_time = timezone.make_aware(
                datetime.datetime.combine(checkin_date, checkin_time_only)
            )
        if checkout_date and checkout_time_only:
            self.instance.checkout_time = timezone.make_aware(
                datetime.datetime.combine(checkout_date, checkout_time_only)
            )

        if (
            self.instance.checkin_time
            and self.instance.checkout_time
            and self.instance.checkin_time >= self.instance.checkout_time
        ):
            raise forms.ValidationError("Check-out must be after check-in.")
        return cleaned



class OrgFormSchool(ModelForm):
    class Meta:
        model = Organization
        fields = ('name', 'address', 'email', 'serial_key', 'image', 'nepali_date')

        labels = {
            'name': "Name",
            'expire_on': "Date of Expire",
            'email': "Organization Email",
            'serial_key': "Organization Key",
            'new_serial_key': 'Activation Number',
            'activate': 'Activated',
            'nepali_date': 'Use Nepali Calendar (BS)',
        }
        widgets = {
            'image': forms.FileInput(attrs={'class': 'form-control col-6 mb-3 mt-3'}),
            'name': forms.TextInput(attrs={'class': 'form-control col-6 mb-3 mt-3', 'placeholder': 'Name'}),
            'address': forms.TextInput(attrs={'class': 'form-control col-6 mb-3 mt-3', 'placeholder': 'Full Address'}),
            'email': forms.EmailInput(attrs={'class': 'form-control col-6 mb-3 mt-3', 'placeholder': 'contact@yourorg.com'}),
            'serial_key': forms.TextInput(attrs={'class': 'form-control col-6 mb-3 mt-3', 'placeholder': 'Puller key'}),
            'expire_on': forms.DateInput(attrs={'class': 'date-picker col-6 form-control mb-3 mt-3', 'type': 'date'}),
            'new_serial_key': forms.TextInput(attrs={'class': 'form-control col-6 mb-3 mt-3', 'placeholder': 'Activation Key'}),
            'activate': forms.CheckboxInput(),
            'nepali_date': forms.CheckboxInput(attrs={'class': 'form-check-input', 'role': 'switch'}),
        }

