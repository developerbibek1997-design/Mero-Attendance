#!/usr/bin/env python
"""
Standalone script: imports 309 historical attendance scans for org #24.

No manage.py, no CLI args, no separate CSV needed - everything is embedded
below so this runs as-is from cPanel's "Execute Python Script" tool.

HOW TO USE
1. Upload this file to your project root (same folder as manage.py).
2. First run it AS-IS (DRY_RUN = True below) and read the summary it
   prints - it tells you exactly what would be created/skipped without
   touching the database.
3. If the summary looks right, edit this file, change DRY_RUN to False,
   re-upload, and run it again to actually commit the records.
4. Safe to run more than once - anything already imported is recognized
   and skipped, so accidentally running it twice never creates duplicates.
"""

import os
import sys
import datetime

# ── 1. Point this at wherever manage.py lives on the server ────────────────
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'school.settings')

import django
django.setup()

from django.db import transaction
from django.utils import timezone
from handle.models import AttendanceRecord, member
from management.models import Organization

# ── 2. Settings ──────────────────────────────────────────────────────────
ORG_ID = 24
ATTENDANCE_METHOD = 'biometric'
DRY_RUN = True   # <-- set to False once the dry-run summary looks correct

# ── 3. Data: (member_id, member_name, "YYYY-MM-DD HH:MM:SS") ───────────────
# member_id already resolved to org #24's current member records by name.
ROWS = [
    (1203, "Dambar Kumar Rai", "2026-07-17 07:20:33"),
    (1210, "Jivan Kumar Karki", "2026-07-17 07:50:27"),
    (1172, "Binu Tamang", "2026-07-17 08:22:48"),
    (1186, "Bikram Tamang", "2026-07-17 08:26:07"),
    (1182, "Manisha Thapa", "2026-07-17 09:44:18"),
    (1168, "Anish Manandhar", "2026-07-17 09:46:50"),
    (1176, "Jiwan Das Shrestha", "2026-07-17 09:49:38"),
    (1197, "Ashish Phuyal", "2026-07-17 09:49:54"),
    (1201, "Nishan Adhikari", "2026-07-17 09:52:02"),
    (1188, "Kopila Majhi", "2026-07-17 09:52:46"),
    (1174, "Gokul Pandey", "2026-07-17 09:54:20"),
    (1164, "Daulat Singh Thagunna", "2026-07-17 09:54:34"),
    (1189, "Shrija Shrestha", "2026-07-17 09:56:25"),
    (1163, "Saran Mali", "2026-07-17 09:57:01"),
    (1177, "Arya Poudel", "2026-07-17 09:57:04"),
    (1171, "Ganga Shrestha", "2026-07-17 09:57:47"),
    (1166, "Siddharth Sharma", "2026-07-17 09:59:27"),
    (1194, "Sundar Rai", "2026-07-17 10:05:09"),
    (1179, "Sushma Rai", "2026-07-17 10:05:13"),
    (1196, "Madhusudan Giri", "2026-07-17 10:07:49"),
    (1192, "Bom Bahadur KC", "2026-07-17 10:08:14"),
    (1200, "Sapishya Pangeni", "2026-07-17 10:09:39"),
    (1170, "Prakash Kumar Karna", "2026-07-17 10:10:46"),
    (1181, "Shirish Amatya", "2026-07-17 10:12:27"),
    (1161, "Umanga Dhungana", "2026-07-17 10:12:36"),
    (1208, "Shrijana Neupane", "2026-07-17 10:18:27"),
    (1169, "Yazu Suwal", "2026-07-17 10:19:49"),
    (1187, "Dewan Shrestha", "2026-07-17 10:31:45"),
    (1185, "Rajan Kumar Shrestha", "2026-07-17 10:32:09"),
    (1195, "Kiran Chaudhari", "2026-07-17 10:47:18"),
    (1202, "Mahesh Tamang", "2026-07-17 10:58:33"),
    (1193, "Archisha Pal", "2026-07-17 11:31:08"),
    (1165, "Manmohan Joshi", "2026-07-17 12:11:39"),
    (1178, "Rajesh Rai", "2026-07-17 12:53:55"),
    (1169, "Yazu Suwal", "2026-07-17 16:36:17"),
    (1197, "Ashish Phuyal", "2026-07-17 16:38:10"),
    (1182, "Manisha Thapa", "2026-07-17 16:52:23"),
    (1162, "Amit Bhattarai", "2026-07-17 16:52:51"),
    (1162, "Amit Bhattarai", "2026-07-17 16:52:53"),
    (1166, "Siddharth Sharma", "2026-07-17 16:52:59"),
    (1168, "Anish Manandhar", "2026-07-17 16:53:14"),
    (1185, "Rajan Kumar Shrestha", "2026-07-17 16:55:46"),
    (1164, "Daulat Singh Thagunna", "2026-07-17 16:57:16"),
    (1164, "Daulat Singh Thagunna", "2026-07-17 16:57:19"),
    (1181, "Shirish Amatya", "2026-07-17 16:57:26"),
    (1171, "Ganga Shrestha", "2026-07-17 16:58:49"),
    (1186, "Bikram Tamang", "2026-07-17 17:00:07"),
    (1172, "Binu Tamang", "2026-07-17 17:00:10"),
    (1208, "Shrijana Neupane", "2026-07-17 17:00:17"),
    (1177, "Arya Poudel", "2026-07-17 17:00:32"),
    (1163, "Saran Mali", "2026-07-17 17:00:38"),
    (1200, "Sapishya Pangeni", "2026-07-17 17:01:07"),
    (1191, "Bidisha Adhikari", "2026-07-17 17:02:43"),
    (1193, "Archisha Pal", "2026-07-17 17:04:53"),
    (1189, "Shrija Shrestha", "2026-07-17 17:05:04"),
    (1170, "Prakash Kumar Karna", "2026-07-17 17:05:12"),
    (1161, "Umanga Dhungana", "2026-07-17 17:05:20"),
    (1201, "Nishan Adhikari", "2026-07-17 17:06:31"),
    (1174, "Gokul Pandey", "2026-07-17 17:08:58"),
    (1188, "Kopila Majhi", "2026-07-17 17:09:33"),
    (1192, "Bom Bahadur KC", "2026-07-17 17:09:39"),
    (1195, "Kiran Chaudhari", "2026-07-17 17:09:42"),
    (1179, "Sushma Rai", "2026-07-17 17:09:48"),
    (1196, "Madhusudan Giri", "2026-07-17 17:09:51"),
    (1194, "Sundar Rai", "2026-07-17 17:09:55"),
    (1210, "Jivan Kumar Karki", "2026-07-17 17:10:38"),
    (1203, "Dambar Kumar Rai", "2026-07-17 17:14:59"),
    (1210, "Jivan Kumar Karki", "2026-07-18 08:15:15"),
    (1203, "Dambar Kumar Rai", "2026-07-19 07:15:57"),
    (1210, "Jivan Kumar Karki", "2026-07-19 07:49:16"),
    (1199, "Sunita Rai", "2026-07-19 07:57:48"),
    (1172, "Binu Tamang", "2026-07-19 08:19:11"),
    (1186, "Bikram Tamang", "2026-07-19 08:24:48"),
    (1197, "Ashish Phuyal", "2026-07-19 08:58:42"),
    (1191, "Bidisha Adhikari", "2026-07-19 09:42:19"),
    (1182, "Manisha Thapa", "2026-07-19 09:42:31"),
    (1163, "Saran Mali", "2026-07-19 09:45:21"),
    (1176, "Jiwan Das Shrestha", "2026-07-19 09:47:10"),
    (1201, "Nishan Adhikari", "2026-07-19 09:49:47"),
    (1166, "Siddharth Sharma", "2026-07-19 09:51:40"),
    (1179, "Sushma Rai", "2026-07-19 09:51:43"),
    (1194, "Sundar Rai", "2026-07-19 09:51:49"),
    (1171, "Ganga Shrestha", "2026-07-19 09:52:00"),
    (1188, "Kopila Majhi", "2026-07-19 09:52:25"),
    (1177, "Arya Poudel", "2026-07-19 09:53:49"),
    (1174, "Gokul Pandey", "2026-07-19 09:53:55"),
    (1208, "Shrijana Neupane", "2026-07-19 09:54:00"),
    (1168, "Anish Manandhar", "2026-07-19 09:54:06"),
    (1164, "Daulat Singh Thagunna", "2026-07-19 09:54:11"),
    (1200, "Sapishya Pangeni", "2026-07-19 10:00:30"),
    (1169, "Yazu Suwal", "2026-07-19 10:01:19"),
    (1196, "Madhusudan Giri", "2026-07-19 10:06:23"),
    (1192, "Bom Bahadur KC", "2026-07-19 10:06:31"),
    (1181, "Shirish Amatya", "2026-07-19 10:13:58"),
    (1185, "Rajan Kumar Shrestha", "2026-07-19 10:16:34"),
    (1165, "Manmohan Joshi", "2026-07-19 10:21:50"),
    (1193, "Archisha Pal", "2026-07-19 10:25:44"),
    (1187, "Dewan Shrestha", "2026-07-19 10:29:22"),
    (1178, "Rajesh Rai", "2026-07-19 10:34:07"),
    (1195, "Kiran Chaudhari", "2026-07-19 10:45:05"),
    (1202, "Mahesh Tamang", "2026-07-19 10:51:39"),
    (1162, "Amit Bhattarai", "2026-07-19 16:54:22"),
    (1162, "Amit Bhattarai", "2026-07-19 16:55:43"),
    (1162, "Amit Bhattarai", "2026-07-19 16:55:48"),
    (1193, "Archisha Pal", "2026-07-19 16:56:54"),
    (1166, "Siddharth Sharma", "2026-07-19 16:56:59"),
    (1161, "Umanga Dhungana", "2026-07-19 16:58:42"),
    (1165, "Manmohan Joshi", "2026-07-19 16:58:46"),
    (1186, "Bikram Tamang", "2026-07-19 16:58:54"),
    (1168, "Anish Manandhar", "2026-07-19 16:58:58"),
    (1164, "Daulat Singh Thagunna", "2026-07-19 16:59:04"),
    (1172, "Binu Tamang", "2026-07-19 16:59:07"),
    (1171, "Ganga Shrestha", "2026-07-19 16:59:11"),
    (1188, "Kopila Majhi", "2026-07-19 16:59:13"),
    (1188, "Kopila Majhi", "2026-07-19 16:59:15"),
    (1192, "Bom Bahadur KC", "2026-07-19 17:00:38"),
    (1194, "Sundar Rai", "2026-07-19 17:01:00"),
    (1178, "Rajesh Rai", "2026-07-19 17:01:06"),
    (1179, "Sushma Rai", "2026-07-19 17:01:10"),
    (1201, "Nishan Adhikari", "2026-07-19 17:01:17"),
    (1181, "Shirish Amatya", "2026-07-19 17:01:22"),
    (1177, "Arya Poudel", "2026-07-19 17:01:25"),
    (1169, "Yazu Suwal", "2026-07-19 17:03:01"),
    (1163, "Saran Mali", "2026-07-19 17:03:03"),
    (1200, "Sapishya Pangeni", "2026-07-19 17:03:08"),
    (1185, "Rajan Kumar Shrestha", "2026-07-19 17:03:28"),
    (1200, "Sapishya Pangeni", "2026-07-19 17:04:03"),
    (1208, "Shrijana Neupane", "2026-07-19 17:04:27"),
    (1199, "Sunita Rai", "2026-07-19 17:05:41"),
    (1191, "Bidisha Adhikari", "2026-07-19 17:05:45"),
    (1203, "Dambar Kumar Rai", "2026-07-19 17:05:48"),
    (1203, "Dambar Kumar Rai", "2026-07-20 07:34:20"),
    (1210, "Jivan Kumar Karki", "2026-07-20 07:53:06"),
    (1172, "Binu Tamang", "2026-07-20 08:11:30"),
    (1199, "Sunita Rai", "2026-07-20 08:17:15"),
    (1185, "Rajan Kumar Shrestha", "2026-07-20 08:22:13"),
    (1186, "Bikram Tamang", "2026-07-20 09:06:44"),
    (1197, "Ashish Phuyal", "2026-07-20 09:25:40"),
    (1191, "Bidisha Adhikari", "2026-07-20 09:40:00"),
    (1182, "Manisha Thapa", "2026-07-20 09:40:12"),
    (1188, "Kopila Majhi", "2026-07-20 09:47:42"),
    (1163, "Saran Mali", "2026-07-20 09:48:10"),
    (1179, "Sushma Rai", "2026-07-20 09:50:09"),
    (1168, "Anish Manandhar", "2026-07-20 09:50:15"),
    (1194, "Sundar Rai", "2026-07-20 09:50:19"),
    (1176, "Jiwan Das Shrestha", "2026-07-20 09:51:26"),
    (1171, "Ganga Shrestha", "2026-07-20 09:52:02"),
    (1166, "Siddharth Sharma", "2026-07-20 09:52:33"),
    (1164, "Daulat Singh Thagunna", "2026-07-20 09:52:42"),
    (1177, "Arya Poudel", "2026-07-20 09:55:18"),
    (1201, "Nishan Adhikari", "2026-07-20 10:04:14"),
    (1161, "Umanga Dhungana", "2026-07-20 10:04:18"),
    (1200, "Sapishya Pangeni", "2026-07-20 10:04:23"),
    (1208, "Shrijana Neupane", "2026-07-20 10:11:51"),
    (1181, "Shirish Amatya", "2026-07-20 10:19:34"),
    (1202, "Mahesh Tamang", "2026-07-20 10:36:02"),
    (1174, "Gokul Pandey", "2026-07-20 10:57:40"),
    (1193, "Archisha Pal", "2026-07-20 11:01:14"),
    (1165, "Manmohan Joshi", "2026-07-20 11:13:17"),
    (1196, "Madhusudan Giri", "2026-07-20 11:36:43"),
    (1187, "Dewan Shrestha", "2026-07-20 12:00:50"),
    (1161, "Umanga Dhungana", "2026-07-20 16:11:34"),
    (1184, "Umesh Nepal", "2026-07-20 16:16:41"),
    (1197, "Ashish Phuyal", "2026-07-20 16:16:47"),
    (1166, "Siddharth Sharma", "2026-07-20 16:55:40"),
    (1164, "Daulat Singh Thagunna", "2026-07-20 16:56:26"),
    (1171, "Ganga Shrestha", "2026-07-20 16:57:47"),
    (1162, "Amit Bhattarai", "2026-07-20 16:59:45"),
    (1162, "Amit Bhattarai", "2026-07-20 16:59:47"),
    (1196, "Madhusudan Giri", "2026-07-20 17:00:00"),
    (1186, "Bikram Tamang", "2026-07-20 17:00:08"),
    (1195, "Kiran Chaudhari", "2026-07-20 17:00:11"),
    (1172, "Binu Tamang", "2026-07-20 17:00:30"),
    (1165, "Manmohan Joshi", "2026-07-20 17:00:44"),
    (1193, "Archisha Pal", "2026-07-20 17:01:12"),
    (1194, "Sundar Rai", "2026-07-20 17:01:17"),
    (1200, "Sapishya Pangeni", "2026-07-20 17:01:24"),
    (1208, "Shrijana Neupane", "2026-07-20 17:01:28"),
    (1163, "Saran Mali", "2026-07-20 17:01:43"),
    (1200, "Sapishya Pangeni", "2026-07-20 17:01:51"),
    (1177, "Arya Poudel", "2026-07-20 17:01:55"),
    (1191, "Bidisha Adhikari", "2026-07-20 17:02:05"),
    (1185, "Rajan Kumar Shrestha", "2026-07-20 17:02:32"),
    (1168, "Anish Manandhar", "2026-07-20 17:02:37"),
    (1188, "Kopila Majhi", "2026-07-20 17:02:43"),
    (1179, "Sushma Rai", "2026-07-20 17:02:49"),
    (1201, "Nishan Adhikari", "2026-07-20 17:03:47"),
    (1181, "Shirish Amatya", "2026-07-20 17:05:15"),
    (1210, "Jivan Kumar Karki", "2026-07-20 17:07:40"),
    (1203, "Dambar Kumar Rai", "2026-07-20 17:08:39"),
    (1199, "Sunita Rai", "2026-07-20 17:08:55"),
    (1203, "Dambar Kumar Rai", "2026-07-21 07:19:25"),
    (1210, "Jivan Kumar Karki", "2026-07-21 07:41:21"),
    (1199, "Sunita Rai", "2026-07-21 08:19:16"),
    (1188, "Kopila Majhi", "2026-07-21 08:35:26"),
    (1185, "Rajan Kumar Shrestha", "2026-07-21 08:39:04"),
    (1186, "Bikram Tamang", "2026-07-21 08:46:12"),
    (1171, "Ganga Shrestha", "2026-07-21 09:42:21"),
    (1191, "Bidisha Adhikari", "2026-07-21 09:43:36"),
    (1176, "Jiwan Das Shrestha", "2026-07-21 09:44:12"),
    (1197, "Ashish Phuyal", "2026-07-21 09:45:22"),
    (1174, "Gokul Pandey", "2026-07-21 09:47:10"),
    (1166, "Siddharth Sharma", "2026-07-21 09:51:19"),
    (1168, "Anish Manandhar", "2026-07-21 09:51:27"),
    (1179, "Sushma Rai", "2026-07-21 09:53:54"),
    (1194, "Sundar Rai", "2026-07-21 09:54:06"),
    (1161, "Umanga Dhungana", "2026-07-21 09:54:14"),
    (1164, "Daulat Singh Thagunna", "2026-07-21 09:54:17"),
    (1163, "Saran Mali", "2026-07-21 09:59:30"),
    (1177, "Arya Poudel", "2026-07-21 09:59:34"),
    (1201, "Nishan Adhikari", "2026-07-21 10:02:41"),
    (1196, "Madhusudan Giri", "2026-07-21 10:08:41"),
    (1200, "Sapishya Pangeni", "2026-07-21 10:08:44"),
    (1169, "Yazu Suwal", "2026-07-21 10:12:18"),
    (1181, "Shirish Amatya", "2026-07-21 10:14:08"),
    (1208, "Shrijana Neupane", "2026-07-21 10:17:23"),
    (1165, "Manmohan Joshi", "2026-07-21 10:18:57"),
    (1202, "Mahesh Tamang", "2026-07-21 10:27:17"),
    (1193, "Archisha Pal", "2026-07-21 10:44:40"),
    (1189, "Shrija Shrestha", "2026-07-21 11:21:05"),
    (1195, "Kiran Chaudhari", "2026-07-21 11:28:20"),
    (1178, "Rajesh Rai", "2026-07-21 12:37:53"),
    (1162, "Amit Bhattarai", "2026-07-21 16:56:02"),
    (1162, "Amit Bhattarai", "2026-07-21 16:56:04"),
    (1166, "Siddharth Sharma", "2026-07-21 16:57:17"),
    (1168, "Anish Manandhar", "2026-07-21 16:59:02"),
    (1169, "Yazu Suwal", "2026-07-21 16:59:26"),
    (1186, "Bikram Tamang", "2026-07-21 17:00:20"),
    (1164, "Daulat Singh Thagunna", "2026-07-21 17:00:36"),
    (1185, "Rajan Kumar Shrestha", "2026-07-21 17:01:15"),
    (1177, "Arya Poudel", "2026-07-21 17:01:17"),
    (1188, "Kopila Majhi", "2026-07-21 17:01:26"),
    (1191, "Bidisha Adhikari", "2026-07-21 17:02:14"),
    (1193, "Archisha Pal", "2026-07-21 17:02:18"),
    (1189, "Shrija Shrestha", "2026-07-21 17:02:28"),
    (1163, "Saran Mali", "2026-07-21 17:02:32"),
    (1208, "Shrijana Neupane", "2026-07-21 17:02:41"),
    (1171, "Ganga Shrestha", "2026-07-21 17:02:48"),
    (1181, "Shirish Amatya", "2026-07-21 17:03:43"),
    (1200, "Sapishya Pangeni", "2026-07-21 17:03:48"),
    (1200, "Sapishya Pangeni", "2026-07-21 17:04:30"),
    (1196, "Madhusudan Giri", "2026-07-21 17:07:53"),
    (1161, "Umanga Dhungana", "2026-07-21 17:09:16"),
    (1194, "Sundar Rai", "2026-07-21 17:09:50"),
    (1179, "Sushma Rai", "2026-07-21 17:09:56"),
    (1197, "Ashish Phuyal", "2026-07-21 17:10:21"),
    (1199, "Sunita Rai", "2026-07-21 17:18:10"),
    (1203, "Dambar Kumar Rai", "2026-07-21 17:18:14"),
    (1203, "Dambar Kumar Rai", "2026-07-22 07:26:18"),
    (1210, "Jivan Kumar Karki", "2026-07-22 07:41:02"),
    (1172, "Binu Tamang", "2026-07-22 08:09:44"),
    (1199, "Sunita Rai", "2026-07-22 08:34:16"),
    (1186, "Bikram Tamang", "2026-07-22 09:01:47"),
    (1174, "Gokul Pandey", "2026-07-22 09:37:49"),
    (1176, "Jiwan Das Shrestha", "2026-07-22 09:38:36"),
    (1182, "Manisha Thapa", "2026-07-22 09:42:14"),
    (1208, "Shrijana Neupane", "2026-07-22 09:44:43"),
    (1191, "Bidisha Adhikari", "2026-07-22 09:45:35"),
    (1188, "Kopila Majhi", "2026-07-22 09:52:02"),
    (1164, "Daulat Singh Thagunna", "2026-07-22 09:52:13"),
    (1168, "Anish Manandhar", "2026-07-22 09:54:11"),
    (1179, "Sushma Rai", "2026-07-22 09:56:14"),
    (1194, "Sundar Rai", "2026-07-22 09:56:18"),
    (1171, "Ganga Shrestha", "2026-07-22 09:56:31"),
    (1202, "Mahesh Tamang", "2026-07-22 09:56:37"),
    (1166, "Siddharth Sharma", "2026-07-22 09:59:13"),
    (1177, "Arya Poudel", "2026-07-22 09:59:15"),
    (1165, "Manmohan Joshi", "2026-07-22 10:01:15"),
    (1169, "Yazu Suwal", "2026-07-22 10:06:29"),
    (1196, "Madhusudan Giri", "2026-07-22 10:06:36"),
    (1185, "Rajan Kumar Shrestha", "2026-07-22 10:06:40"),
    (1201, "Nishan Adhikari", "2026-07-22 10:06:44"),
    (1189, "Shrija Shrestha", "2026-07-22 10:08:01"),
    (1200, "Sapishya Pangeni", "2026-07-22 10:08:34"),
    (1163, "Saran Mali", "2026-07-22 10:09:24"),
    (1197, "Ashish Phuyal", "2026-07-22 10:16:07"),
    (1181, "Shirish Amatya", "2026-07-22 10:16:11"),
    (1193, "Archisha Pal", "2026-07-22 10:30:51"),
    (1195, "Kiran Chaudhari", "2026-07-22 11:27:22"),
    (1178, "Rajesh Rai", "2026-07-22 12:01:53"),
    (1161, "Umanga Dhungana", "2026-07-22 12:46:01"),
    (1206, "Preshit Baral", "2026-07-22 15:59:01"),
    (1206, "Preshit Baral", "2026-07-22 15:59:06"),
    (1197, "Ashish Phuyal", "2026-07-22 16:55:18"),
    (1162, "Amit Bhattarai", "2026-07-22 16:56:56"),
    (1162, "Amit Bhattarai", "2026-07-22 16:56:58"),
    (1166, "Siddharth Sharma", "2026-07-22 16:57:14"),
    (1164, "Daulat Singh Thagunna", "2026-07-22 16:57:28"),
    (1196, "Madhusudan Giri", "2026-07-22 16:57:37"),
    (1171, "Ganga Shrestha", "2026-07-22 16:57:58"),
    (1168, "Anish Manandhar", "2026-07-22 16:59:31"),
    (1201, "Nishan Adhikari", "2026-07-22 16:59:38"),
    (1172, "Binu Tamang", "2026-07-22 17:00:03"),
    (1186, "Bikram Tamang", "2026-07-22 17:00:10"),
    (1169, "Yazu Suwal", "2026-07-22 17:00:14"),
    (1177, "Arya Poudel", "2026-07-22 17:00:18"),
    (1194, "Sundar Rai", "2026-07-22 17:00:47"),
    (1191, "Bidisha Adhikari", "2026-07-22 17:01:11"),
    (1200, "Sapishya Pangeni", "2026-07-22 17:01:29"),
    (1179, "Sushma Rai", "2026-07-22 17:01:51"),
    (1188, "Kopila Majhi", "2026-07-22 17:02:01"),
    (1189, "Shrija Shrestha", "2026-07-22 17:02:11"),
    (1193, "Archisha Pal", "2026-07-22 17:02:14"),
    (1208, "Shrijana Neupane", "2026-07-22 17:03:06"),
    (1181, "Shirish Amatya", "2026-07-22 17:03:10"),
    (1185, "Rajan Kumar Shrestha", "2026-07-22 17:03:14"),
    (1163, "Saran Mali", "2026-07-22 17:03:19"),
    (1199, "Sunita Rai", "2026-07-22 17:09:57"),
    (1203, "Dambar Kumar Rai", "2026-07-22 17:10:02"),
]

