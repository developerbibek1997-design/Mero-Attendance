from django.views import View
from handle.models import AttendingClassification, member
from django.shortcuts import render, redirect
from django.views.generic.list import ListView
from handle.models import AttendanceRecord
import datetime
from datetime import datetime as dt
from handle.models import Classification, PaySlip
from handle.models import Device
from management.models import CustomUser, LeaveReport
from management.models import Organization
from handle.forms import PaySlipForm
from django.http import HttpResponseRedirect, JsonResponse
from django.urls import reverse
from django.contrib import messages
from .forms import OrgFormSchool
from handle.models import Staff, member, Classification
from django.shortcuts import render, get_object_or_404
from management.models import Holiday, Occasion
from datetime import timedelta, date
from django.conf import settings
from django.core.mail import send_mail, BadHeaderError

class AllRecord(ListView):
    model = AttendanceRecord
    paginate_by = 100
    template_name = 'admin/allReport.html'

    def get_context_data(self, request, **kwargs):
        today_date = datetime.date.today()
        context = super().get_context_data(**kwargs)
        context["daily"] = self.model.objects.filter(scanned_time__date = today_date)
        context['member'] = member.objects.all()
        auser = request.user
        org =  auser.schooladmin.org
        context['org'] = org
        return context



def getMember(request):
    qid = request.GET.get('questionid', None)




def orgDetail(request):
    user = request.user
    org = user.schooladmin.org
    form = OrgFormSchool(instance=org)
    holiday = Holiday.objects.filter(org = org)
    print(holiday)
    existing_holidays = [holiday.holiday for holiday in holiday]
    occasion = Occasion.objects.filter(org =org)
    dist = {
        'form':form,
        'org':org,
        'holiday':existing_holidays,
        'occasions':occasion

    }
    if request.method == 'POST':
        org.name = request.POST['name']
        try:
            org.image = request.FILES['image'] or None
        except:
            pass
        org.serial_key = request.POST['serial_key']
        org.address = request.POST['address']
        org.save()
       
        messages.success(request, "Succesfully Update Organizaton")
      

        return HttpResponseRedirect(reverse('schooladmin:orgDetail'))
   

    return render(request, "admin/orgDetail.html", dist)



class Dashboard(View):
    template_name = 'admin/Adashboard.html'

    def get(self, request, *args, **kwargs):
        user = request.user
        org = user.schooladmin.org
        all_records = AttendanceRecord.objects.filter(org = org).order_by('mem', 'scanned_time')
        # for mem in all_records.values_list('mem', flat=True).distinct():
        #     member_records = all_records.filter(mem=mem)
        #     previous_record = None
        #     for record in member_records:
        #         if previous_record and (record.scanned_time - previous_record.scanned_time).total_seconds() <= 120:
        #             record.delete()
        #         else:
        #             previous_record = record
        member.date = datetime.date.today()
        total_member = member.objects.filter(org=org).count()
        tm = member.objects.filter(org=org)
        leave = LeaveReport.objects.filter(org = org).count
        absent = 0
        present = 0
        for i in tm:
            if i.first_daily_time() == None:
                absent +=1
            else:
                present +=1
        dist = {
            'org':org,
            'tm':total_member,
            'absent':absent,
            'present': present,
            'leave':leave,
            'unseen_leave':LeaveReport.objects.filter(seen = False).filter(org=org).count(),
            'devices':Device.objects.filter(org=org)
        }
        return render(request, self.template_name, dist)
       

class DailyReport(ListView):

    template_name = 'admin/dailyReport.html'

    def get(self, request, *args, **kwargs):
        user = request.user
        org = user.schooladmin.org
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
        org = user.schooladmin.org
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



