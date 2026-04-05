
from management.models import Organization
from .models import Classification, Device, member, AttendanceRecord
from django.contrib import messages
from django.shortcuts import redirect, render
from django.views import View
from django.http import HttpResponseRedirect
from django.urls import reverse
from .forms import ClassificationForm, DeviceForm, FormChangePassword, MemberForm
# from zk import ZK
from django.db.models import Q 

# Create your views here.
class AddMember(View):
    form_class = MemberForm
    template_name = 'handle/addMember.html'
    def get(self, request, *args, **kwargs):
        auser = request.user
        if auser.user_type == "2":
            org =  auser.schooladmin.org
        else:
            org = None
        total_member = member.objects.filter(org= org).count()
        print(total_member)
        print(org.member_limit)
        form = self.form_class()
        return render(request, self.template_name, {'form':form,'org':org,'classi':Classification.objects.filter(org = org), 'total_member': total_member})

    def post(self, request, *args, **kwargs):
        form = self.form_class(request.POST)
        auser = request.user

        print("User", auser)

        if auser.user_type == "2":
            org =  auser.schooladmin.org
            
        else:
            org = None
        
    
      
        if form.is_valid():

            new_form = form.save(commit=False)
           
            print("adding to device")
        
            # Start checking from user_count + 1
            device_id_candidate = int(member.objects.filter(org=org).count()) + 1
            
            # Keep incrementing until we find a unique device_id for the org
            while member.objects.filter(org=org, device_id=device_id_candidate).exists():
                device_id_candidate += 1
            
            new_form.device_id = device_id_candidate
            new_form.org = org
            new_form.classification = Classification.objects.get(id=request.POST['classification'])
            new_form.save()

        
            messages.success(request, "Sucessfully added Member")
            return HttpResponseRedirect(reverse('handle:addMember'))
        else:
            messages.error(request, "Failed adding Member" + form.errors.as_text())
            return HttpResponseRedirect(reverse('handle:addMember'))
    

class AddClassification(View):
    template_name = "handle/addClassification.html"
    form_class = ClassificationForm

    def get(self, request, *args, **kwargs):
        form = self.form_class()
        auser = request.user
        print("User", auser)
        if auser.user_type == "2":
            org =  auser.schooladmin.org
        else:
            org = None
        clas = Classification.objects.filter(org = org)
        return render(request, self.template_name, {'form':form,'clas':clas, 'org':org})
    
    def post(self, request, *args, **kwargs):
        form = self.form_class(request.POST)
        auser = request.user
        print("User", auser)
        if auser.user_type == "2":
            org =  auser.schooladmin.org
        else:
            org = None
        if form.is_valid():
            classi = form.save(commit=False)
            classi.org = org
            classi.save()
            messages.success(request, "Successfully added Classification")
            return HttpResponseRedirect(reverse('handle:addClassification'))
        else:
            messages.error(request, "Fail adding Classification")
            return HttpResponseRedirect(reverse('handle:addClassification'))

class AddDevice(View):
    form_class = DeviceForm
    template_name = 'handle/addDevice.html'

    def get(self, request, *args, **kwargs):
        form = self.form_class()
        auser = request.user
        org =  auser.schooladmin.org
        dist = {
            'form':form,
            'org':org
        }
        return render(request, self.template_name, dist)

    def post(self, request, *args, **kwargs):
        auser = request.user
        print("User", auser)
        if auser.user_type == "2":
            org =  auser.schooladmin.org
        else:
            org = None
        form = self.form_class(request.POST)
        if form.is_valid():
            de_f = form.save(commit=False)
            de_f.org = org
            de_f.save()
            messages.success(request,"Successfully Added Devices")
            return HttpResponseRedirect(reverse('handle:addDevice'))
        else:
            messages.error(request,"Failed Adding Devices")
            return HttpResponseRedirect(reverse('handle:addDevice'))


def editDevice(request, id):
    template_name = 'handle/editDevice.html'
    form = DeviceForm()
    devi = Device.objects.get(id = id)
    form.fields['name'].initial = devi.name
    form.fields['ip_address'].initial = devi.ip_address
    form.fields['port_no'].initial = devi.port_no

    if request.method == "POST":
        devi.name = request.POST['name']
        devi.ip_address = request.POST['ip_address']
        devi.port_no = request.POST['port_no']
        devi.save()
        messages.success(request, "Successfully Edited Device")
        return HttpResponseRedirect(reverse('handle:editDevice', args=[devi.id]))
    auser = request.user
    org =  auser.schooladmin.org
    dist = {
        'form':form,
        'devi':devi,
        'org':org
    }

    return render(request, template_name, dist)

def deleteDevice(request, id):
    devi = Device.objects.get(id = id)
    devi.delete()
    # messages.success(request, "Successfully Deleted Device")
    return HttpResponseRedirect(reverse('schooladmin:dashboard'))