# ── 4. Import logic (mirrors import_attendance_by_id.py) ───────────────────

def main():
    try:
        org = Organization.objects.get(pk=ORG_ID)
    except Organization.DoesNotExist:
        print(f"ERROR: Organization id={ORG_ID} does not exist.")
        return

    print(f"Importing attendance into org #{org.id} ({org.name})")
    print("*** DRY RUN - no changes will be saved ***" if DRY_RUN else "*** LIVE RUN - writing to the database ***")
    print()

    valid_member_ids = set(member.objects.filter(org=org).values_list('id', flat=True))
    existing_scans = set(
        AttendanceRecord.objects.filter(org=org).values_list('mem_id', 'scanned_time')
    )

    verb = 'would create' if DRY_RUN else 'created'
    created = 0
    duplicate = 0
    skipped = []

    for row_num, (mem_id, name, time_str) in enumerate(ROWS, start=1):
        if mem_id not in valid_member_ids:
            skipped.append((row_num, name, f"member #{mem_id} does not belong to org #{org.id}"))
            continue

        try:
            scanned_time = datetime.datetime.strptime(time_str, '%Y-%m-%d %H:%M:%S')
        except ValueError:
            skipped.append((row_num, name, f"bad time format: '{time_str}'"))
            continue

        if timezone.is_naive(scanned_time):
            try:
                scanned_time = timezone.make_aware(scanned_time)
            except Exception:
                pass

        if (mem_id, scanned_time) in existing_scans:
            duplicate += 1
            continue

        if DRY_RUN:
            created += 1
            print(f"  + Attendance {verb}: {name} (member #{mem_id}) at {scanned_time}")
            existing_scans.add((mem_id, scanned_time))
            continue

        try:
            with transaction.atomic():
                AttendanceRecord.objects.create(
                    mem_id=mem_id, org=org, scanned_time=scanned_time,
                    attendance_method=ATTENDANCE_METHOD,
                )
            existing_scans.add((mem_id, scanned_time))
            created += 1
            print(f"  + Attendance {verb}: {name} (member #{mem_id}) at {scanned_time}")
        except Exception as e:
            skipped.append((row_num, name, f"error: {e}"))

    print()
    print("-- Summary --------------------------")
    print(f"  Attendance records {verb}: {created}")
    print(f"  Already existed (skipped as duplicate): {duplicate}")
    print(f"  Rows skipped (invalid): {len(skipped)}")
    for row_num, name, reason in skipped:
        print(f"    row {row_num} ({name}): {reason}")
    if DRY_RUN:
        print()
        print("Dry run complete - no changes were saved.")
        print("Edit this file, set DRY_RUN = False, re-upload, and run again to commit.")


if __name__ == '__main__':
    main()