class PresentToday(ListView):

    template_name = 'admin/presentToday.html'

    def get(self, request, *args, **kwargs):
        user = request.user
        org = user.schooladmin.org
        tm = member.objects.filter(org=org)
        today_attendance_data = AttendanceRecord.objects.filter(org = org).filter(scanned_time__date = datetime.date.today())
        print(today_attendance_data)
        classifi = Classification.objects.filter(org=org)
        today_date = datetime.date.today()
        member_data = []
        for j in tm:
            for i in today_attendance_data:
                if i.mem == j:
                    member_data.append(j)
                    break
        print(member_data)
        dist = {
            'date': today_date,
            'tm':member_data,
            'org':org,
            'thisone':'All',
            'clas':classifi
        }
        return render(request, self.template_name, dist)
    def post(self, request, *args, **kwargs):
        today_date = datetime.date.today()
        user = request.user
        org = user.schooladmin.org
        name = request.POST['filter']
        print(name)
         
        if request.POST['date']:
            date = request.POST['date']
        else:
            date = today_date

        classifi = Classification.objects.filter(org=org)
        today_attendance_data = AttendanceRecord.objects.filter(scanned_time__date = date)
        member_data = []
        print(today_attendance_data)
        if not name == 'All':
            if not date: 
                date = today_date
                member.date = today_date
              
            else:
                member.date = date
            tm = member.objects.filter(org = org).filter(classification=name)
            for j in tm:
                for i in today_attendance_data:
                    if i.mem == j:
                        member_data.append(j)
                        break
            print(member_data)
            sn = Classification.objects.get(id = name).name
        else:
            if not date: 
                date = today_date
                member.date = today_date
            else:
                member.date = date
            sn = 'All'
            tm = member.objects.filter(org = org)
            for j in tm:
                for i in today_attendance_data:
                    if i.mem == j:
                        member_data.append(j)
                        break
            print(member_data)
        dist = {
            'date': date,
            'tm':member_data,
            'thisone':sn,
            'org':org,
            'clas':classifi
        }
        return render(request, self.template_name, dist)




class AbsentToday(ListView):

    template_name = 'admin/absentToday.html'

    def get(self, request, *args, **kwargs):
        user = request.user
        org = user.schooladmin.org
        tm = member.objects.filter(org=org)
        today_attendance_data = AttendanceRecord.objects.filter(org = org).filter(scanned_time__date = datetime.date.today())
        print(today_attendance_data)
        classifi = Classification.objects.filter(org=org)
        today_date = datetime.date.today()
        member_data = []
        for j in tm:
            for i in today_attendance_data:
                if i.mem == j:
                    member_data.append(j)
                    break
        new = list(set(member_data).symmetric_difference(set(tm)))
        print(new)
        dist = {
            'date': today_date,
            'tm':new,
            'org':org,
            'thisone':'All',
            'clas':classifi
        }
        return render(request, self.template_name, dist)
    def post(self, request, *args, **kwargs):
        today_date = datetime.date.today()
        user = request.user
        org = user.schooladmin.org
        name = request.POST['filter']
        print(name)
        if request.POST['date']:
            date = request.POST['date']
        else:
            date = today_date
        classifi = Classification.objects.filter(org=org)
        today_attendance_data = AttendanceRecord.objects.filter(scanned_time__date = date)
        member_data = []
        print(today_attendance_data)
        if not name == 'All':
            if not date: 
                date = today_date
                member.date = today_date
              
            else:
                member.date = date
            tm = member.objects.filter(org = org).filter(classification=name)
            for j in tm:
                for i in today_attendance_data:
                    if i.mem == j:
                        member_data.append(j)
                        break
            print(member_data)
            sn = Classification.objects.get(id = name).name
        else:
            if not date: 
                date = today_date
                member.date = today_date
              
            else:
                member.date = date
            tm = member.objects.filter(org = org)
            for j in tm:
                for i in today_attendance_data:
                    if i.mem == j:
                        member_data.append(j)
                        break
            print(member_data)
            sn = 'All'
        new = list(set(member_data).symmetric_difference(set(tm)))
        dist = {
            'date': date,
            'tm':new,
            'thisone':sn,
            'org':org,
            'clas':classifi
        }
        return render(request, self.template_name, dist)






def parse_time(time_string):
    try:
        # Try parsing with microseconds
        return dt.strptime(time_string, '%H:%M:%S.%f')
    except ValueError:
        # Fallback to parsing without microseconds
        return dt.strptime(time_string.split('.')[0], '%H:%M:%S')
    
