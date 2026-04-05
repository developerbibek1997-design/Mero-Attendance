
from django.forms import ModelForm
from django import forms
from management.models import Organization



class OrgFormSchool(ModelForm):
    class Meta:
        model = Organization
        fields = ('name', 'address','serial_key', 'image')

        labels = {
            'name':"Name",
            'expire_on':"Date of Expire",
            'serial_key':"Organization Key ",
            'new_serial_key': 'Activation Number',
            'activate':'Activated'
        }
        widgets ={
            'image':forms.FileInput(attrs= {'class':'form-control mb-3 mt-3', 'placeholder':' Name'}),
            'name':forms.TextInput(attrs= {'class':'form-control mb-3 mt-3', 'placeholder':' Name'}),
            'address':forms.TextInput(attrs= {'class':'form-control mb-3 mt-3', 'placeholder':' Full Address'}),
            'serial_key':forms.TextInput(attrs= {'class':'form-control mb-3 mt-3', 'placeholder':'Puller key'}),
            'expire_on':forms.DateInput(attrs= {'class':'date-picker form-control mb-3 mt-3', 'type':'date'}),
            'new_serial_key':forms.TextInput(attrs= {'class':'form-control mb-3 mt-3', 'placeholder':'Activation Key'}),
            'activate':forms.CheckboxInput()
        }

