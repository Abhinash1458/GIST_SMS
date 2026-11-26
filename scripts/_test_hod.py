"""Temporary end-to-end check for the HOD approval screens."""

import http.client
import os
import re
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

TEMP_DIR = Path(tempfile.mkdtemp(prefix="sms-hod-"))
DB_PATH = TEMP_DIR / "test.db"
os.environ["DATABASE_URL"] = f"sqlite:///{DB_PATH.as_posix()}"

PORT = 8013
HOST = "127.0.0.1"
UPLOAD_ROOT = BASE_DIR / "app" / "static" / "uploads" / "registrations"

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
    data = response.read().decode("utf-8", errors="replace")
    result = (
        response.status,
        response.getheader("Location"),
        dict(response.getheaders()),
        data,
    )
    connection.close()
    return result


def login(username, password):
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

from sqlmodel import Session, select

from app.database import create_db_and_tables, engine
from app.config import settings
from app.models import (
    Batch,
    Department,
    MentorGroup,
    Registration,
    RegistrationStatus,
    Role,
    Section,
    Student,
    User,
)
from app.security import hash_password, verify_password

create_db_and_tables()

now = datetime.now(timezone.utc)

with Session(engine) as session:
    cse = Department(code="CSE", name="Computer Science and Engineering", intake=180)
    it = Department(code="IT", name="Information Technology", intake=120)
    session.add(cse)
    session.add(it)
    session.flush()

    users = {
        "hod_cse": User(
            username="hod-cse@example.com",
            full_name="CSE HOD",
            email="hod-cse@example.com",
            password_hash=hash_password("Hod@12345"),
            role=Role.hod,
            department_id=cse.id,
            created_at=now,
        ),
        "hod_it": User(
            username="hod-it@example.com",
            full_name="IT HOD",
            email="hod-it@example.com",
            password_hash=hash_password("Hod@12345"),
            role=Role.hod,
            department_id=it.id,
            created_at=now,
        ),
        "mentor_cse": User(
            username="mentor-cse@example.com",
            full_name="CSE Mentor",
            email="mentor-cse@example.com",
            password_hash=hash_password("Mentor@12345"),
            role=Role.mentor,
            department_id=cse.id,
            created_at=now,
        ),
        "management": User(
            username="management@example.com",
            full_name="Management",
            email="management@example.com",
            password_hash=hash_password("Admin@12345"),
            role=Role.management,
            created_at=now,
        ),
    }
    for user in users.values():
        session.add(user)
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
    session.add(
        MentorGroup(
            section_id=section.id,
            name="A-1",
            mentor_user_id=users["mentor_cse"].id,
            capacity=30,
        )
    )
    session.flush()

    registrations = {}

    def make_registration(reference, name, department_id):
        folder = UPLOAD_ROOT / reference
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "photo.jpg").write_bytes(b"\xff\xd8\xff\xe0test")
        (folder / "marks_memo.pdf").write_bytes(b"%PDF-1.4 test")
        (folder / "id_proof.png").write_bytes(b"\x89PNG test")
        record = Registration(
            reference_no=reference,
            full_name=name,
            dob=date(2007, 5, 10),
            gender="Male",
            phone="9876543210",
            email=f"{reference.lower()}@example.com",
            parent_name="Test Parent",
            department_id=department_id,
            quota="Convener",
            entrance_rank=101,
            tenth_percent=88.5,
            inter_percent=91.25,
            photo_path=f"uploads/registrations/{reference}/photo.jpg",
            marks_memo_path=f"uploads/registrations/{reference}/marks_memo.pdf",
            id_proof_path=f"uploads/registrations/{reference}/id_proof.png",
            status=RegistrationStatus.pending,
            submitted_at=now,
        )
        session.add(record)
        session.flush()
        return record

    registrations["cse"] = make_registration(
        "REG-2026-90001", "CSE Applicant", cse.id
    )
    registrations["cse_reject"] = make_registration(
        "REG-2026-90002", "CSE Reject Me", cse.id
    )
    registrations["it"] = make_registration(
        "REG-2026-90003", "IT Applicant", it.id
    )

    cse_ids = {
        "cse": registrations["cse"].id,
        "cse_reject": registrations["cse_reject"].id,
    }
    it_id = registrations["it"].id

    session.commit()

# ----------------------------------------------------------------------
# Start the application
# ----------------------------------------------------------------------

server_env = dict(os.environ)
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
    env=server_env,
    stdout=subprocess.DEVNULL,
    stderr=subprocess.STDOUT,
)