class GapReport(View):
    template_name = "admin/gapReport.html"
    def get(self, request, *args, **kwargs):
        user = request.user
        org = user.schooladmin.org
        tm = None
        today_date = datetime.date.today()
        clas = Classification.objects.filter(org=org)
        dist = {
            'date': today_date,
            'tm':tm,
            'org':org,
            'thisone':'All',
            'clas':clas
        }
        return render(request, self.template_name, dist)
    
    def post(self, request, *args, **kwargs):
        first_date = request.POST['first_date']
        last_date = request.POST['last_date']
        start_date = datetime.datetime.strptime(first_date, "%Y-%m-%d").date()
        end_date = datetime.datetime.strptime(last_date, "%Y-%m-%d").date()
        delta = datetime.timedelta(days=1)
        user = request.user
        org = user.schooladmin.org
        clas = Classification.objects.filter(org=org)
        name = request.POST['classification']
        later_date = start_date
        print(name)
        if name == 'All':
            mem = member.objects.filter(org = org)
            th = 'All' 
        else:
            mem = member.objects.filter(org = org).filter(classification=name)
            th = Classification.objects.get(id = name).name
        member_data = []
        clas = Classification.objects.filter(org=org)
        holiday = Holiday.objects.filter(org = org)
        occasion = Occasion.objects.filter(org = org)
        for i in mem:
            print(i)
            while start_date <= end_date:
                print(start_date)
                i.date = start_date
                aa = i.first_daily_time()
                try:
                    bb = i.last_daily_time()
                except:
                    bb = None
                time_interval = None

                print(aa)
                print(bb)
                
                if not aa is None:
                    time_1 = parse_time(str(aa))
                if bb:
                    time_2 = parse_time(str(bb))
                    time_interval = time_2 - time_1
                holi = False
                oca = ""
              
                for p in holiday:
                    if p.holiday == start_date.strftime("%A"):
                        holi = True
                    else:holi = False
                
                oca = None

                for n in occasion:
                    if not n.end_date:
                        # Single day occasion
                        if n.date == start_date:
                            oca = n.name
                    else:
                        # Multi-day occasion
                        current_date = n.date
                        while current_date <= n.end_date:
                            if current_date == start_date:
                                oca = n.name
                                break  # Exit the loop once the date is found
                            current_date += datetime.timedelta(days=1)

                member_data.append([start_date, i.name, i.first_daily_time(), i.last_daily_time(), time_interval, holi, oca])
                i.first_date = None
                i.last_date = None
                i.ft = None
                i.tt = None
                i.date = None
              
                start_date += delta
            start_date = later_date
      
        dist = {
            'first_date': first_date,
            'last_date':last_date,
            'tm':member_data,
            'thisone':th,
            'org':org,
            'clas':clas
        }
        return render(request, self.template_name, dist)


class MemberGapReport(View):
    template_name = "admin/memberRecord.html"
    def get(self, request, *args, **kwargs):
        id = self.kwargs['id']
        user = request.user
        org = user.schooladmin.org
        memb = member.objects.get(id = id)
        today_date = datetime.date.today()
        memb.date = today_date
        member_data = []
        # aa = memb.first_daily_time()
        # bb = memb.last_daily_time()
        time_interval = None
        
        aa = memb.first_daily_time()
        try:
            bb = memb.last_daily_time()
        except:
            bb = None
     
        if not aa is None:
            time_1 = parse_time(str(aa))
        if bb:
            time_2 = parse_time(str(bb))
            time_interval = time_2 - time_1
      

        
        member_data.append([today_date, memb.name, memb.first_daily_time(), memb.last_daily_time(), time_interval])
        
        print(member_data)

        dist = {
            'date': today_date,
            'tm':member_data,
            'org':org,
            'thisone':memb.name,
            
        }
        return render(request, self.template_name, dist)
    
    def post(self, request, *args, **kwargs):
        id = self.kwargs['id']
        first_date = request.POST['first_date']
        last_date = request.POST['last_date']
        start_date = datetime.datetime.strptime(first_date, "%Y-%m-%d").date()
        end_date = datetime.datetime.strptime(last_date, "%Y-%m-%d").date()
        delta = datetime.timedelta(days=1)
        user = request.user
        org = user.schooladmin.org
        mem = member.objects.get(id = id)
        member_data = []
        holiday = Holiday.objects.filter(org = org)
        occasion = Occasion.objects.filter(org = org)
        total_days = 0
        total_absent_days = 0
        total_present_days = 0
        total_holidays = 0
        total_occasion_holidays = 0
        total_leave_days = 0
        total_leave = LeaveReport.objects.filter(member = mem).filter(approved = True)
        leave_date = []

        for leave_report in total_leave:
            total_leave_days += leave_report.total_leave_days()
                
        for i in total_leave:
            if not i.gap_end:
                leave_date.append(i.gap_start)
            else:
                current_date = i.gap_start
                while current_date <= i.gap_end:
                    leave_date.append(current_date)
                    current_date += timedelta(days=1)


        print("The Data is the place")
        print(leave_date)

        while start_date <= end_date:
            total_days += 1
            # print(start_date)
            i = mem
            i.date = start_date
            aa = i.first_daily_time()
            bb = i.last_daily_time()
            time_interval = None
            if aa:
                time_1 = parse_time(str(aa))
            if bb:
                time_2 = parse_time(str(bb))
                time_interval = time_2 - time_1

            holi = False
            oca = ""

            
            for p in holiday:
                if p.holiday == start_date.strftime("%A"):
                    total_holidays += 1
                    holi = True
                else:holi = False
            
            oca = None
            leave_status = None

            for n in occasion:
                if not n.end_date:
                    # Single day occasion
                    if n.date == start_date:
                        oca = n.name
                        total_occasion_holidays += 1
                        break
                else:
                    # Multi-day occasion
                    current_date = n.date
                    while current_date <= n.end_date:
                        if current_date == start_date:
                            oca = n.name
                            total_occasion_holidays += 1
                            break  # Exit the loop once the date is found
                        current_date += datetime.timedelta(days=1)

            if aa:
                total_present_days += 1
            else:
                if not holi or oca:
                    total_absent_days += 1

            if start_date in leave_date:
                leave_status = 'On Leave'

            member_data.append([start_date, i.name, i.first_daily_time(), i.last_daily_time(), time_interval, holi, oca, leave_status])
            i.first_date = None
            i.last_date = None
            i.ft = None
            i.tt = None
            i.date = None
              
            start_date += delta
        # print(member_data)
       
       
        # print(name)
        dist = {
            'first_date': first_date,
            'last_date':last_date,
            'tm':member_data,
            'org':org,
            'thisone':mem.name,
            'total_days': total_days,
            'total_absent_days': total_absent_days,
            'total_present_days': total_present_days,
            'total_holidays': total_holidays,
            'total_occasion_holidays': total_occasion_holidays,
            'total_leave_days':total_leave_days
        }
        return render(request, self.template_name, dist)

