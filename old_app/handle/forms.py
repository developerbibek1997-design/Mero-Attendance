from django import forms
from django.forms import widgets

from management.models import CustomUser
from .models import Classification, Device, member, PaySlip


class PaySlipForm(forms.ModelForm):
    class Meta:
        model = PaySlip
        fields = ('member','from_date', 'to_date', 'month', 'salary', 'tax', 'total')

        labels = {
            'member': "",
            'from_date': "",
            'to_date': "",
            'month': "",
            'salary': "",
            'tax': "",
            'total': ""
        }
        widgets = {
            'member': forms.Select(attrs={'class': 'form-control mt-3' ,'hidden': True}),
            'from_date': forms.DateInput(attrs={'class': 'form-control mt-3 ','hidden': True}),
            'to_date': forms.DateInput(attrs={'class': 'form-control mt-3','hidden': True}),
            'month': forms.TextInput(attrs={'class': 'form-control mt-3','hidden': True}),
            'salary': forms.NumberInput(attrs={'class': 'form-control mt-3','hidden': True}),
            'tax': forms.NumberInput(attrs={'class': 'form-control mt-3','hidden': True}),
            'total': forms.NumberInput(attrs={'class': 'form-control mt-3','hidden': True}),
        }



class MemberForm(forms.ModelForm):
    class Meta:
        model = member
        fields = ('name', 'card', 'gender', 'address', 'email' ,'phone','salary_per_hour')


    def __init__(self, *args, **kwargs):
        super(MemberForm, self).__init__(*args, **kwargs)
        for field in self.fields:
            self.fields[field].widget.attrs.update({'class': 'form-control'})
            self.fields[field].widget.attrs.update({'placeholder': field.capitalize()})

    def clean_email(self):
        email = self.cleaned_data['email']
        try:
            match = member.objects.get(email=email)
        except:
            # Unable to find a user, this is fine
            return email
        # A user was found with this as a username, raise an error.
        raise forms.ValidationError('This email address is already in use.')
    def clean_card(self):
        data = self.cleaned_data['card']
        try:
            match = member.objects.get(card=data)
        except:
            # Unable to find a user, this is fine
            return data
        raise forms.ValidationError('This card is already in use.')

class ClassificationForm(forms.ModelForm):
    class Meta:
        model = Classification
        fields = ('name',)

        widgets = {
            'name': forms.TextInput(attrs={'required': True, 'class':'form-control', 'placeholder':'Classification / Section'})
        }

class DeviceForm(forms.ModelForm):
    class Meta:
        model = Device
        fields =('name','ip_address', 'port_no')

        widgets = {
            'name': forms.TextInput(attrs={'required': True, 'class':'form-control', 'placeholder':'Name of the Device'}),
            'ip_address': forms.TextInput(attrs={'required': True, 'class':'form-control', 'placeholder':'Ip Address'}),
            'port_no': forms.TextInput(attrs={'required': True, 'class':'form-control', 'placeholder':'Port No.'})
        }


from django.contrib.auth.forms import PasswordChangeForm

class FormChangePassword(PasswordChangeForm):
    def __init__(self, *args, **kwargs):
        super(FormChangePassword, self).__init__(*args, **kwargs)
        for field in ('old_password', 'new_password1', 'new_password2'):
            self.fields['old_password'].widget.attrs = {'class':'form-control ps-0 form-control-line', 'placeholder':"Old Password"}
            self.fields['new_password1'].widget.attrs = {'class':'form-control ps-0 form-control-line', 'placeholder':"New Password"}
            self.fields['new_password2'].widget.attrs = {'class':'form-control ps-0 form-control-line', 'placeholder':"Re New Password"}