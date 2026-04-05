import datetime
from management.models import Organization, CustomUser
from django.db import models

from datetime import datetime as dt
class Classification(models.Model):
    id = models.AutoField(primary_key=1)
    org = models.ForeignKey(Organization, on_delete=models.CASCADE, null = True)
    name = models.CharField(max_length=200)
    objects = models.Manager()

    def __str__(self):
        return self.name

class member(models.Model):
    classification = models.ForeignKey(Classification, on_delete=models.DO_NOTHING, related_name='member_type', null=True, blank = True)
    id = models.AutoField(primary_key = 1)
    device_id = models.IntegerField(null=True)
    org = models.ForeignKey(Organization, on_delete=models.CASCADE, null = True)
    name = models.CharField(max_length=200)
    privilege = models.IntegerField(default=1)
    card = models.CharField(max_length=14, unique= False)
    gender = models.CharField(max_length=200, choices=(
        ('Male', 'Male'),
        ('Female', "Female"),
    ))
    address = models.CharField(max_length=200, null = True)
    email = models.EmailField(null=True, unique=True)
    phone = models.BigIntegerField(null=True)
    created_date = models.DateTimeField(auto_now_add=True)
    updated_date = models.DateTimeField(auto_now=True)
    sms_enabled = models.BooleanField(default= False)
    black_list = models.BooleanField(default=False)
    salary_per_hour = models.IntegerField(default=15)
    objects = models.Manager()
    first_date = None
    last_date = None
    ft = None
    tt = None
    date = None
    def __str__(self):
        return f"{self.name} - {self.card} - {self.phone}"

    def first_daily_time(self):
        if self.date == None:
            all_today_data_of_member = self.member_record.filter(scanned_time__date = datetime.date.today())
        else:
            all_today_data_of_member = self.member_record.filter(scanned_time__date = self.date)
        for d in all_today_data_of_member:
            self.first_date = d.scanned_time.time()
            self.ft = d.scanned_time
            break
        return self.first_date
    def last_daily_time(self):
        if self.date == None:
            all_todays_data_of_member = self.member_record.filter(scanned_time__date = datetime.date.today())
        else:
            all_todays_data_of_member = self.member_record.filter(scanned_time__date = self.date)
        if(len(all_todays_data_of_member) <= 1 or len(all_todays_data_of_member)%2 == 1):
            self.last_date = None
        else:
            for d in all_todays_data_of_member:
                print(d)
                self.last_date = d.scanned_time.time()
                self.tt = d.scanned_time
            return self.last_date
        
    def parse_time(self, time_string):
        try:
            # Try parsing with microseconds
            return dt.strptime(time_string, '%H:%M:%S.%f')
        except ValueError:
            # Fallback to parsing without microseconds
            return dt.strptime(time_string, '%H:%M:%S')

    def hour_inside(self):
        aa = self.first_daily_time()
        try:
            bb = self.last_daily_time()
        except:
            bb = None  # Make sure bb is set to None if the exception is caught

        time_interval = None
        if aa:
            time_1 = self.parse_time(str(aa))
        if bb:
            time_2 = self.parse_time(str(bb))
            time_interval = time_2 - time_1
        return time_interval
    
    def alldataofdaily(self):
        if self.date == None:
            all_todays_data_of_member = self.member_record.filter(scanned_time__date = datetime.date.today())
        else:
            all_todays_data_of_member = self.member_record.filter(scanned_time__date = self.date)
        return all_todays_data_of_member
    


class Staff(models.Model):
    id = models.AutoField(primary_key = True)
    admin = models.OneToOneField(CustomUser, on_delete=models.CASCADE)
    org = models.ForeignKey(Organization, on_delete=models.CASCADE)
    member = models.OneToOneField(member, related_name="staff_member", null = True, blank=True, on_delete=models.CASCADE)
    number = models.BigIntegerField(null=True)
    objects = models.Manager()
    def __str__(self):
        return self.admin.email
    
    
class AttendingClassification(models.Model):
    id = models.AutoField(primary_key = True)
    staff = models.ForeignKey(CustomUser, related_name='staff_attending' ,on_delete=models.CASCADE)
    classification = models.ForeignKey(Classification, related_name='staff_classificaton' ,on_delete=models.CASCADE)
    objects = models.Manager()
    def __str__(self):
        return self.staff.email
    

class PaySlip(models.Model):
    member = models.ForeignKey(member, related_name="member_pay_slip", on_delete=models.CASCADE)
    from_date = models.DateField()
    to_date = models.DateField()
    month = models.CharField(max_length=200)
    salary = models.DecimalField(decimal_places=3, max_digits=30)
    tax = models.DecimalField(decimal_places=3, max_digits=30)
    total = models.DecimalField(decimal_places= 3, max_digits=30)
    created_at = models.DateTimeField(auto_now=True)
    updated_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return super().__str__()

class Device(models.Model):
    org = models.ForeignKey(Organization, on_delete=models.CASCADE, null = True)
    name = models.CharField(max_length=200)
    ip_address = models.CharField(max_length=30)
    port_no = models.IntegerField()

    def __str__(self):
        return f"{self.org}- {self.name}"


class AttendanceRecord(models.Model):
    mem = models.ForeignKey(member, related_name = "member_record", on_delete=models.CASCADE)
    org = models.ForeignKey(Organization, on_delete=models.CASCADE, null = True)
    scanned_time = models.DateTimeField()
    got_time = datetime.datetime.today()

    def __str__(self):
        return f"{self.mem.name} scanned on {self.scanned_time}"
    def first_daily_time(self):
        # return f"{self.mem.name, self.mem.card}"
        today_data = AttendanceRecord.objects.filter(scanned_time__date = self.got_time).filter(mem=self.mem)
        first_date = None
        for d in today_data:
            first_date = d.scanned_time.time()
            break
        return first_date
    def last_daily_time(self):
        today_data = AttendanceRecord.objects.filter(scanned_time__date = self.got_time).filter(mem=self.mem)
        last_date = None
        if(len(today_data) <= 1):
            last_date = None
        else:
            for d in today_data:
                print(d)
                last_date = d.scanned_time.time()
            return last_date
        