class salaryReport(View):
    template_name = "admin/salaryReport.html"
    def get(self, request, *args, **kwargs):
        id = self.kwargs['id']
        user = request.user
        org = user.schooladmin.org
        memb = member.objects.get(id = id)
        today_date = datetime.date.today()
        memb.date = today_date
        member_data = []
        aa = memb.first_daily_time()
        bb = memb.last_daily_time()
        time_interval = None
        time_interval_cost = None
        total_hour = None
        total_cost = 0
        if aa:
            time_1 = parse_time(str(aa))
        if bb:
            time_2 = parse_time(str(bb))
            time_interval = time_2 - time_1
            time_interval_s = time_interval.total_seconds()
            tis = time_interval_s/60
            tim= tis/60
            times = float("{:.2f}".format(tim))

            time_interval_cost = times * memb.salary_per_hour
            total_cost+=time_interval_cost
        member_data.append([today_date, memb.name, memb.first_daily_time(), memb.last_daily_time(), time_interval, time_interval_cost ])
        
        print(member_data)
        dist = {
            'date': today_date,
            'tm':member_data,
            'org':org,
            'thisone':memb.name,
            'total_hour':total_hour,
            'total_cost':total_cost,
            'allMember':member.objects.filter(org = org)
        }
        return render(request, self.template_name, dist)
    def post(self, request, *args, **kwargs):
        id = request.POST['member']
        first_date = request.POST['first_date']
        last_date = request.POST['last_date']
        start_date = datetime.datetime.strptime(first_date, "%Y-%m-%d").date()
        end_date = datetime.datetime.strptime(last_date, "%Y-%m-%d").date()
        delta = datetime.timedelta(days=1)
        user = request.user
        org = user.schooladmin.org
        mem = member.objects.get(id = id)
        member_data = []
        total_hour_in_sec = 0.0
        total_cost = 0
        while start_date <= end_date:
            # print(start_date)
            time_interval = None
            total_hour = None
            time_interval_cost = 0
            i = mem
            i.date = start_date
            aa = i.first_daily_time()
            bb = i.last_daily_time()
           
            if aa:
                time_1 = parse_time(str(aa))
            if bb:
                time_2 = parse_time(str(bb))
                time_interval = time_2 - time_1
                print(time_interval)
                
                time_interval_s = time_interval.total_seconds()
                tis = time_interval_s/60
                tim= tis/60
                print(tim)
                times = float("{:.2f}".format(tim))
                total_hour_in_sec += tim
                time_interval_cost = tim * mem.salary_per_hour
                total_cost+=round(time_interval_cost)
            member_data.append([start_date, i.name, i.first_daily_time(), i.last_daily_time(), time_interval,round(time_interval_cost)])
            i.first_date = None
            i.last_date = None
            i.ft = None
            i.tt = None
            i.date = None
            start_date += delta
        total_hour = int(total_hour_in_sec)
        dist = {
            'first_date': first_date,
            'last_date':last_date,
            'tm':member_data,
            'org':org,
            'allMember':member.objects.filter(org = org),
            'thisone':mem.name,
            'total_hour':total_hour,
            'total_cost':total_cost,
        }
        return render(request, self.template_name, dist)