try:
    for _ in range(60):
        try:
            status, _, _, _ = request("GET", "/health")
            if status == 200:
                break
        except OSError:
            pass
        time.sleep(0.25)
    else:
        raise RuntimeError("Server did not start")

    print("\n== 1. Access control ==")
    status, location, _, html = request("GET", "/hod/registrations")
    check("anonymous redirected", status == 303 and location == "/login", status)

    management_status, mgmt_headers = login(
        "management@example.com", "Admin@12345"
    )
    check("management login", management_status == 303, management_status)
    status, _, _, html = request(
        "GET", "/hod/registrations", headers=mgmt_headers
    )
    check("non-HOD blocked", status == 403 and "Access denied" in html, status)

    print("\n== 2. CSE HOD list ==")
    status, cse_headers = login("hod-cse@example.com", "Hod@12345")
    check("HOD login", status == 303, status)

    status, _, _, html = request("GET", "/hod/registrations", headers=cse_headers)
    check("list loads", status == 200, status)
    check("own registration visible", "REG-2026-90001" in html)
    check("other department hidden", "REG-2026-90003" not in html)
    check("pending KPI", "Pending" in html and "Approved this year / intake" in html)
    check("documents count", "3/3" in html)
    check("filter tabs", "Sent back" in html and "Rejected" in html)

    status, _, _, html = request("GET", "/hod", headers=cse_headers)
    check("dashboard loads", status == 200, status)

    print("\n== 3. Detail page ==")
    status, _, _, html = request(
        "GET", f"/hod/registrations/{cse_ids['cse']}", headers=cse_headers
    )
    check("detail loads", status == 200, status)
    check("photo shown", "photo.jpg" in html and "Applicant photo" in html)
    check("document links", "Open Marks memo" in html and "Open ID proof" in html)
    check("decision forms", "/approve" in html and "/reject" in html and "/correction" in html)

    print("\n== 4. Remarks are required ==")
    status, _, _, html = request(
        "POST",
        f"/hod/registrations/{cse_ids['cse']}/reject",
        {"remarks": "   "},
        cse_headers,
    )
    check("empty remarks rejected", status == 400 and "Remarks are required" in html, status)

    with Session(engine) as session:
        record = session.get(Registration, cse_ids["cse"])
        check("still pending after empty remarks", record.status == RegistrationStatus.pending)

    print("\n== 5. Approve ==")
    status, _, _, html = request(
        "POST",
        f"/hod/registrations/{cse_ids['cse']}/approve",
        headers=cse_headers,
    )
    check("approval result page", status == 200, status)
    check("success banner", "CSE Applicant is now a student of CSE" in html, html[:500])

    match = re.search(r'<div class="ref-number">([^<]+)</div>', html)
    roll_number = match.group(1).strip() if match else ""
    check("roll number displayed", bool(roll_number), roll_number)
    check("roll breakdown", "How the roll number is built" in html)
    check("mentor group and name", "CSE Mentor" in html and "Mentor group" in html)
    check("password shown once", "Temporary password" in html and "Shown once" in html)

    password_match = re.search(r"<code class=\"fs-6\">([^<]+)</code>", html)
    temp_password = password_match.group(1) if password_match else ""

    with Session(engine) as session:
        record = session.get(Registration, cse_ids["cse"])
        check("registration approved in DB", record.status == RegistrationStatus.approved)
        check("student linked", record.student_id is not None)
        student = session.get(Student, record.student_id)
        check("roll number in DB", student.roll_number == roll_number, student.roll_number)
        check(
            "temporary password stored as hash",
            bool(temp_password) and verify_password(temp_password, student.user.password_hash),
        )
        check("must change password", student.user.must_change_password)

    print("\n== 6. Cannot approve twice ==")
    status, _, _, html = request(
        "POST",
        f"/hod/registrations/{cse_ids['cse']}/approve",
        headers=cse_headers,
    )
    check("second approval does not crash", status == 200, status)
    check("already decided message", "No action taken" in html and "no longer pending" in html)

    with Session(engine) as session:
        count = len(
            session.exec(
                select(Student).where(Student.full_name == "CSE Applicant")
            ).all()
        )
        check("no duplicate student", count == 1, count)

    print("\n== 7. Reject with remarks ==")
    status, _, location, _ = request(
        "POST",
        f"/hod/registrations/{cse_ids['cse_reject']}/reject",
        {"remarks": "Marks memo is unreadable."},
        cse_headers,
    )
    check("reject redirects", status == 303, status)
    with Session(engine) as session:
        record = session.get(Registration, cse_ids["cse_reject"])
        check("status rejected", record.status == RegistrationStatus.rejected)
        check("remarks saved", record.hod_remarks == "Marks memo is unreadable.")

    print("\n== 8. Other department's HOD ==")
    status, it_headers = login("hod-it@example.com", "Hod@12345")
    check("IT HOD login", status == 303, status)

    status, _, _, html = request("GET", "/hod/registrations", headers=it_headers)
    check("IT HOD sees own registration", "REG-2026-90003" in html)
    check("IT HOD cannot see CSE registration", "REG-2026-90001" not in html)

    status, _, _, html = request(
        "GET", f"/hod/registrations/{cse_ids['cse']}", headers=it_headers
    )
    check("cross-department detail blocked", status == 404, status)

    status, _, _, html = request(
        "POST",
        f"/hod/registrations/{cse_ids['cse']}/approve",
        headers=it_headers,
    )
    check("cross-department approve blocked", status == 404, status)

    status, _, _, html = request(
        "POST",
        f"/hod/registrations/{it_id}/correction",
        {"remarks": "Please upload a clearer ID proof."},
        it_headers,
    )
    check("correction redirects", status == 303, status)
    with Session(engine) as session:
        record = session.get(Registration, it_id)
        check("status correction", record.status == RegistrationStatus.correction)
        check("correction remarks saved", "clearer ID proof" in (record.hod_remarks or ""))

finally:
    server.terminate()
    try:
        server.wait(timeout=10)
    except subprocess.TimeoutExpired:
        server.kill()
    shutil.rmtree(TEMP_DIR, ignore_errors=True)
    for reference in ("REG-2026-90001", "REG-2026-90002", "REG-2026-90003"):
        shutil.rmtree(UPLOAD_ROOT / reference, ignore_errors=True)

print("\n----------------------------------")
if FAILURES:
    print(f"{len(FAILURES)} FAILED: {FAILURES}")
    sys.exit(1)

print("All HOD checks passed.")
