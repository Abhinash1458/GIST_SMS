"""Temporary end-to-end check for the SQLADMIN screens."""

import http.client
import os
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import quote

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

TEMP_DIR = Path(tempfile.mkdtemp(prefix="sms-admin-"))
DB_PATH = TEMP_DIR / "test.db"
os.environ["DATABASE_URL"] = f"sqlite:///{DB_PATH.as_posix()}"

HOST = "127.0.0.1"
PORT = 8016

FAILURES = []


def check(label, condition, detail=""):
    if condition:
        print(f"PASS  {label}")
    else:
        FAILURES.append(label)
        print(f"FAIL  {label} {detail}")


def request(method, path, fields=None, headers=None):
    body = ""
    request_headers = dict(headers or {})

    if fields is not None:
        body = "&".join(
            f"{quote(str(key))}={quote(str(value))}"
            for key, value in fields.items()
        )
        request_headers["Content-Type"] = "application/x-www-form-urlencoded"

    connection = http.client.HTTPConnection(HOST, PORT, timeout=30)
    connection.request(method, path, body=body, headers=request_headers)
    response = connection.getresponse()
    result = (
        response.status,
        response.getheader("Location"),
        dict(response.getheaders()),
        response.read().decode("utf-8", errors="replace"),
    )
    connection.close()
    return result


def admin_login(username, password):
    status, _, headers, html = request(
        "POST",
        "/admin/login",
        {"username": username, "password": password},
    )
    cookie = headers.get("set-cookie", "").split(";")[0]
    return status, ({"Cookie": cookie} if cookie else {}), html


def main_login(username, password):
    status, _, headers, _ = request(
        "POST",
        "/login",
        {"username": username, "password": password},
    )
    cookie = headers.get("set-cookie", "").split(";")[0]
    return status, {"Cookie": cookie}


# ----------------------------------------------------------------------
# Seed a temporary database
# ----------------------------------------------------------------------

from sqlmodel import Session

from app.config import settings
from app.database import create_db_and_tables, engine
from app.models import (
    Batch,
    Department,
    Registration,
    RegistrationStatus,
    Role,
    Section,
    Student,
    StudentStatus,
    User,
)
from app.security import hash_password

create_db_and_tables()

now = datetime.now(timezone.utc)

with Session(engine) as session:
    cse = Department(code="CSE", name="Computer Science and Engineering", intake=120)
    session.add(cse)
    session.flush()

    management = User(
        username="management@college.edu",
        full_name="GIST Management",
        email="management@college.edu",
        password_hash=hash_password("Admin@12345"),
        role=Role.management,
        is_active=True,
        created_at=now,
    )
    hod = User(
        username="hod.cse@college.edu",
        full_name="CSE HOD",
        email="hod.cse@college.edu",
        password_hash=hash_password("Hod@12345"),
        role=Role.hod,
        department_id=cse.id,
        is_active=True,
        created_at=now,
    )
    student_user = User(
        username="26CSE001",
        full_name="CSE Applicant",
        email="cse-applicant@example.com",
        password_hash=hash_password("Student@12345"),
        role=Role.student,
        department_id=cse.id,
        is_active=True,
        must_change_password=True,
        created_at=now,
    )
    session.add(management)
    session.add(hod)
    session.add(student_user)
    session.flush()

    batch = Batch(
        department_id=cse.id,
        start_year=settings.ADMISSION_YEAR,
        end_year=settings.ADMISSION_YEAR + 4,
    )
    session.add(batch)
    session.flush()

    section = Section(
        batch_id=batch.id,
        name="A",
        current_year=1,
        current_semester=1,
        capacity=60,
    )
    session.add(section)
    session.flush()

    student = Student(
        user_id=student_user.id,
        roll_number="26CSE001",
        full_name="CSE Applicant",
        dob=date(2007, 5, 10),
        gender="Male",
        phone="9876543210",
        email="cse-applicant@example.com",
        parent_name="Test Parent",
        department_id=cse.id,
        batch_id=batch.id,
        section_id=section.id,
        quota="Convener",
        admission_year=settings.ADMISSION_YEAR,
        status=StudentStatus.active,
        created_at=now,
    )
    session.add(student)
    session.flush()

    registration = Registration(
        reference_no="REG-2026-80001",
        full_name="Pending Applicant",
        dob=date(2007, 6, 12),
        gender="Female",
        phone="9876543211",
        email="pending@example.com",
        parent_name="Pending Parent",
        department_id=cse.id,
        quota="Convener",
        entrance_rank=5,
        tenth_percent=90.0,
        inter_percent=92.0,
        status=RegistrationStatus.pending,
        submitted_at=now,
    )
    session.add(registration)
    session.commit()

    management_hash = management.password_hash
    management_id = management.id
    student_user_id = student_user.id
    student_hash = student_user.password_hash

# ----------------------------------------------------------------------
# Start the application
# ----------------------------------------------------------------------

server = subprocess.Popen(
    [
        sys.executable,
        "-m",
        "uvicorn",
        "app.main:app",
        "--host",
        HOST,
        "--port",
        str(PORT),
        "--log-level",
        "warning",
    ],
    cwd=BASE_DIR,
    env=dict(os.environ),
    stdout=subprocess.DEVNULL,
    stderr=subprocess.STDOUT,
)

