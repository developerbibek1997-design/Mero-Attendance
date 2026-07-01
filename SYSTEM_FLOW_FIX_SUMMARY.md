# System Flow Fix Summary — Mero Attendance HRMS

**Date:** 2026-07-01  
**Scope:** Full system audit, feature-gate fixes, sidebar overhaul, SEO system, security hardening

---

## 1. Flows Checked

| Area | Status |
|------|--------|
| Organization feature flags (17 flags) | ✅ Audited |
| Middleware URL feature protection | ✅ Fixed |
| Schooladmin sidebar (all sections) | ✅ Audited + Fixed |
| Staff/Teacher sidebar | ✅ Fixed — staff_perms wired |
| Student portal sidebar | ✅ Fixed — staff_perms wired |
| Admin dashboard (Adashboard.html) | ✅ Audited |
| Staff dashboard (Sdashboard.html) | ✅ Audited |
| Payroll / Payslip flow | ✅ Audited |
| Leave management flow | ✅ Audited |
| Billing flow | ✅ Audited |
| Results / Exam flow | ✅ Audited |
| Stock / Inventory flow | ✅ Audited |
| Events flow | ✅ Audited |
| Finance (Income/Expense) flow | ✅ Audited |
| Branch management flow | ✅ Audited |
| Complaints flow | ✅ Audited |
| Resignation / HRMS flow | ✅ Audited |
| Task management flow | ✅ Audited |
| Public/SEO pages | ✅ Built |
| Blog system | ✅ Audited (model exists, views wired) |
| Sitemap / robots.txt | ✅ Created |
| StaffPermission model | ✅ Audited — 47 granular perms |
| Context processors | ✅ Working (org, features, staff_perms injected) |

---

## 2. Bugs Found & Fixed

### Bug 1 — Middleware: Staff URL patterns were ALL wrong (Critical)
**File:** `school/middleware.py`  
**Problem:** `_STAFF_FEATURE_URL_MAP` had URL prefixes like `staff/payslip`, `staff/billing`, `staff/leave`, `staff/complaints` — none of which matched the actual URL patterns in `staff/urls.py`. Staff feature protection was completely non-functional for every protected route.  
**Fix:** Corrected all staff URL prefixes to match actual routes:
- `staff/payslip` → `staff/my-payslips`
- `staff/billing` → `staff/my-bills`
- `staff/results` → `staff/my-results`
- `staff/leave` → `staff/apply-leave`
- `staff/complaints` → `staff/my-complaint`
- Added: `staff/teaching-log` → `study_gap`, `staff/my-resignation` → `hrms`, `staff/location-checkin` → `gps`, `staff/wifi-checkin` → `wifi`

### Bug 2 — Sidebar: Events, Courses, Study Gaps all gated under `feature_events` (Wrong)
**File:** `templates/dashboard.html` (lines 536–566)  
**Problem:** Courses and Study Gaps were shown inside the `{% if not org or org.feature_events %}` block. This meant:
- Disabling Events also hid Courses and Study Gaps
- Disabling Courses/Study Gaps had no effect if Events was on — they still showed
**Fix:** Split into three independent feature blocks:
- Events → `{% if not org or org.feature_events %}`
- Courses → `{% if not org or org.feature_courses %}`
- Study Gaps → `{% if not org or org.feature_study_gap %}`

### Bug 3 — Staff sidebar: No permission checks (Critical for security)
**File:** `templates/dashboard.html` (staff section, lines 995–1055)  
**Problem:** Staff sidebar showed Teaching Log, Class Reports, My Payslips, Apply Leave, Complaints, and Tasks to ALL staff regardless of their `StaffPermission` settings. The permission model existed but was never consulted in the sidebar.  
**Fix:** Added `staff_perms` guards to every staff nav item:
- Teaching Log → `{% if staff_perms.can_view_attendance %}`
- Class Reports → `{% if staff_perms.can_view_attendance %}`
- My Payslips → `{% if staff_perms.can_view_own_payslip %}`
- Apply Leave → `{% if staff_perms.can_request_leave %}`
- File Complaint → `{% if staff_perms.can_view_complaints %}`
- Tasks → `{% if staff_perms.can_view_tasks %}`
- My Resignation → `{% if features.hrms %}` (HRMS feature gate added — was missing)

