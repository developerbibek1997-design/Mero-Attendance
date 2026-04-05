from django.http.response import HttpResponseRedirect
from django.shortcuts import render
from django.views import View
from django.contrib import messages
from django.urls import reverse
from management.models import Organization
from management.models import Schooladmin
from management.models import CustomUser
from .forms import OrgForm, SchooladminForm

# Create your views here.
class Dashboard(View):
    template_name = 'super_admin/SAdashboard.html'

    def get(self, request, *args, **kwagrs):
        org = Organization.objects.all()
        org_count = org.count()
        user_count = Schooladmin.objects.all().count()
        dist = {
            'org':org,
            'org_count':org_count,
            'user_count':user_count

        }
        return render(request, self.template_name, dist)
    
    

class addOrg(View):
    template_name = 'super_admin/addOrg.html'

    def get(self, request, *args, **kwagrs):
        org = Organization.objects.all()
        form = OrgForm()
        dist = {
            'org':org,
            'form':form
        }
        return render(request, self.template_name, dist)
    
    def post(self, request, *args, **kwargs):
        form = OrgForm(request.POST or None)
        if form.is_valid():
            form.save()
            messages.success(request, "Sucessfully Added Organization")
            return HttpResponseRedirect(reverse('superadmin:addOrg'))
        else:
            messages.error(request, "Something went Wrong")
            return HttpResponseRedirect(reverse('superadmin:addOrg'))

def deleteOrg(request, id):
    org = Organization.objects.get(id = id)
    org.delete()
    messages.success(request, "Successfully Delete Organization")
    return HttpResponseRedirect(reverse('superadmin:dashboard'))

def editOrg(request, id):
    form = OrgForm()
    org = Organization.objects.get(id =id)
    form.fields['name'].initial = org.name
    form.fields['address'].initial = org.address
    form.fields['member_limit'].initial = org.member_limit
    form.fields['mutifeature_enable'].initial = org.mutifeature_enable
    form.fields['serial_key'].initial = org.serial_key
    form.fields['expire_on'].initial = org.expire_on
    form.fields['new_serial_key'].initial = org.new_serial_key
    form.fields['activate'].initial = org.activate

    dist = {
        'form':form,
        'org':org
    }
    if request.method == 'POST':
        org.name = request.POST['name']
        org.member_limit = request.POST['member_limit']

        try:
            org.mutifeature_enable =True if request.POST['mutifeature_enable']  == 'on' else False
        except:
            pass

        org.serial_key = request.POST['serial_key']
        org.address = request.POST['address']
        org.expire_on = request.POST['expire_on']
        org.new_serial_key = request.POST['new_serial_key']
        org.activate = True if request.POST['activate'] == 'on' else False
        org.save()

        messages.success(request, "Succesfully Update Organizaton")
        
        return HttpResponseRedirect(reverse('superadmin:editOrg', args=[org.id]))
    return render(request, 'super_admin/editOrg.html', dist)

class addUser(View):
    template_name = 'super_admin/addUser.html'

    def get(self, request, *args, **kwagrs):
        org = Organization.objects.all()
        form = SchooladminForm()
        dist = {
            'org':org,
            'form':form
        }
        return render(request, self.template_name, dist)
    
    def post(self, request, *args, **kwargs):
        form = SchooladminForm(request.POST or None)
        if form.is_valid():
            cd = form.cleaned_data
            first_name = cd['first_name']
            last_name = cd['last_name']
            email = cd['email']
            password = cd['password']
            number = cd['number']
            org = cd['org']
            TypeOne = CustomUser.objects.create_user(first_name=first_name, last_name = last_name, email = email, username = email, password=password)
            Schooladmin.objects.create(admin = TypeOne, org = org, number = number)
            TypeOne.user_type = "2"
            TypeOne.save()
            messages.success(request, "Succesfully Added User")
            return HttpResponseRedirect(reverse('superadmin:addUser'))
        else:
            messages.error(request, "Something went Wrong")
            return render(request, self.template_name, {'form':form})

def deleteUser(request, id):
    org = Organization.objects.get(id = id)
    org.delete()
    messages.success(request, "Successfully Delete User")
    return HttpResponseRedirect(reverse('superadmin:dashboard'))

def editUser(request, id):
    form = OrgForm()
    org = Organization.objects.get(id =id)
    form.fields['name'].initial = org.name
    form.fields['serial_key'].initial = org.serial_key
    form.fields['expire_on'].initial = org.expire_on
    form.fields['new_serial_key'].initial = org.new_serial_key
    form.fields['activate'].initial = org.activate

    dist = {
        'form':form,
        'org':org
    }
    if request.method == 'POST':
        org.name = request.POST['name']
        org.serial_key = request.POST['serial_key']
        org.expire_on = request.POST['expire_on']
        org.new_serial_key = request.POST['new_serial_key']
        org.activate = True if request.POST['activate'] == 'on' else False
        org.save()
        messages.success(request, "Succesfully Update Organizaton")
        return HttpResponseRedirect(reverse('superadmin:editOrg', args=[org.id]))
    return render(request, 'super_admin/editOrg.html', dist)