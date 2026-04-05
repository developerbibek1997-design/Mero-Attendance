from django.db import models
from django.contrib.auth.models import AbstractUser
from django.dispatch import receiver
from django.db.models.signals import post_save


from datetime import datetime, date

# Create your models here.

class CustomUser(AbstractUser):
    user_type_data = (("1", "superadmin"), ("2", 'schooladmin'), ("3", 'staff'))
    user_type = models.CharField(default = "1", choices = user_type_data, max_length = 10)
    email = models.EmailField(unique = True)
    

class Organization(models.Model):
    id = models.AutoField(primary_key= True)
    image = models.ImageField(upload_to="image", null= True, blank=True)
    address = models.CharField(max_length=200, null= True, blank= True)
    name = models.CharField(max_length=300)
    member_limit = models.IntegerField(default=25)
    expire_on = models.DateTimeField()
    serial_key = models.CharField(max_length=100)
    new_serial_key = models.CharField(max_length=100)
    activate = models.BooleanField(default=True)
    mutifeature_enable = models.BooleanField(default=False)
    objects = models.Manager()

    def __str__(self):
        return self.name

class Holiday(models.Model):
    org = models.ForeignKey(Organization, related_name="org_holiday", on_delete=models.CASCADE)
    holiday = models.CharField(max_length=300)

    def __str__(self):
        return self.holiday
    
class Occasion(models.Model):
    name = models.CharField(max_length=200)
    org = models.ForeignKey(Organization, related_name="org_occasion", on_delete=models.CASCADE)
    date = models.DateField()
    end_date = models.DateField(null=True, blank=True)  # Optional end date for gap holidays

    def __str__(self):
        return self.org.name
    

class Superadmin(models.Model):
    id = models.AutoField(primary_key = 1)
    admin = models.OneToOneField(CustomUser, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add= True)
    updated_at = models.DateTimeField(auto_now_add=True)
    objects = models.Manager()
    def __str__(self):
        return self.admin.username


class Schooladmin(models.Model):
    id = models.AutoField(primary_key = True)
    admin = models.OneToOneField(CustomUser, on_delete=models.CASCADE)
    org = models.ForeignKey(Organization, on_delete=models.CASCADE)
    number = models.BigIntegerField(null = True)
    objects = models.Manager()
    
    def __str__(self):
        return self.admin.first_name

class ContactUs(models.Model):
    fullname = models.CharField(max_length=200)
    email = models.EmailField(null= True, blank=True)
    number = models.BigIntegerField()
    message = models.TextField(null= True, blank= True)
     
    def __str__(self) -> str:
        return self.fullname
    
class Pricing(models.Model):
    name = models.CharField(max_length=200)
    price = models.IntegerField()
    limit = models.IntegerField()
    device = models.CharField(max_length=200)
    image = models.ImageField(upload_to='devices/', null=True, blank=True)

    def __str__(self) -> str:
        return self.name


class LeaveReport(models.Model):
    member = models.ForeignKey('handle.Member', on_delete=models.CASCADE)
    org = models.ForeignKey(Organization, on_delete=models.CASCADE)
    gap_start = models.DateField(null=True, blank=True)
    gap_end = models.DateField(null=True, blank=True)
    approved = models.BooleanField(default=False)
    rejected = models.BooleanField(default=False)
    reason = models.TextField()
    seen = models.BooleanField(default=False)
    objects = models.Manager()

    def __str__(self):
        return f"{self.member} - {self.org}"
    
    def total_leave_days(self):
        if not self.gap_start:
            return 0

        if self.gap_end:
            return (self.gap_end - self.gap_start).days + 1
        else:
            # If gap_end is None, consider the leave as ongoing up to today
            return (date.today() - self.gap_start).days + 1

@receiver(post_save, sender=CustomUser)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        if instance.user_type == "1":
            Superadmin.objects.create(admin = instance)
        if instance.user_type == "2":
            Schooladmin.objects.create(admin = instance)
        # if instance.user_type == "3":
        #     Staff.objects.create(admin = instance)
     

@receiver(post_save, sender=CustomUser)
def _post_save_receiver(sender, instance, **kwargs):
    if instance.user_type == "1":
        instance.superadmin.save()
    if instance.user_type == "2":
        instance.schooladmin.save()
    if instance.user_type == "3":
        instance.staff.save()