### Bug 4 — Student sidebar: No permission checks
**File:** `templates/dashboard.html` (student section, lines 947–993)  
**Problem:** Same as Bug 3 — student portal sidebar showed Bills, Results, Leave, Complaints to all students with no per-student permission check.  
**Fix:** Added `staff_perms` guards:
- My Bills → `{% if staff_perms.can_view_billing %}`
- My Results → `{% if staff_perms.can_view_courses %}`
- Apply Leave → `{% if staff_perms.can_request_leave %}`
- Complaints → `{% if staff_perms.can_view_complaints %}`

### Bug 5 — Student Management always visible regardless of `feature_student_mgmt`
**File:** `templates/dashboard.html` (line 254)  
**Problem:** "Student Management" link showed in schooladmin sidebar even if `feature_student_mgmt` was disabled for the org.  
**Fix:** Wrapped in `{% if not org or org.feature_student_mgmt %}`.

### Bug 6 — WiFi Management always visible regardless of attendance method settings
**File:** `templates/dashboard.html` (lines 371–379)  
**Problem:** "Manage Office WiFi" appeared in every org's sidebar even if the org had neither WiFi nor location-based attendance enabled.  
**Fix:** Gated on `{% if not org or org.mutifeature_enable or org.location_based or org.qr_based %}`.

### Bug 7 — Middleware fail-open for unknown feature keys
**File:** `school/middleware.py` (line 150)  
**Status:** Documented (not changed — intentional design decision). Unknown feature keys default to allow. This is acceptable as a safety net but should be monitored.

### Bug 8 — `member.email` unique constraint with NULL values
**File:** `handle/models.py` (line ~120)  
**Status:** Documented. `email = models.EmailField(null=True, unique=True)` can cause issues with multiple NULL emails in some DB backends. SQLite handles this correctly (NULL != NULL), but worth noting for PostgreSQL migration.

---

## 3. Flows Improved

### Staff Privilege System (Complete)
The `StaffPermission` model (47 granular boolean fields) now actually controls sidebar visibility for staff users. Previously the model existed in the database but was never consulted in templates. Now every staff sidebar item checks both the org feature flag AND the individual staff permission.

### Feature Gate Consistency
All sidebar sections now correctly use their own dedicated feature flag:
- Events → `feature_events` only
- Courses → `feature_courses` only  
- Study Gaps → `feature_study_gap` only
- Student Management → `feature_student_mgmt`

### Middleware URL Protection Restored
Staff-side feature URL protection now actually works for all protected routes (previously all pattern matches were failing silently).

---

## 4. SEO Pages Added

Created a centralized SEO landing page system (`SeoLandingView`) driven by a single `SEO_PAGES` dictionary in `management/views.py`. One template (`templates/basic/seo_landing.html`) serves all pages.

**20 SEO landing pages created:**

| URL | Topic |
|-----|-------|
| `/attendance-management-system/` | General AMS |
| `/school-attendance-system/` | School focus |
| `/employee-attendance-system/` | Office/HR focus |
| `/biometric-attendance-system/` | Biometric devices |
| `/zkteco-attendance-software/` | ZKTeco specific |
| `/hikvision-attendance-software/` | Hikvision specific |
| `/qr-attendance-system/` | QR check-in |
| `/gps-attendance-system/` | Field staff GPS |
| `/wifi-attendance-system/` | WiFi auto-attendance |
| `/hrms-software-nepal/` | HRMS platform |
| `/payroll-management-system/` | Payroll module |
| `/school-billing-management-system/` | School billing |
| `/student-result-management-system/` | Result management |
| `/leave-management-system/` | Leave module |
| `/multi-branch-attendance-system/` | Multi-branch |
| `/staff-management-system/` | Staff HR |
| `/office-management-system/` | Office module |
| `/school-erp-nepal/` | School ERP |
| `/attendance-app-nepal/` | Mobile app |
| `/cloud-attendance-system/` | Cloud SaaS |

**Each page includes:**
- Unique `<title>` and `<meta description>`
- H1 and intro paragraph
- 3–4 content sections
- FAQ schema (JSON-LD structured data)
- CTA buttons (primary + contact sales)
- Related pages strip for internal linking
- Full-width CTA banner

**Additional files:**
- `templates/basic/sitemap.xml` — XML sitemap with all public + SEO + blog URLs
- `robots.txt` view — blocks admin/staff/schooladmin paths, links to sitemap
- `{% block meta %}` added to `pillar.html` — all public pages can now inject custom meta tags

**New URL patterns in `management/urls.py`:**
```python
path('sitemap.xml', views.SitemapView.as_view(), name='sitemap'),
path('robots.txt', views.robots_txt, name='robots_txt'),
path('<slug:slug>/', views.SeoLandingView.as_view(), name='seo_landing'),
```

---