def memberEdit(request, id):
    mem = member.objects.get(id = id)
    form = MemberForm()
    form.fields['name'].initial = mem.name
    # form.fields['classification'].initial = mem.classification
    form.fields['card'].initial = mem.card
    form.fields['gender'].initial = mem.gender
    form.fields['salary_per_hour'].initial = mem.salary_per_hour
    form.fields['address'].initial = mem.address
    form.fields['email'].initial = mem.email
    form.fields['phone'].initial = mem.phone
    auser = request.user
    print("User", auser)
    if auser.user_type == "2":
        org =  auser.schooladmin.org
    else:
        org = None
    dist ={
        'form':form,
        'mem':mem,
        'classi':Classification.objects.filter(org = org),
        'org':org
    }
    if request.method == 'POST':
        mem.name = request.POST['name']
        mem.classification = Classification.objects.get(id =request.POST['classification']) 
        mem.card = request.POST['card']
        mem.gender = request.POST['gender']
        mem.address = request.POST['address']
        mem.email = request.POST['email']
        mem.phone = request.POST['phone']
        mem.salary_per_hour = request.POST['salary_per_hour']
        mem.save()
        messages.success(request, "Successfully Updated " +mem.name+ " details")
        return HttpResponseRedirect(reverse('handle:memberEdit', args=[mem.id]))
    else:
        return render(request, "handle/editMember.html", dist)

def deleteMember(request, id):
    devi = member.objects.get(id = id)
    name = devi.name

    try:
        devi.delete()
        messages.success(request, "Successfully Deleted Member " +name)
    except:
        messages.success(request, "There are attendance records of the user, the system will delete your user after deleting records which can take a while!")
        
    
    return HttpResponseRedirect(reverse('handle:memberReport'))

def editClassification(request, id):
    form = ClassificationForm()
    clas = Classification.objects.get(id= id)
    form.fields['name'].initial = clas.name
    auser = request.user
    if auser.user_type == "2":
        org =  auser.schooladmin.org
    else:
        org = None

    dist = {
        'form':form,
        'org':org,
        'clas':clas
    }

    if request.method == 'POST':
        clas.name = request.POST['name']
        clas.save()
        messages.success(request, "Successfullt Updated Classification")
        return HttpResponseRedirect(reverse('handle:addClassification'))
    else:
        return render(request,"handle/editClassification.html", dist)


def deleteClassification(request, id):
    clas = Classification.objects.get(id= id)
    clas.delete()
    messages.success(request, "Successfully deleted classification")
    return HttpResponseRedirect(reverse('handle:addClassification'))



class Search(View):
    template_name = 'handle/search_result.html'
    model = member
    
    def get(self, request, *args, **kwargs):
        auser = request.user
        if auser.user_type == "2":
            org =  auser.schooladmin.org
        elif auser.user_type == "3":
            org =  auser.staff.org
        else:
            org = None
        name = request.GET['member']
        memb = member.objects.filter(Q(name__icontains=name) | Q(card=name)).filter(org=org)
        dist = {
            'object_list':memb,
            'org':org
        }
        return render(request, self.template_name, dist)

class MemberReport(View):
    template_name = 'handle/member_Report.html'

    def get(self, request, *args, **kwargs):
        auser = request.user
        if auser.user_type == "2":
            org =  auser.schooladmin.org
        else:
            org = None
  
        memb = member.objects.filter(org=org).order_by('-id')

        dist = {
            'mem':memb,
            'clas':Classification.objects.filter(org=org),
            'thisone':'All',
            'org':org
        }
        return render(request, self.template_name, dist)

    def post(self, request, *agrs, **kwargs):
        clas = request.POST['classification']
        print('class', clas)
        auser = request.user
        if auser.user_type == "2":
            org =  auser.schooladmin.org
        elif auser.user_type == "3":
            org =  auser.staff.org
      
        cl=Classification.objects.filter(org=org)
        if clas == 'All':
            mem = member.objects.filter(org = org)
            th = 'All' 
        else:
            mem = member.objects.filter(org = org).filter(classification=clas)
            th = Classification.objects.get(id = clas).name
        dist = {
            'mem':mem,
            'clas':cl,
            'thisone': th,
            'org':org
        }
        return render(request, self.template_name, dist)
    
from django.contrib.auth import update_session_auth_hash

def changePassword(request):
    if request.method == 'POST':
        form = FormChangePassword(request.user, request.POST)
        if form.is_valid():
            user = form.save()
            update_session_auth_hash(request, user)  # Important!
            messages.success(request, 'Your password was successfully updated!')
            return redirect('handle:changePassword')
        else:
            messages.error(request, 'Please correct the error below.')
    else:
        form = FormChangePassword(request.user)
    return render(request, 'handle/changePassword.html', {
        'form': form,
    })
