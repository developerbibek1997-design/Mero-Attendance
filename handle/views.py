
import csv
from datetime import timedelta

from management.models import CustomUser, Organization
from .models import (
    AttendanceRecord,
    Branch,
    Classification,
    Course,
    Device,
    FinancialTransaction,
    Section,
    Staff,
    StockCategory,
    StockItem,
    StockMovement,
    TransactionCategory,
    member,
)
from django.contrib import messages
from django.shortcuts import redirect, render
from django.views import View
from django.http import HttpResponse, HttpResponseRedirect, JsonResponse
from django.urls import reverse
from django.core.mail import send_mail
from django.conf import settings
from django.utils import timezone
from .forms import (
    BranchForm,
    ClassificationForm,
    CourseForm,
    DeviceForm,
    FinancialTransactionForm,
    FormChangePassword,
    MemberForm,
    SectionForm,
    StockCategoryForm,
    StockItemForm,
    StockMovementForm,
    TransactionCategoryForm,
)
# from zk import ZK
from django.db.models import Q, Sum

# Helper function to send the welcome email
def send_staff_welcome_email(user_email, user_name, user_password):
    subject = 'Welcome to Mero Attendance - Your Dashboard Access'
    message = f"""Hello {user_name},

                An account has been created for you to access the Mero Attendance Dashboard.

                Here are your login credentials:
                Email: {user_email}
                Password: {user_password}

                Please log in to your dashboard here: https://meroattendance.com/login

                We recommend changing your password after your first login.

                Best Regards,
                The Mero Attendance Team
                """
    try:
        send_mail(
            subject,
            message,
            settings.DEFAULT_FROM_EMAIL, # Make sure this is set in settings.py
            [user_email],
            fail_silently=True, # Set to False during testing if you want to see SMTP errors
        )
    except Exception as e:
        print(f"Failed to send email: {e}")


def current_org_for_user(user):
    if user.user_type == "2" and hasattr(user, 'schooladmin'):
        return user.schooladmin.org
    if user.user_type == "3" and hasattr(user, 'staff'):
        return user.staff.org
    return None

class AddMember(View):
    form_class = MemberForm
    template_name = 'handle/addMember.html'

    def get(self, request, *args, **kwargs):
        auser = request.user
        
        if auser.user_type == "2":
            org = auser.schooladmin.org
        else:
            org = None
            
        total_member = member.objects.filter(org=org).count()
        form = self.form_class(org=org)
        
        dist = {
            'form': form,
            'org': org,
            'classi': Classification.objects.filter(org=org, status='active'),
            'branches': Branch.objects.filter(org=org, status='active'),
            'sections': Section.objects.filter(org=org, status='active'),
            'courses': Course.objects.filter(org=org, status='active'),
            'total_member': total_member
        }
        return render(request, self.template_name, dist)

    def post(self, request, *args, **kwargs):
        auser = request.user

        if auser.user_type == "2":
            org = auser.schooladmin.org
        else:
            org = None

        form = self.form_class(request.POST, org=org)
            
        if form.is_valid():
            new_form = form.save(commit=False)
            
            # Generate Unique Device ID
            device_id_candidate = int(member.objects.filter(org=org).count()) + 1
            while member.objects.filter(org=org, device_id=device_id_candidate).exists():
                device_id_candidate += 1
            
            new_form.device_id = device_id_candidate
            new_form.org = org
            
            # Capture tax percentage (assuming it's in your form/model)
            new_form.tax_percentage = request.POST.get('tax_percentage', 0)
            
            new_form.save()
            form.save_m2m()

            # =========================================================
            # STAFF CREATION LOGIC
            # =========================================================
            if new_form.make_staff and new_form.email and new_form.phone:
                if not CustomUser.objects.filter(email=new_form.email).exists():
                    password = str(new_form.phone)
                    TypeOne = CustomUser.objects.create_user(first_name=new_form.name, last_name = new_form.name, email = new_form.email, username = new_form.email, password=str(new_form.phone))
                    Staff.objects.create(member =new_form, admin = TypeOne, org = org, number = new_form.phone)
                    TypeOne.user_type = "3"
                    TypeOne.save()
                                
                    # SEND EMAIL
                    send_staff_welcome_email(new_form.email, new_form.name, password)
                    
                    messages.success(request, f"Successfully added {new_form.name}, granted dashboard access, and sent login credentials via email.")
                else:
                    messages.warning(request, f"Member added, but Staff account wasn't created. The email '{new_form.email}' already exists.")
            else:
                messages.success(request, f"Successfully added Member: {new_form.name}.")

            return HttpResponseRedirect(reverse('handle:addMember'))
        else:
            messages.error(request, "Failed adding Member: " + form.errors.as_text())
            return HttpResponseRedirect(reverse('handle:addMember'))
        
        