## 5. Dashboard Improvements

The admin dashboard (`Adashboard.html`) already had feature-gated cards from the previous session. No additional changes were needed beyond what was already implemented:
- Finance stats: gated on `feature_finance`
- Stock stats: gated on `feature_stock`
- Leave requests: gated on `feature_leave`
- Task stats: gated on `feature_tasks`
- Payroll stats: gated on `feature_payroll`
- Billing stats: gated on `feature_billing`
- Results stats: gated on `feature_results`

---

## 6. Feature Gate Improvements

### Superadmin (user_type=1)
- Bypasses all feature checks in middleware (correct — superadmin must configure features)

### Schooladmin (user_type=2)
- Middleware blocks all feature-gated URLs when feature is disabled
- Sidebar shows/hides sections based on org feature flags
- All 17 feature flags respected in sidebar

### Staff (user_type=3)
- Middleware now correctly blocks: payslips, bills, results, leave, complaints, tasks, teaching log, resignation, GPS checkin, WiFi checkin
- Sidebar now checks BOTH feature flag AND individual `StaffPermission` for each item
- `_AdminPermissions` sentinel returns True for all perms when user_type is 1 or 2

### Student portal (user_type=3, member_type=student)
- Same permission model as staff
- Bills, results, leave, complaints all gated on both feature + staff_perms

---

## 7. Migrations Required

No new migrations required for this session. All model changes were done in the previous session:
- `management/migrations/0022_organization_feature_bulk_export_and_more.py` — 6 new feature fields
- `handle/migrations/0029_staffpermission.py` — StaffPermission model

Run if not already applied:
```bash
python3 manage.py migrate
```

---

## 8. Admin Settings Required

### For each new organization:
1. Go to `schooladmin/org-features/` (Feature Settings page)
2. Enable the modules your org needs
3. Apply a preset (School / College / Office / Institute) for quick setup

### For staff with special access:
1. Go to `schooladmin/hrms/staff-permissions/`
2. Click "Edit Permissions" for the staff member
3. Enable the specific permissions they need (view payslip, approve leave, manage members, etc.)

### For the SEO pages:
1. Make sure the production domain is `meroattendance.com` (hardcoded in sitemap)
2. Submit `/sitemap.xml` to Google Search Console
3. No further config needed — all 20 SEO pages are live immediately

---

## 9. Remaining Issues / Manual Decisions Needed

### High Priority

1. **`_NullPermissions` defaults** — Staff with no `StaffPermission` row get safe defaults (view attendance, view leave, request leave, view tasks, view payslips, view events, view complaints). If you want stricter defaults (deny all by default), change `_NullPermissions` in `school/features.py`.

2. **Auto-create StaffPermission on member → staff promotion** — When `make_member_staff=True` in a member form, a `StaffPermission` row is NOT auto-created. Add a signal in `handle/models.py` or call `StaffPermission.objects.get_or_create(member=member, org=org)` in the view that promotes a member to staff.

3. **`PayrollPolicy` auto-create** — If an org enables payroll but never visits Payroll Settings, `payroll_policy` may not exist, causing a crash in some payroll views. Add `get_or_create` in any view that accesses `PayrollPolicy`.

### Medium Priority

4. **WiFi feature field mapping** — `wifi` maps to `mutifeature_enable` (the multi-feature WiFi flag) in the middleware. This is accurate but unconventional. Consider renaming or adding a dedicated `feature_wifi` field in a future migration.

5. **Blog posts need seeding** — The `BlogPost` model is fully functional but has no content. Add 10–20 blog posts via the Django admin at `/admin/` or via a management command to populate the blog for SEO value.

6. **SEO page domain** — The sitemap and canonical URLs hardcode `meroattendance.com`. If you run on a different domain, update `management/views.py` in the `SitemapView` and `SeoLandingView` canonical URL.

7. **30+ more SEO pages** — The current 20 pages cover the main topics. The full requested list (factory, hospital, hotel, college, institute, teacher attendance, etc.) can be added by extending the `SEO_PAGES` dict in `management/views.py` — no template or URL changes needed.

### Low Priority

8. **`member.email` NULL uniqueness** — Fine on SQLite, may need a custom constraint for PostgreSQL migration.

9. **Attendance correction feature flag** — "Absence Correction" in the sidebar is currently ungated (always visible). If you want to restrict it, add a `feature_attendance_correction` flag or gate it behind `feature_hrms`.

10. **Analytics page (`schooladmin:analytics`)** — Currently always visible. Consider gating on `feature_bulk_export` or a new `feature_analytics` flag.