try:
    for _ in range(60):
        try:
            if request("GET", "/health")[0] == 200:
                break
        except OSError:
            pass
        time.sleep(0.25)
    else:
        raise RuntimeError("Server did not start")

    print("\n== 1. Admin entry and login ==")
    status, location, _, html = request("GET", "/admin/")
    check("anonymous redirected to admin login",
          status == 302 and (location or "").endswith("/admin/login"),
          f"{status} {location}")

    status, _, _, html = request("GET", "/admin/login")
    check("admin login page loads", status == 200, status)
    check("GIST branding on login", "GIST SMS" in html and "SQLADMIN" in html)
    check("login form fields", 'name="username"' in html and 'name="password"' in html)

    status, _, html = admin_login("hod.cse@college.edu", "Hod@12345")
    check("HOD refused at admin login", status == 403, status)
    check("HOD sees explicit reason", "Only Management" in html, html[:300])
    check("no password hash leaked on refusal", management_hash not in html)

    status, _, html = admin_login("management@college.edu", "wrong-password")
    check("wrong password refused", status == 401, status)

    status, admin_headers, html = admin_login(
        "management@college.edu", "Admin@12345"
    )
    check("management login to admin", status == 302, status)
    check("admin session cookie set", "admin_session" in str(admin_headers), admin_headers)

    print("\n== 2. Admin dashboard and menu groups ==")
    status, _, _, html = request("GET", "/admin/", headers=admin_headers)
    check("admin index loads", status == 200, status)
    for group in ("People", "Academics", "Admissions", "Exams and attendance"):
        check(f"menu group: {group}", group in html)

    list_paths = (
        "/admin/user/list",
        "/admin/student/list",
        "/admin/department/list",
        "/admin/batch/list",
        "/admin/section/list",
        "/admin/mentor-group/list",
        "/admin/subject/list",
        "/admin/teaching-assignment/list",
        "/admin/roll-counter/list",
        "/admin/registration/list",
        "/admin/attendance/list",
        "/admin/mark/list",
        "/admin/exam/list",
        "/admin/exam-schedule/list",
        "/admin/hall-ticket/list",
        "/admin/leave-request/list",
        "/admin/notice/list",
    )
    for path in list_paths:
        status, _, _, _ = request("GET", path, headers=admin_headers)
        check(f"admin list {path}", status == 200, status)

    print("\n== 3. Password hash is never shown or editable ==")
    endpoints = [
        "/admin/user/list",
        f"/admin/user/details/{management_id}",
        f"/admin/user/edit/{management_id}",
        "/admin/user/create",
    ]
    for path in endpoints:
        status, _, _, html = request("GET", path, headers=admin_headers)
        check(f"{path} loads", status == 200, status)
        check(f"{path} no hash", management_hash not in html)
        check(f"{path} no password column/field",
              "password_hash" not in html and "Password hash" not in html)

    status, _, _, html = request("GET", "/admin/user/list", headers=admin_headers)
    check("user list shows username", "management@college.edu" in html)
    check("user list shows role", "management" in html)

    print("\n== 4. Search ==")
    status, _, _, html = request(
        "GET", "/admin/student/list?search=26CSE001", headers=admin_headers
    )
    check("student roll-number search", status == 200 and "26CSE001" in html
          and "CSE Applicant" in html, status)

    status, _, _, html = request(
        "GET", "/admin/student/list?search=CSE%20Applicant", headers=admin_headers
    )
    check("student name search", "26CSE001" in html, status)

    status, _, _, html = request(
        "GET", "/admin/user/list?search=management", headers=admin_headers
    )
    check("user username search", "management@college.edu" in html, status)

    status, _, _, html = request(
        "GET", "/admin/user/list?search=hod", headers=admin_headers
    )
    check("user role search", "hod.cse@college.edu" in html, status)

    status, _, _, html = request(
        "GET", "/admin/registration/list?search=pending", headers=admin_headers
    )
    check("registration status search", "REG-2026-80001" in html, status)

    print("\n== 5. Admin link visibility ==")
    status, mgmt_headers = main_login("management@college.edu", "Admin@12345")
    check("management main login", status == 303, status)
    status, _, _, html = request("GET", "/management", headers=mgmt_headers)
    check("management dashboard loads", status == 200, status)
    check("Admin link in management sidebar", 'href="/admin"' in html
          and ">Admin<" in html)

    status, hod_headers = main_login("hod.cse@college.edu", "Hod@12345")
    check("HOD main login", status == 303, status)
    status, _, _, html = request("GET", "/management", headers=hod_headers)
    check("HOD cannot open management dashboard", status == 403, status)
    check("Admin link hidden from HOD", 'href="/admin"' not in html)

    status, _, _, html = request("GET", "/hod", headers=hod_headers)
    check("HOD dashboard still works", status == 200, status)
    check("Admin link not in HOD menu", 'href="/admin"' not in html)

    print("\n== 6. Password hashes unchanged ==")
    with Session(engine) as session:
        check(
            "student password hash unchanged",
            session.get(User, student_user_id).password_hash == student_hash,
        )
        check(
            "management password hash unchanged",
            session.get(User, management_id).password_hash == management_hash,
        )

finally:
    server.terminate()
    try:
        server.wait(timeout=10)
    except subprocess.TimeoutExpired:
        server.kill()
    shutil.rmtree(TEMP_DIR, ignore_errors=True)

print("\n----------------------------------")
if FAILURES:
    print(f"{len(FAILURES)} FAILED: {FAILURES}")
    sys.exit(1)

print("All SQLADMIN checks passed.")