class salaryReportAll(View):
    template_name = 'admin/salaryReportAll.html'

    def get(self, request, *args, **kwargs):
        auser = request.user
        if auser.user_type == "2":
            org =  auser.schooladmin.org
        elif auser.user_type == "3":
            org =  auser.staff.org
        else:
            org = None
  
        memb = member.objects.filter(org=org).order_by('-id')

        dist = {
            'mem':memb,
            'org':org,
            'clas':Classification.objects.filter(org=org),
            'thisone':'All'
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
            'org':org,
            'thisone': th
        }
        return render(request, self.template_name, dist)


class leaveReportView(View):
    template_name = "admin/leaveReportView.html"
    def get(self, request, *args, **kwagrs):
        user = request.user
        org = user.schooladmin.org
        leave = LeaveReport.objects.filter(org = org).order_by('-gap_start')
        dist ={
            'org':org,
            'leave':leave
        }
        return render(request, self.template_name, dist)
    


def leaveStatus(request, id, status):
    leve = LeaveReport.objects.get(id = id)
    if status == "accept":
        leve.approved = True
        leve.seen = True
        leve.save()
      
        subject = 'Leave Approved'
        if not leve.gap_end:
            message = leve.org.name + ": Your leave for " + str(leve.gap_start) + " has been approved."
        else:
            message = leve.org.name + ": Your leave for " + str(leve.gap_start) + "to " + str(leve.gap_end) +" has been approved."
        from_email = settings.EMAIL_HOST_USER  # Sender's email address
        recipient_list = [leve.member.email,]  # List of recipients' email addresses
        
        try:
            send_mail(subject, message, from_email, recipient_list)
            messages.success(request, "Successfully approved the leave. Member has received the mail")

        except:
            messages.error(request, "Failed sending member approved email. Please make sure member email is verified email.") 
  

    if status == "reject":
        leve.rejected = True
        leve.seen = True
        leve.save()
        # messages.success(request, "Successfully rejected the leave")
        subject = 'Leave Rejected'
        if not leve.gap_end:
            message = leve.org.name + ": Your leave for " + str(leve.gap_start) + " has been rejected."
        else:
            message = leve.org.name + ": Your leave for " + str(leve.gap_start) + "to " + leve.gap_end +" has been rejected."
        from_email = settings.EMAIL_HOST_USER  # Sender's email address
        recipient_list = [leve.member.email,]  # List of recipients' email addresses
        try:
            send_mail(subject, message, from_email, recipient_list)
            messages.success(request, "Successfully rejected the leave. Member has received the mail")
          

        except:
            messages.error(request, "Failed sending member rejected email. Please make sure member email is verified email.") 
  

    
    return HttpResponseRedirect(reverse('schooladmin:dashboard'))

   
def playSlipView(request):
    auser = request.user
    if auser.user_type == "2":
        org =  auser.schooladmin.org
    elif auser.user_type == "3":
        org =  auser.staff.org
    else:
        org = None

    memb = member.objects.filter(org=org).order_by('-id')

    dist = {
        'mem':memb,
        'org':org,
        'clas':Classification.objects.filter(org=org),
        'thisone':'All'
    }
    return render(request, "admin/payslip.html", dist)


