from datetime import timezone
import datetime
from django.http.response import HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View
from django.contrib import messages
from django.urls import reverse
from management.models import Holiday, Occasion, Organization
from management.models import Schooladmin
from management.models import CustomUser
from school import settings
from .forms import OrgForm, SchooladminForm
from handle.models import AttendanceRecord, Classification, Course, Device, Staff, member

from django.core.mail import send_mail


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

class Dashboard(View):
    template_name = 'super_admin/SAdashboard.html'

    def get(self, request, *args, **kwargs):
        org = Organization.objects.all()
        org_count = org.count()
        user_count = Schooladmin.objects.all().count()
        
        # Fetching both weekly and occasion holidays for the dashboard
        recent_holidays = Holiday.objects.all().select_related('org').order_by('-id')[:5] 
        recent_occasions = Occasion.objects.all().select_related('org').order_by('-date')[:5]
        
        dist = {
            'org': org,
            'org_count': org_count,
            'user_count': user_count,
            'recent_holidays': recent_holidays,
            'recent_occasions': recent_occasions,
        }
        return render(request, self.template_name, dist)

class OrganizationDetail(View):
    template_name = 'super_admin/orgDetails.html'

    def get(self, request, id, *args, **kwargs):
        print("fck me ")
        org = get_object_or_404(Organization, id=id)
        
        # 1. Fetch Members & Classifications
        members = member.objects.filter(org=org).order_by('-created_date')
        classifications = Classification.objects.filter(org=org)
        
        # Generate Classification Distribution for the Chart
        classification_distribution = []
        for cls in classifications:
            count = members.filter(classification=cls).count()
            if count > 0:
                classification_distribution.append({
                    'name': cls.name,
                    'count': count
                })

        # 2. Fetch Infrastructure & Staff
        devices = Device.objects.filter(org=org)
        # Fetch the actual Org Admins created by Superadmin
        school_admins = Schooladmin.objects.filter(org=org).select_related('admin')
        # Fetch standard staff if any exist
        staff_members = Staff.objects.filter(org=org).select_related('admin')
        
        # 3. Generate Top Stats
        total_members = members.count()
        active_members = members.filter(black_list=False).count()
        total_attendance = AttendanceRecord.objects.filter(org=org).count()
        
        # Connected Year (Fallback to current year if no members)
        first_member = members.order_by('created_date').first()
        connected_year = first_member.created_date.year if first_member else datetime.date.today().year

        # 4. Fetch Holidays
        weekly_holidays = Holiday.objects.filter(org=org)
        occasions = Occasion.objects.filter(org=org).order_by('-date')

        context = {
            'org': org,
            'members': members,
            'total_members': total_members,
            'active_members': active_members,
            'total_attendance': total_attendance,
            'classifications': classifications,
            'classification_distribution': classification_distribution, # Required for Pie Chart!
            'devices': devices,
            'school_admins': school_admins, # Passing the Org Admins
            'staff_members': staff_members, # Passing Standard Staff
            'weekly_holidays': weekly_holidays,
            'occasions': occasions,
            'connected_year': connected_year,
        }
    
        return render(request, self.template_name, context)


class GlobalHolidayView(View):
    template_name = 'super_admin/addGlobalHoliday.html'

    def get(self, request, *args, **kwargs):
        orgs = Organization.objects.filter(activate=True).order_by('name')
        
        # Fetch distinct occasions so we don't show duplicates if pushed to multiple orgs
        occasions = Occasion.objects.values('name', 'date', 'end_date').distinct().order_by('-date')[:30]
        
        return render(request, self.template_name, {
            'orgs': orgs,
            'occasions': occasions
        })

    def post(self, request, *args, **kwargs):
        org_ids = request.POST.getlist('organizations')
        action_type = request.POST.get('action_type') # 'weekly' or 'occasion'
        
        if not org_ids:
            messages.error(request, "Please select at least one organization.")
            return redirect('superadmin:globalHoliday')

        # Determine target organizations
        if 'all' in org_ids:
            target_orgs = Organization.objects.all()
        else:
            target_orgs = Organization.objects.filter(id__in=org_ids)

        # Handle Weekly Days Off
        if action_type == 'weekly':
            days = request.POST.getlist('day')
            for org in target_orgs:
                existing_days = set(Holiday.objects.filter(org=org).values_list('holiday', flat=True))
                selected_days = set(days)
                
                # Add new holidays that don't exist yet for this org
                holidays_to_add = selected_days - existing_days
                for day in holidays_to_add:
                    Holiday.objects.create(holiday=day, org=org)
                    
                # Optional: Remove unchecked days (if you want strict override)
                # holidays_to_remove = existing_days - selected_days
                # Holiday.objects.filter(org=org, holiday__in=holidays_to_remove).delete()

            messages.success(request, f"Weekly holidays successfully pushed to {target_orgs.count()} organization(s).")

        # Handle Occasion / Gap Holidays
        elif action_type == 'occasion':
            occasion_name = request.POST.get('occasion')
            start_date = request.POST.get('ocDate')
            holiday_type = request.POST.get('holidayType')
            end_date = request.POST.get('ocEndDate') if holiday_type == 'gap' else None
            
            for org in target_orgs:
                Occasion.objects.create(
                    name=occasion_name,
                    org=org,
                    date=start_date,
                    end_date=end_date if end_date else None
                )
            messages.success(request, f"Occasion '{occasion_name}' added to {target_orgs.count()} organization(s).")

        return redirect('superadmin:dashboard')

