from django.shortcuts import render
from django.views import View
from handle.models import AttendingClassification, Classification, member
import datetime
from django.views.generic import ListView
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from handle.models import AttendanceRecord, Organization




@csrf_exempt
def mark_present(request):
    if request.method == "POST":
        member_id = request.POST.get('member_id')
        organization_id = request.POST.get('organization_id')
        memb = member.objects.get(id=member_id)
        organization = Organization.objects.get(id=organization_id)
        
        AttendanceRecord.objects.create(
            mem=memb,
            org=organization,
            scanned_time=datetime.datetime.now()
        )
        
        return JsonResponse({"status": "success"})
    
    return JsonResponse({"status": "failed"})


def Dashboard(request):
    template_name = 'staff/Sdashboard.html'
    clas = AttendingClassification.objects.filter(staff = request.user)
    dist = {
        'clas':clas
    }
    return render(request, template_name, dist)

def attendanceView(request, id, name):
    clas = Classification.objects.get(id = id)
    mem = member.objects.filter(classification = clas, org = request.user.staff.org)
    
    # Fetch existing attendance records for today
    attendance_records = AttendanceRecord.objects.filter(
        mem__in=mem, 
        org=request.user.staff.org,
        scanned_time__date= datetime.datetime.today().date()
    ).values_list('mem_id', flat=True)
    
    # Convert QuerySet to a set for faster lookup in the template
    attended_members = set(attendance_records)
    dist = {
        'mem':mem,
        'clas':clas,
        'date': datetime.datetime.today(),
        'org':request.user.staff.org,
        'attended_members': attended_members,
    }
    return render(request, "staff/attendance.html", dist)



class memReport(ListView):

    template_name = 'staff/report.html'

    def get(self, request, *args, **kwargs):
        user = request.user
        org = user.staff.org
        tm = member.objects.filter(org=org)
        classifi = Classification.objects.filter(org=org)
        today_date = datetime.date.today()
       
        dist = {
            'date': today_date,
            'tm':tm,
            'org':org,
            'thisone':'All',
            'clas':classifi
        }
        return render(request, self.template_name, dist)
    def post(self, request, *args, **kwargs):
        today_date = datetime.date.today()
        user = request.user
        org = user.staff.org
        name = request.POST['filter']
        print(name)
        date = request.POST['date']
        classifi = Classification.objects.filter(org=org)
        if not name == 'All':
            if not date: 
                date = today_date
                member.date = today_date
            else:
                member.date = date
            tm = member.objects.filter(org = org).filter(classification=name)
            sn = Classification.objects.get(id = name).name
        else:
            if not date: 
                date = today_date
                member.date = today_date
            else:
                member.date = date
            tm = member.objects.filter(org = org)
            sn = 'All'
        dist = {
            'date': date,
            'tm':tm,
            'thisone':sn,
            'org':org,
            'clas':classifi
        }
        return render(request, self.template_name, dist)