def paySlipDetailView(request, id):
    auser = request.user
    if auser.user_type == "2":
        org =  auser.schooladmin.org
    elif auser.user_type == "3":
        org =  auser.staff.org
    else:
        org = None
    memb = member.objects.get(id=id)

    dist = {
        'mem':memb,
        'org':org,
        'clas':Classification.objects.filter(org=org),
        'thisone':'All',
        'paySlip': PaySlip.objects.filter(member__id = id).order_by('-id')
    }
    if request.method == 'POST':
        id = id
        first_date = request.POST['first_date']
        last_date = request.POST['last_date']
        start_date = datetime.datetime.strptime(first_date, "%Y-%m-%d").date()
        end_date = datetime.datetime.strptime(last_date, "%Y-%m-%d").date()
        delta = datetime.timedelta(days=1)
        user = request.user
        org = user.schooladmin.org
        mem = member.objects.get(id = id)
        member_data = []
        total_hour_in_sec = 0.0
        total_cost = 0
        while start_date <= end_date:
            # print(start_date)
            time_interval = None
            total_hour = None
            time_interval_cost = 0
            i = mem
            i.date = start_date
            aa = i.first_daily_time()
            bb = i.last_daily_time()
           
            if aa:
                time_1 = parse_time(str(aa))
            if bb:
                time_2 = parse_time(str(bb))
                time_interval = time_2 - time_1
                print(time_interval)
                
                time_interval_s = time_interval.total_seconds()
                tis = time_interval_s/60
                tim= tis/60
                print(tim)
                times = float("{:.2f}".format(tim))
                total_hour_in_sec += tim
                time_interval_cost = tim * mem.salary_per_hour
                total_cost+=round(time_interval_cost)
            member_data.append([start_date, i.name, i.first_daily_time(), i.last_daily_time(), time_interval,round(time_interval_cost)])
            i.first_date = None
            i.last_date = None
            i.ft = None
            i.tt = None
            i.date = None
            start_date += delta
        total_hour = int(total_hour_in_sec)
        form = PaySlipForm()
        form.initial['from_date'] = first_date
        form.initial['last_date'] = last_date
        first_date_obj = datetime.datetime.strptime(first_date, '%Y-%m-%d')
        first_date_objs = datetime.datetime.strptime(last_date, '%Y-%m-%d')

        month_name = first_date_obj.strftime('%B') 
        month_names = first_date_objs.strftime('%B') 

        form.initial['month'] = month_name + " - " + month_names
        form.initial['from_date'] = first_date
        form.initial['member'] = id
        form.initial['to_date'] = last_date
        form.initial['salary'] = total_cost
        tax = 10/100*total_cost
        tota = total_cost - tax
        form.initial['tax'] = round(tax,2)
        form.initial['total'] =  round(tota,2)

    
        dist = {
            'first_date': first_date,
            'last_date':last_date,
            'tm':member_data,
            'mem':memb,
            'org':org,
            'allMember':member.objects.filter(org = org),
            'thisone':mem.name,
            'total_hour':total_hour,
            'total_cost':total_cost,
            'tds':10/100*total_cost,
            'total':total_cost - 10/100*total_cost,
            'thisone':'All',
            'form':form
        }
       
        
    return render(request, "admin/generate_payslip.html", dist)


def generate(request, id):
    if request.method == 'POST':
        form = PaySlipForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Successfully saved salary data")
            return HttpResponseRedirect(reverse('schooladmin:play-slip-detail', args=(id,)))
        else:
            messages.error(request, "Failed to save salary data. Please check the form.")
    else:
        form = PaySlipForm()
        auser = request.user
        if auser.user_type == "2":
            org =  auser.schooladmin.org
        elif auser.user_type == "3":
            org =  auser.staff.org
        else:
            org = None
        memb = member.objects.get(id=id)

        dist = {
            'mem':memb,
            'form'
            'org':org,
            'clas':Classification.objects.filter(org=org),
            'thisone':'All',
            'paySlip': PaySlip.objects.filter(member__id = id).order_by('-id')
        }
        return render(request, "admin/generate_payslip.html", dist)
    
def addHoliday(request):
    org =  request.user.schooladmin.org
    if request.method == 'POST':
        days = request.POST.getlist('day')
        for i in days:
            Holiday.objects.create(holiday = i, org = org)
        print(days)
        messages.success(request,"Successfully added holiday")
    return HttpResponseRedirect(reverse('schooladmin:orgDetail'))