def memberEdit(request, id):
    mem = member.objects.get(id=id)
    auser = request.user
    org = auser.schooladmin.org if auser.user_type == "2" else None

    if request.method == 'POST':
        form = MemberForm(request.POST, instance=mem, org=org)
        if not form.is_valid():
            messages.error(request, "Failed updating Member: " + form.errors.as_text())
            return HttpResponseRedirect(reverse('handle:memberEdit', args=[mem.id]))

        mem = form.save(commit=False)
        mem.org = org
        mem.save()
        form.save_m2m()

        # Handle granting Staff later in edit phase
        if mem.make_staff and mem.email and mem.phone:
            # First check if they are already staff
            if not Staff.objects.filter(member=mem).exists():
                # Then check if the email is free to use
                if not CustomUser.objects.filter(email=mem.email).exists():
                    password = str(mem.phone)
                    
                    # Exact working logic from AddMember
                    TypeOne = CustomUser.objects.create_user(
                        first_name=mem.name, 
                        last_name=mem.name, 
                        email=mem.email, 
                        username=mem.email, 
                        password=password
                    )
                    
                    Staff.objects.create(member=mem, admin=TypeOne, org=org, number=mem.phone)
                    
                    TypeOne.user_type = "3"
                    TypeOne.save()
                    
                    # SEND EMAIL
                    send_staff_welcome_email(mem.email, mem.name, password)
                    
                    messages.success(request, f"Granted Staff access to {mem.name} and sent credentials to their email.")
                else:
                    messages.warning(request, "Failed to grant Staff access: Email already in use.")

        messages.success(request, f"Successfully Updated {mem.name}'s details.")
        return HttpResponseRedirect(reverse('handle:memberEdit', args=[mem.id]))

    form = MemberForm(instance=mem, org=org)
    dist ={
        'form': form,
        'mem': mem,
        'classi': Classification.objects.filter(org=org, status='active'),
        'sections': Section.objects.filter(org=org, status='active'),
        'branches': Branch.objects.filter(org=org, status='active'),
        'courses': Course.objects.filter(org=org, status='active'),
        'org': org
    }
    
    return render(request, "handle/editMember.html", dist)