# 2. Advanced Broadcast Email View
class BroadcastNotificationView(View):
    template_name = 'super_admin/broadcastEmail.html'

    def get(self, request, *args, **kwargs):
        orgs = Organization.objects.filter(activate=True).order_by('name')
        return render(request, self.template_name, {'orgs': orgs})

    def post(self, request, *args, **kwargs):
        org_ids = request.POST.getlist('organizations')
        subject = request.POST.get('subject')
        message = request.POST.get('message')
        
        if not org_ids:
            messages.error(request, "Please select at least one organization to email.")
            return redirect('superadmin:broadcastEmail')

        if subject and message:
            # Filter admins based on selected orgs
            if 'all' in org_ids:
                admins = Schooladmin.objects.select_related('admin').all()
            else:
                admins = Schooladmin.objects.select_related('admin').filter(org_id__in=org_ids)
                
            recipient_list = [admin.admin.email for admin in admins if admin.admin.email]
            
            if not recipient_list:
                messages.warning(request, "No valid email addresses found for the selected organizations.")
                return redirect('superadmin:broadcastEmail')

            try:
                send_mail(
                    subject,
                    message,
                    settings.EMAIL_HOST_USER,
                    recipient_list,
                    fail_silently=False,
                )
                messages.success(request, f"Email sent successfully to {len(recipient_list)} admin(s).")
            except Exception as e:
                messages.error(request, f"Failed to send email: {str(e)}")
        else:
            messages.error(request, "Subject and Message are required.")
            
        return redirect('superadmin:dashboard')


    

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

    def get(self, request, *args, **kwargs):
        org = Organization.objects.all()
        form = OrgForm()
        dist = {
            'org': org,
            'form': form
        }
        return render(request, self.template_name, dist)
    
    def post(self, request, *args, **kwargs):
        # Added request.FILES to support image uploads if you add them later
        form = OrgForm(request.POST, request.FILES or None)
        if form.is_valid():
            form.save()
            messages.success(request, "Successfully Added Organization")
            return HttpResponseRedirect(reverse('superadmin:addOrg'))
        else:
            messages.error(request, "Please check the form for errors.")
            return render(request, self.template_name, {'form': form, 'org': Organization.objects.all()})


def deleteOrg(request, id):
    org = Organization.objects.get(id=id)
    org.delete()
    messages.success(request, "Successfully Deleted Organization")
    return HttpResponseRedirect(reverse('superadmin:dashboard'))


