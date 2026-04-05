from django.core.exceptions import ValidationError
from django.forms import ModelForm
from django import forms
from management.models import Organization, Schooladmin
from management.models import CustomUser
from handle.models import Staff


class SchooladminForm(forms.ModelForm):
    first_name = forms.CharField(label = 'First Name', widget = forms.TextInput(attrs={'class':'form-control', 'placeholder':'First Name'}))
    last_name = forms.CharField(label = 'Last Name', widget = forms.TextInput(attrs={'class':'form-control', 'placeholder':'Last Name'}))
    email = forms.EmailField(label = 'Email', max_length = 200, widget = forms.TextInput(attrs={'class':'form-control', 'placeholder' : 'Email'}))
    password = forms.CharField(label = 'Password', widget = forms.PasswordInput(attrs={'class':'form-control', 'placeholder':'Password'}))
    re_password = forms.CharField(label = 'Repeat Password', widget = forms.PasswordInput(attrs={'class':'form-control', 'placeholder':'Repeat Password'}))
    class Meta:
       model = Schooladmin 
       fields = ('first_name', 'last_name','email', 'number','password','re_password','org')
       labels = {
           'number' :'Phone Number',
           'org':'Organization'
           
       }
       widgets = {
        'org': forms.Select(attrs={'class':'form-control', 'placeholder' : 'Organization'}),
        'number': forms.NumberInput(attrs={'class':'form-control', 'placeholder' : 'Your Phone Number'}),
   }
       
    def clean_email(self):
        email = self.cleaned_data['email']
        try:
            match = CustomUser.objects.get(email=email)
        except CustomUser.DoesNotExist:
            # Unable to find a user, this is fine
            return email
        # A user was found with this as a username, raise an error.
        raise forms.ValidationError('This email address is already in use.')
    def clean_number(self):
        data = self.cleaned_data['number']
        d = str(data)
        if len(d) > 10 or len(d) < 10 :
            raise ValidationError("Number can not be less or more than 10 digits")
        if not d.startswith('98' or '97'):
            raise ValidationError("Nepali number should start with 98")
        return data
    def clean_password(self):
        data = self.cleaned_data['password']
        d = str(data)
        if len(d) < 6:
            raise ValidationError("Password must be greater than 6 digits")
        return data
    def clean_re_password(self):
        password1 = self.cleaned_data.get('password')
        password2 = self.cleaned_data.get('re_password')
        if password1 and password2:
            if password1 != password2:
                raise forms.ValidationError('Password Did not Match')
        return password2
    

class StaffadminForm(forms.ModelForm):
    first_name = forms.CharField(label = 'First Name', widget = forms.TextInput(attrs={'class':'form-control', 'placeholder':'First Name'}))
    last_name = forms.CharField(label = 'Last Name', widget = forms.TextInput(attrs={'class':'form-control', 'placeholder':'Last Name'}))
    email = forms.EmailField(label = 'Email', max_length = 200, widget = forms.TextInput(attrs={'class':'form-control', 'placeholder' : 'Email'}))
    password = forms.CharField(label = 'Password', widget = forms.PasswordInput(attrs={'class':'form-control', 'placeholder':'Password'}))
    re_password = forms.CharField(label = 'Repeat Password', widget = forms.PasswordInput(attrs={'class':'form-control', 'placeholder':'Repeat Password'}))
    class Meta:
       model = Staff 
       fields = ('first_name', 'last_name','email', 'number','password','re_password','org')
       labels = {
           'number' :'Phone Number',
           'org':'Organization'
           
       }
       widgets = {
        'org': forms.Select(attrs={'class':'form-control', 'placeholder' : 'Organization'}),
        'number': forms.NumberInput(attrs={'class':'form-control', 'placeholder' : 'Your Phone Number'}),
   }
       
    def clean_email(self):
        email = self.cleaned_data['email']
        try:
            match = CustomUser.objects.get(email=email)
        except CustomUser.DoesNotExist:
            # Unable to find a user, this is fine
            return email
        # A user was found with this as a username, raise an error.
        raise forms.ValidationError('This email address is already in use.')
    def clean_number(self):
        data = self.cleaned_data['number']
        d = str(data)
        if len(d) > 10 or len(d) < 10 :
            raise ValidationError("Number can not be less or more than 10 digits")
        if not d.startswith('98' or '97'):
            raise ValidationError("Nepali number should start with 98")
        return data
    def clean_password(self):
        data = self.cleaned_data['password']
        d = str(data)
        if len(d) < 6:
            raise ValidationError("Password must be greater than 6 digits")
        return data
    def clean_re_password(self):
        password1 = self.cleaned_data.get('password')
        password2 = self.cleaned_data.get('re_password')
        if password1 and password2:
            if password1 != password2:
                raise forms.ValidationError('Password Did not Match')
        return password2

class OrgForm(ModelForm):
    class Meta:
        model = Organization
        fields = ('name','expire_on', 'address','member_limit','mutifeature_enable','serial_key','new_serial_key','activate')

        labels = {
            'name':"Name",
            'expire_on':"Date of Expire",
            'mutifeature_enable':'Allow staff to do attendance without device',
            'serial_key':"Organization Key ",
            'new_serial_key': 'Activation Number',
            'member_limit':'Member Limitation',
            'activate':'Activated'
        }
        widgets ={
            'name':forms.TextInput(attrs= {'class':'form-control mb-3 mt-3', 'placeholder':' Name'}),
            'mutifeature_enable':forms.CheckboxInput(),
            'member_limit':forms.NumberInput(attrs= {'class':'form-control mb-3 mt-3', 'placeholder':'Limit'}),
            'address':forms.TextInput(attrs= {'class':'form-control mb-3 mt-3', 'placeholder':' Full Address'}),
            'serial_key':forms.TextInput(attrs= {'class':'form-control mb-3 mt-3', 'placeholder':'Puller key'}),
            'expire_on':forms.DateInput(attrs= {'class':'date-picker form-control mb-3 mt-3', 'type':'date'}),
            'new_serial_key':forms.TextInput(attrs= {'class':'form-control mb-3 mt-3', 'placeholder':'Activation Key'}),
            'activate':forms.CheckboxInput()
        }