class AddClassification(View):
    template_name = "handle/addClassification.html"
    form_class = ClassificationForm

    def get(self, request, *args, **kwargs):
        auser = request.user
        print("User", auser)
        if auser.user_type == "2":
            org =  auser.schooladmin.org
        else:
            org = None
        form = self.form_class(org=org)
        clas = Classification.objects.filter(org = org).select_related('branch')
        context = {
            'form': form,
            'branch_form': BranchForm(org=org),
            'section_form': SectionForm(org=org),
            'course_form': CourseForm(org=org),
            'branches': Branch.objects.filter(org=org),
            'sections': Section.objects.filter(org=org).select_related('branch', 'classification'),
            'courses': Course.objects.filter(org=org).select_related('branch', 'teacher').prefetch_related('classifications', 'sections'),
            'clas': clas,
            'org': org,
        }
        return render(request, self.template_name, context)
    
    def post(self, request, *args, **kwargs):
        auser = request.user
        print("User", auser)
        if auser.user_type == "2":
            org =  auser.schooladmin.org
        else:
            org = None

        if 'add_branch' in request.POST:
            form = BranchForm(request.POST, org=org)
            if form.is_valid():
                branch = form.save(commit=False)
                branch.org = org
                branch.save()
                messages.success(request, "Successfully added Branch")
            else:
                messages.error(request, "Failed adding Branch: " + form.errors.as_text())
            return HttpResponseRedirect(reverse('handle:addClassification'))

        if 'add_section' in request.POST:
            form = SectionForm(request.POST, org=org)
            if form.is_valid():
                section = form.save(commit=False)
                section.org = org
                if not section.branch and section.classification:
                    section.branch = section.classification.branch
                section.save()
                messages.success(request, "Successfully added Section")
            else:
                messages.error(request, "Failed adding Section: " + form.errors.as_text())
            return HttpResponseRedirect(reverse('handle:addClassification'))

        if 'add_course' in request.POST:
            form = CourseForm(request.POST, org=org)
            if form.is_valid():
                course = form.save(commit=False)
                course.org = org
                course.save()
                form.save_m2m()
                messages.success(request, "Successfully added Course")
            else:
                messages.error(request, "Failed adding Course: " + form.errors.as_text())
            return HttpResponseRedirect(reverse('handle:addClassification'))

        form = self.form_class(request.POST, org=org)
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
    clas = Classification.objects.get(id=id)
    auser = request.user
    org = auser.schooladmin.org if auser.user_type == "2" else None

    # Handle Bulk Transfer
    if request.method == 'POST' and 'transfer_members' in request.POST:
        target_class_id = request.POST.get('target_classification')
        selected_member_ids = request.POST.getlist('member_select')
        
        if target_class_id and selected_member_ids:
            target_class = Classification.objects.get(id=target_class_id)
            member.objects.filter(id__in=selected_member_ids).update(classification=target_class)
            messages.success(request, f"Successfully transferred {len(selected_member_ids)} members to {target_class.name}")
        return HttpResponseRedirect(reverse('handle:editClassification', args=[clas.id]))

    # Handle Name Update
    elif request.method == 'POST' and 'update_name' in request.POST:
        form = ClassificationForm(request.POST, instance=clas, org=org)
        if form.is_valid():
            form.save()
            messages.success(request, "Successfully Updated Classification")
        else:
            messages.error(request, "Failed updating Classification: " + form.errors.as_text())
        return HttpResponseRedirect(reverse('handle:editClassification', args=[clas.id]))

    # GET Request
    form = ClassificationForm(instance=clas, org=org)
    dist = {
        'form': form,
        'org': org,
        'clas': clas,
        'all_classifications': Classification.objects.filter(org=org).exclude(id=clas.id)
    }
    return render(request, "handle/editClassification.html", dist)
def deleteClassification(request, id):
    clas = Classification.objects.get(id= id)
    clas.delete()
    messages.success(request, "Successfully deleted classification")
    return HttpResponseRedirect(reverse('handle:addClassification'))


def sections_by_classification(request):
    auser = request.user
    if auser.user_type == "2":
        org = auser.schooladmin.org
    elif auser.user_type == "3":
        org = auser.staff.org
    else:
        org = None

    classification_id = request.GET.get('classification_id')
    branch_id = request.GET.get('branch_id')
    sections = Section.objects.filter(org=org, status='active')
    if classification_id:
        sections = sections.filter(classification_id=classification_id)
    if branch_id:
        sections = sections.filter(Q(branch_id=branch_id) | Q(branch__isnull=True))

    data = [{'id': item.id, 'name': item.name} for item in sections.order_by('name')]
    return JsonResponse({'sections': data})