def updateHoliday(request):
    org = request.user.schooladmin.org
    if request.method == 'POST':
        current_holidays = Holiday.objects.filter(org=org)
        selected_days = request.POST.getlist('day')

        # Convert the selected days and current holidays to sets for easier comparison
        selected_days_set = set(selected_days)
        current_holidays_set = set(holiday.holiday for holiday in current_holidays)

        # Holidays to add
        holidays_to_add = selected_days_set - current_holidays_set
        for day in holidays_to_add:
            # Check if the holiday already exists to avoid duplicates
            if not Holiday.objects.filter(holiday=day, org=org).exists():
                Holiday.objects.create(holiday=day, org=org)
                print(f"Adding holiday: {day}")

        # Holidays to remove
        holidays_to_remove = current_holidays_set - selected_days_set
        for day in holidays_to_remove:
            holiday_to_delete = Holiday.objects.filter(holiday=day, org=org).first()
            if holiday_to_delete:
                holiday_to_delete.delete()
                print(f"Deleting holiday: {day}")

        messages.success(request, "Successfully updated holidays")
        return HttpResponseRedirect(reverse('schooladmin:orgDetail'))


def addOccasion(request):
    org = request.user.schooladmin.org

    if request.method == 'POST':
        name = request.POST['occasion']
        start_date = request.POST['ocDate']
        holiday_type = request.POST['holidayType']
        end_date = request.POST.get('ocEndDate', None)

        if holiday_type == 'gap' and end_date:
            Occasion.objects.create(org=org, date=start_date, end_date=end_date, name=name)
        else:
            Occasion.objects.create(org=org, date=start_date, name=name)

        messages.success(request, "Successfully added occasion")
        return HttpResponseRedirect(reverse('schooladmin:orgDetail'))


def staffMake(request):
   
    auser = request.user
    if auser.user_type == "2":
        org =  auser.schooladmin.org
    elif auser.user_type == "3":
        org =  auser.staff.org
    else:
        org = None
    memb = member.objects.filter(org = org)

    dist = {
        'member':memb,
        'classifications':Classification.objects.filter(org = org)
    }
    if request.method == 'POST':
        print("POSSSS")
        classification_ids = request.POST.getlist('classifications')
        memId = request.POST['member']
        memb = member.objects.get(id = memId)
        print(memId)
        print(classification_ids)
        classifications = Classification.objects.filter(id__in=classification_ids)
        TypeOne = CustomUser.objects.create_user(first_name=memb.name, last_name = memb.name, email = memb.email, username = memb.email, password=str(memb.phone))
        Staff.objects.create(member =memb, admin = TypeOne, org = org, number = memb.phone)
        TypeOne.user_type = "3"
        TypeOne.save()
       
        
      
        for classification in classifications:
            AttendingClassification.objects.create(staff=TypeOne, classification=classification)
        
        messages.success(request, "Succesfully Added User")

    
    return render(request, "admin/addStaff.html", dist)
    


def updateClass(request, id):
    mem = member.objects.get(id=id)
    staf = Staff.objects.get(admin__email=mem.email)
    current_classifications = AttendingClassification.objects.filter(staff=staf.admin)
        
    
    if request.method == 'POST':

        # Get the IDs of the classifications selected in the form
        selected_classifications = request.POST.getlist('classifications')
        
        # Get the current classifications for this staff member
        current_classifications = AttendingClassification.objects.filter(staff=staf.admin)
        
        # Extract the IDs of current classifications
        current_classification_ids = [str(classification.classification.id) for classification in current_classifications]
        
        # Determine classifications to be added
        to_add = set(selected_classifications) - set(current_classification_ids)
        # Determine classifications to be removed
        to_remove = set(current_classification_ids) - set(selected_classifications)
        
        # Add new classifications
        for classification_id in to_add:
            classification = Classification.objects.get(id=classification_id)
            AttendingClassification.objects.create(staff=staf.admin, classification=classification)
        
        # Remove classifications that were unchecked
        for classification_id in to_remove:
            AttendingClassification.objects.filter(
                staff=staf.admin,
                classification__id=classification_id
            ).delete()

        messages.success(request, "Successfully updated classes")
        
        return HttpResponseRedirect(reverse('schooladmin:updateClass', args=(mem.id,)))  # Replace with your success URL or handle response as needed
    
    # For GET requests, render the form
    clas = Classification.objects.filter(org=mem.org)

    holiday = []

    for i in current_classifications:
        holiday.append(i.classification.id)

    print(holiday)

    dist = {
        'clas': clas,
        'staf': staf,
        'cas': AttendingClassification.objects.filter(staff=staf.admin),
        'mem': mem,
        'holiday':holiday
    }
    
    return render(request, "admin/updateClass.html", dist)