def editOrg(request, id):
    org = Organization.objects.get(id=id)
    
    if request.method == 'POST':
        # Text, Int, Date, and Choice fields
        org.name = request.POST.get('name', org.name)
        org.category = request.POST.get('category', org.category)
        org.address = request.POST.get('address', org.address)
        org.member_limit = request.POST.get('member_limit', org.member_limit)
        org.serial_key = request.POST.get('serial_key', org.serial_key)
        org.new_serial_key = request.POST.get('new_serial_key', org.new_serial_key)
        org.expire_on = request.POST.get('expire_on', org.expire_on)

        # Refactored Boolean fields (cleaner approach without try/except)
        org.activate = request.POST.get('activate') == 'on'
        org.mutifeature_enable = request.POST.get('mutifeature_enable') == 'on'
        org.location_based = request.POST.get('location_based') == 'on'
        org.qr_based = request.POST.get('qr_based') == 'on'
        org.auto_checkin = request.POST.get('auto_checkin') == 'on'
        
        # Attendance & platform booleans
        org.rfid_based = request.POST.get('rfid_based') == 'on'
        org.manual_attendance = request.POST.get('manual_attendance') == 'on'
        org.nepali_date = request.POST.get('nepali_date') == 'on'
        org.free_demo = request.POST.get('free_demo') == 'on'
        org.course_based_attendance = request.POST.get('course_based_attendance') == 'on'

        # Module feature flags
        org.feature_finance      = request.POST.get('feature_finance') == 'on'
        org.feature_billing      = request.POST.get('feature_billing') == 'on'
        org.feature_stock        = request.POST.get('feature_stock') == 'on'
        org.feature_tasks        = request.POST.get('feature_tasks') == 'on'
        org.feature_results      = request.POST.get('feature_results') == 'on'
        org.feature_hrms         = request.POST.get('feature_hrms') == 'on'
        org.feature_payroll      = request.POST.get('feature_payroll') == 'on'
        org.feature_complaints   = request.POST.get('feature_complaints') == 'on'
        org.feature_events       = request.POST.get('feature_events') == 'on'
        org.feature_branches     = request.POST.get('feature_branches') == 'on'
        org.feature_leave        = request.POST.get('feature_leave') == 'on'
        # Extended feature flags
        org.feature_study_gap      = request.POST.get('feature_study_gap') == 'on'
        org.feature_bulk_export    = request.POST.get('feature_bulk_export') == 'on'
        org.feature_notifications  = request.POST.get('feature_notifications') == 'on'
        org.feature_courses        = request.POST.get('feature_courses') == 'on'
        org.feature_student_mgmt   = request.POST.get('feature_student_mgmt') == 'on'
        org.feature_member_mgmt    = request.POST.get('feature_member_mgmt') == 'on'
        # Dependency enforcement
        if not org.feature_courses:
            org.feature_results = False
            org.feature_study_gap = False
        if not org.feature_student_mgmt:
            org.feature_billing = False

        org.save()
        messages.success(request, "Successfully Updated Organization")
        return HttpResponseRedirect(reverse('superadmin:editOrg', args=[org.id]))

    # GET request - initialize form
    form = OrgForm()
    
    # Initialize Text/Choice fields
    form.fields['name'].initial = org.name
    form.fields['category'].initial = org.category
    form.fields['address'].initial = org.address
    form.fields['member_limit'].initial = org.member_limit
    form.fields['serial_key'].initial = org.serial_key
    form.fields['new_serial_key'].initial = org.new_serial_key
    form.fields['expire_on'].initial = org.expire_on
    
    # Initialize Boolean fields
    form.fields['activate'].initial = org.activate
    form.fields['mutifeature_enable'].initial = org.mutifeature_enable
    form.fields['location_based'].initial = org.location_based
    form.fields['qr_based'].initial = org.qr_based
    form.fields['auto_checkin'].initial = org.auto_checkin
    form.fields['rfid_based'].initial = org.rfid_based
    form.fields['manual_attendance'].initial = org.manual_attendance
    form.fields['nepali_date'].initial = org.nepali_date
    form.fields['free_demo'].initial = org.free_demo
    form.fields['course_based_attendance'].initial = org.course_based_attendance
    # Feature flags
    form.fields['feature_finance'].initial    = org.feature_finance
    form.fields['feature_billing'].initial    = org.feature_billing
    form.fields['feature_stock'].initial      = org.feature_stock
    form.fields['feature_tasks'].initial      = org.feature_tasks
    form.fields['feature_results'].initial    = org.feature_results
    form.fields['feature_hrms'].initial       = org.feature_hrms
    form.fields['feature_payroll'].initial    = org.feature_payroll
    form.fields['feature_complaints'].initial = org.feature_complaints
    form.fields['feature_events'].initial     = org.feature_events
    form.fields['feature_branches'].initial   = org.feature_branches
    form.fields['feature_leave'].initial      = org.feature_leave
    form.fields['feature_study_gap'].initial      = org.feature_study_gap
    form.fields['feature_bulk_export'].initial    = org.feature_bulk_export
    form.fields['feature_notifications'].initial  = org.feature_notifications
    form.fields['feature_courses'].initial        = org.feature_courses
    form.fields['feature_student_mgmt'].initial   = org.feature_student_mgmt
    form.fields['feature_member_mgmt'].initial    = org.feature_member_mgmt

    dist = {
        'form': form,
        'org': org
    }
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

# ── Cross-Org Attendance Report ────────────────────────────────────────────────

from handle.models import AttendanceRecord as _AR

class SuperAttendanceReportView(View):
    template_name = 'super_admin/attendance_report.html'

    def get(self, request):
        orgs = Organization.objects.all().order_by('name')
        selected_org = request.GET.get('org', '')
        from_date = request.GET.get('from_date', '')
        to_date = request.GET.get('to_date', '')
        records = _AR.objects.none()
        org_obj = None
        total = 0

        if selected_org:
            try:
                org_obj = Organization.objects.get(pk=selected_org)
                records = _AR.objects.filter(org=org_obj).select_related('mem').order_by('-scanned_time')
                if from_date:
                    records = records.filter(scanned_time__date__gte=from_date)
                if to_date:
                    records = records.filter(scanned_time__date__lte=to_date)
                total = records.count()
                records = records[:1000]
            except Organization.DoesNotExist:
                pass

        return render(request, self.template_name, {
            'orgs': orgs, 'records': records, 'total_records': total,
            'selected_org': selected_org, 'org_obj': org_obj,
            'from_date': from_date, 'to_date': to_date,
        })

    def post(self, request):
        selected_org = request.POST.get('org')
        from_date = request.POST.get('from_date')
        to_date = request.POST.get('to_date')
        if request.POST.get('confirm') != 'yes':
            messages.error(request, "Check the confirmation box before deleting.")
            return redirect('superadmin:attendance_report')
        try:
            org_obj = Organization.objects.get(pk=selected_org)
            qs = _AR.objects.filter(org=org_obj)
            if from_date:
                qs = qs.filter(scanned_time__date__gte=from_date)
            if to_date:
                qs = qs.filter(scanned_time__date__lte=to_date)
            count = qs.count()
            qs.delete()
            messages.success(request, f"Deleted {count} records from {org_obj.name}.")
        except Exception as e:
            messages.error(request, str(e))
        return redirect('superadmin:attendance_report')