class OperationsCenter(View):
    template_name = "handle/operations.html"

    def get(self, request, *args, **kwargs):
        org = current_org_for_user(request.user)
        if request.GET.get('export') == 'stock':
            return self.export_stock(org)
        if request.GET.get('export') == 'transactions':
            return self.export_transactions(org)
        if request.GET.get('export') == 'birthdays':
            return self.export_birthdays(org)
        return render(request, self.template_name, self.context_data(request, org))

    def post(self, request, *args, **kwargs):
        org = current_org_for_user(request.user)
        if not org:
            messages.error(request, "No organization found for this user.")
            return HttpResponseRedirect(reverse('handle:operations'))

        action = request.POST.get('action')
        form_map = {
            'stock_category': StockCategoryForm,
            'stock_item': StockItemForm,
            'stock_movement': StockMovementForm,
            'transaction_category': TransactionCategoryForm,
            'financial_transaction': FinancialTransactionForm,
        }
        form_class = form_map.get(action)
        if not form_class:
            messages.error(request, "Invalid operations action.")
            return HttpResponseRedirect(reverse('handle:operations'))

        if action == 'financial_transaction':
            form = form_class(request.POST, request.FILES, org=org)
        elif action in ('stock_item', 'stock_movement'):
            form = form_class(request.POST, org=org)
        else:
            form = form_class(request.POST)

        if form.is_valid():
            obj = form.save(commit=False)
            obj.org = org
            if hasattr(obj, 'created_by_id'):
                obj.created_by = request.user
            if hasattr(obj, 'branch') and not obj.branch and action == 'stock_movement':
                obj.branch = obj.item.branch
            obj.save()
            messages.success(request, "Operations record saved successfully.")
        else:
            messages.error(request, "Could not save record: " + form.errors.as_text())
        return HttpResponseRedirect(reverse('handle:operations'))

    def context_data(self, request, org):
        branch_id = request.GET.get('branch') or ''
        category_id = request.GET.get('category') or ''
        tx_type = request.GET.get('transaction_type') or ''
        start_date = request.GET.get('start_date') or ''
        end_date = request.GET.get('end_date') or ''

        stock_items = StockItem.objects.filter(org=org).select_related('branch', 'category')
        movements = StockMovement.objects.filter(org=org).select_related('branch', 'item', 'created_by')
        transactions = FinancialTransaction.objects.filter(org=org).select_related('branch', 'category', 'created_by')
        birthdays = member.objects.filter(org=org, date_of_birth__isnull=False).select_related('branch', 'classification', 'section')

        if branch_id:
            stock_items = stock_items.filter(branch_id=branch_id)
            movements = movements.filter(branch_id=branch_id)
            transactions = transactions.filter(branch_id=branch_id)
            birthdays = birthdays.filter(branch_id=branch_id)
        if category_id:
            stock_items = stock_items.filter(category_id=category_id)
        if tx_type:
            transactions = transactions.filter(transaction_type=tx_type)
        if start_date:
            movements = movements.filter(movement_date__gte=start_date)
            transactions = transactions.filter(transaction_date__gte=start_date)
        if end_date:
            movements = movements.filter(movement_date__lte=end_date)
            transactions = transactions.filter(transaction_date__lte=end_date)

        today = timezone.localdate()
        next_30 = today + timedelta(days=30)
        birthday_pool = list(birthdays)
        todays_birthdays = [m for m in birthday_pool if m.date_of_birth.month == today.month and m.date_of_birth.day == today.day]
        upcoming_birthdays = [
            m for m in birthday_pool
            if today < self.next_birthday_date(m.date_of_birth, today) <= next_30
        ]
        upcoming_birthdays.sort(key=lambda m: self.next_birthday_date(m.date_of_birth, today))

        income_total = transactions.filter(transaction_type='income').aggregate(total=Sum('amount'))['total'] or 0
        expense_total = transactions.filter(transaction_type='expense').aggregate(total=Sum('amount'))['total'] or 0

        return {
            'org': org,
            'branches': Branch.objects.filter(org=org, status='active'),
            'stock_categories': StockCategory.objects.filter(org=org),
            'transaction_categories': TransactionCategory.objects.filter(org=org),
            'stock_category_form': StockCategoryForm(),
            'stock_item_form': StockItemForm(org=org),
            'stock_movement_form': StockMovementForm(org=org),
            'transaction_category_form': TransactionCategoryForm(),
            'financial_transaction_form': FinancialTransactionForm(org=org),
            'stock_items': stock_items,
            'stock_movements': movements[:25],
            'transactions': transactions[:25],
            'low_stock_items': [item for item in stock_items if item.is_low_stock],
            'income_total': income_total,
            'expense_total': expense_total,
            'net_total': income_total - expense_total,
            'todays_birthdays': todays_birthdays,
            'upcoming_birthdays': upcoming_birthdays[:20],
            'filters': {
                'branch': branch_id,
                'category': category_id,
                'transaction_type': tx_type,
                'start_date': start_date,
                'end_date': end_date,
            }
        }

    def next_birthday_date(self, birthday, today):
        try:
            candidate = birthday.replace(year=today.year)
        except ValueError:
            candidate = birthday.replace(year=today.year, day=28)
        if candidate < today:
            try:
                candidate = birthday.replace(year=today.year + 1)
            except ValueError:
                candidate = birthday.replace(year=today.year + 1, day=28)
        return candidate

    def export_stock(self, org):
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="stock-report.csv"'
        writer = csv.writer(response)
        writer.writerow(['Item', 'Branch', 'Category', 'SKU', 'Quantity', 'Unit', 'Low Stock Threshold', 'Supplier', 'Purchase Cost', 'Status'])
        for item in StockItem.objects.filter(org=org).select_related('branch', 'category'):
            writer.writerow([
                item.name, item.branch or '', item.category or '', item.sku or '',
                item.quantity, item.unit, item.low_stock_threshold,
                item.supplier or '', item.purchase_cost, item.status
            ])
        return response

    def export_transactions(self, org):
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="transactions-report.csv"'
        writer = csv.writer(response)
        writer.writerow(['Date', 'Type', 'Title', 'Category', 'Branch', 'Amount', 'Payment Method', 'Reference'])
        for item in FinancialTransaction.objects.filter(org=org).select_related('branch', 'category'):
            writer.writerow([
                item.transaction_date, item.transaction_type, item.title,
                item.category or '', item.branch or '', item.amount,
                item.payment_method, item.reference_number or ''
            ])
        return response

    def export_birthdays(self, org):
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="birthday-report.csv"'
        writer = csv.writer(response)
        writer.writerow(['Name', 'Birthday', 'Branch', 'Classification', 'Section', 'Phone', 'Email'])
        for item in member.objects.filter(org=org, date_of_birth__isnull=False).select_related('branch', 'classification', 'section'):
            writer.writerow([
                item.name, item.date_of_birth, item.branch or '',
                item.classification or '', item.section or '', item.phone or '', item.email or ''
            ])
        return response



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
            'clas':Classification.objects.filter(org=org, status='active'),
            'branches': Branch.objects.filter(org=org, status='active'),
            'sections': Section.objects.filter(org=org, status='active'),
            'thisone':'All',
            'selected_branch': 'All',
            'selected_section': 'All',
            'org':org
        }
        return render(request, self.template_name, dist)

    def post(self, request, *agrs, **kwargs):
        clas = request.POST.get('classification', 'All')
        branch = request.POST.get('branch', 'All')
        section = request.POST.get('section', 'All')
        print('class', clas)
        auser = request.user
        if auser.user_type == "2":
            org =  auser.schooladmin.org
        elif auser.user_type == "3":
            org =  auser.staff.org
      
        cl=Classification.objects.filter(org=org, status='active')
        mem = member.objects.filter(org=org)
        if branch != 'All':
            mem = mem.filter(branch_id=branch)
        if section != 'All':
            mem = mem.filter(section_id=section)
        if clas == 'All':
            th = 'All' 
        else:
            mem = mem.filter(classification=clas)
            th = Classification.objects.get(id = clas).name
        dist = {
            'mem':mem,
            'clas':cl,
            'branches': Branch.objects.filter(org=org, status='active'),
            'sections': Section.objects.filter(org=org, status='active'),
            'thisone': th,
            'selected_branch': branch,
            'selected_section': section,
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
