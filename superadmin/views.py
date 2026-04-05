from datetime import timezone
from django.http.response import HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View
from django.contrib import messages
from django.urls import reverse
from management.models import Holiday, Occasion, Organization
from management.models import Schooladmin
from management.models import CustomUser
from .forms import OrgForm, SchooladminForm
from handle.models import AttendanceRecord, Classification, member









def activate(request, id):
    if request.method == 'POST':
        date = request.POST.get('date')
        if not date:
            messages.error(request, "Please provide a valid date.")
            return HttpResponseRedirect(reverse('superadmin:dashboard'))
        else:
            org = Organization.objects.get(id = id)
            org.activate = True
            org.expire_on = date
            org.save()
            messages.success(request, "Successfully Activated Organization")
            return HttpResponseRedirect(reverse('superadmin:dashboard'))
    else:
        messages.error(request, "Invalid request method.")
        return HttpResponseRedirect(reverse('superadmin:dashboard'))

def deactivate(request, id):
    org = Organization.objects.get(id = id)
    org.activate = False
    org.save()
    messages.success(request, "Successfully Deactivated Organization")
    return HttpResponseRedirect(reverse('superadmin:dashboard'))

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
    

class OrganizationDetail(View):
    template_name = 'super_admin/orgDetails.html'

    def get(self, request, id, *args, **kwargs):
        org_id = id
        org = get_object_or_404(Organization, id=org_id)
    
        # Get all related data
        holidays = Holiday.objects.filter(org=org)
        occasions = Occasion.objects.filter(org=org)
        members = member.objects.filter(org=org)
        classifications = Classification.objects.filter(org=org)
        
        # Counts and stats
        total_members = members.count()
        active_members = members.filter(black_list=False).count()
        blacklisted_members = members.filter(black_list=True).count()
        
        # Member classification distribution
        classification_distribution = []
        for classification in classifications:
            count = members.filter(classification=classification).count()
            if count > 0:  # Only include classifications with members
                classification_distribution.append({
                    'name': classification.name,
                    'count': count,
                    'percentage': round((count / total_members) * 100, 1) if total_members > 0 else 0
                })
        
        context = {
            'org': org,
            'holidays': holidays,
            'occasions': occasions,
            'total_members': total_members,
            'active_members': active_members,
            'blacklisted_members': blacklisted_members,
            'classification_distribution': classification_distribution,
            'members': members.order_by('-created_date')[:10],  # Recent 10 members
        }
    
        return render(request, self.template_name, context)
    

class MemberList(View):
    template_name = 'super_admin/memberList.html'

    def get(self, request, *args, **kwargs):
        mem = member.objects.all()
       
        dist = {
            'mem': mem,
            'org': Organization.objects.all()
           
        }
        return render(request, self.template_name, dist)
    
    def post(self, request, *agrs, **kwargs):
        clas = request.POST['classification']
        print('class', clas)
        try:

            ors = Organization.objects.get(id = clas)
        except:
            pass
        
        cl=Organization.objects.all()
        if clas == 'All':
            mem = member.objects.all()
            th = 'All' 
        else:
            mem = member.objects.filter(org = ors)
            th = Organization.objects.get(id = clas).name
        dist = {
            'mem':mem,
            'clas':cl,
            'thisone': th,
            'org': Organization.objects.all()
        }
        return render(request, self.template_name, dist)
    
class Settings(View):
    template_name = 'super_admin/settings.html'

    def get(self, request, *args, **kwargs):
        org = Organization.objects.all()
        dist = {
            'org': org
        }
        return render(request, self.template_name, dist)
    
    def post(self, request, *args, **kwargs):
        messages.success(request, "Settings Updated Successfully")
        return HttpResponseRedirect(reverse('superadmin:settings'))


class SearchView(View):

    template_name = 'super_admin/searchResult.html'


    def post(self, request, *args, **kwargs):
        search_query = request.POST.get('search_query', '')
        if search_query:
            org = Organization.objects.filter(name__icontains=search_query)
            user = Schooladmin.objects.filter(admin__first_name__icontains=search_query) | Schooladmin.objects.filter(admin__last_name__icontains=search_query)
            mem = member.objects.filter(name=search_query) | member.objects.filter(email__icontains=search_query)

            print(org, user, mem)
            
            dist = {
                'org': org,
                'user': user,
                'search_query': search_query, 
                'mem': mem,
            }
            return render(request, self.template_name, dist)
        else:
            messages.error(request, "Please enter a search term.")
            return HttpResponseRedirect(reverse('superadmin:dashboard'))

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
    form.fields['location_based'].initial = org.location_based
    form.fields['qr_based'].initial = org.qr_based
    form.fields['auto_checkin'].initial = org.auto_checkin

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

        try:
            org.location_based =True if request.POST['location_based']  == 'on' else False
        except:
            pass

        try:
            org.qr_based =True if request.POST['qr_based']  == 'on' else False
        except:
            pass

        try:
            org.auto_checkin =True if request.POST['auto_checkin']  == 'on' else False
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