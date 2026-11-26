"""Temporary end-to-end check for the public registration flow."""

import http.client
import sqlite3
import sys
import uuid
from datetime import date, datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

HOST = "127.0.0.1"
PORT = 8011

UPLOADS = BASE_DIR / "app" / "static" / "uploads" / "registrations"
REFERENCE = "REG-2026-00001"

failures = []


def check(label, condition, detail=""):
    if condition:
        print(f"PASS  {label}")
    else:
        failures.append(label)
        print(f"FAIL  {label} {detail}")


def request(method, path, fields=None, files=None, headers=None):
    boundary = "----test" + uuid.uuid4().hex
    body = b""

    if fields is not None or files is not None:
        parts = []

        for name, value in (fields or {}).items():
            parts.append(
                (
                    f"--{boundary}\r\n"
                    f'Content-Disposition: form-data; name="{name}"\r\n\r\n'
                    f"{value}\r\n"
                ).encode()
            )

        for name, (filename, content) in (files or {}).items():
            parts.append(
                (
                    f"--{boundary}\r\n"
                    f'Content-Disposition: form-data; name="{name}"; '
                    f'filename="{filename}"\r\n'
                    "Content-Type: application/octet-stream\r\n\r\n"
                ).encode()
            )
            parts.append(content)
            parts.append(b"\r\n")

        parts.append(f"--{boundary}--\r\n".encode())
        body = b"".join(parts)

        headers = dict(headers or {})
        headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"

    connection = http.client.HTTPConnection(HOST, PORT, timeout=30)
    connection.request(method, path, body=body, headers=headers or {})
    response = connection.getresponse()
    data = response.read().decode("utf-8", errors="replace")
    status = response.status
    location = response.getheader("Location")
    connection.close()
    return status, location, data


FIELDS = {
    "full_name": "Test Student",
    "dob": "2007-05-10",
    "gender": "Male",
    "phone": "9876543210",
    "email": "test.student@example.com",
    "parent_name": "Test Parent",
    "department_id": "1",
    "quota": "Convener",
    "tenth_percent": "88.5",
    "inter_percent": "91.25",
    "entrance_rank": "1234",
}

PHOTO = b"\xff\xd8\xff\xe0" + b"0" * 500
MEMO = b"%PDF-1.4\n" + b"0" * 500
IDPROOF = b"\x89PNG\r\n\x1a\n" + b"0" * 500

FILES = {
    "photo": ("photo.jpg", PHOTO),
    "marks_memo": ("memo.pdf", MEMO),
    "id_proof": ("id.png", IDPROOF),
}


print("\n== 1. GET /register ==")
status, _, html = request("GET", "/register")
check("form loads", status == 200, status)
check("branch dropdown has departments", "CSE - Computer Science" in html)
check("four steps rendered", html.count("form-step") >= 4)


print("\n== 2. POST /register (valid) ==")
status, location, html = request("POST", "/register", FIELDS, FILES)
check("redirects after submit", status == 303, status)
check("redirect target", location == f"/register/done/{REFERENCE}", location)


print("\n== 3. GET /register/done ==")
status, _, html = request("GET", f"/register/done/{REFERENCE}")
check("done page loads", status == 200, status)
check("shows reference", REFERENCE in html)
check("shows save message", "Save this number to track your application" in html)


print("\n== 4. Database row ==")
conn = sqlite3.connect(BASE_DIR / "sms.db")
row = conn.execute(
    "select reference_no, full_name, phone, department_id, status, "
    "photo_path, marks_memo_path, id_proof_path "
    "from registration where reference_no = ?",
    (REFERENCE,),
).fetchone()
check("row exists", row is not None)
if row:
    check("status pending", row[4] == "pending", row[4])
    check("department saved", row[3] == 1, row[3])
    check(
        "all three paths saved",
        all(row[5:8]),
        row[5:8],
    )


print("\n== 5. Upload files ==")
folder = UPLOADS / REFERENCE
for filename in ("photo.jpg", "marks_memo.pdf", "id_proof.png"):
    path = folder / filename
    check(f"{filename} saved", path.is_file(), path)


print("\n== 6. 5 MB file rejected ==")
big_files = dict(FILES)
big_files["photo"] = ("big.jpg", b"0" * (5 * 1024 * 1024))
status, location, html = request("POST", "/register", FIELDS, big_files)
check("status 400", status == 400, status)
check("size error shown", "must not exceed 2 MB" in html)
check(
    "no extra registration created",
    conn.execute("select count(*) from registration").fetchone()[0] == 1,
)


print("\n== 7. Bad extension rejected ==")
bad_files = dict(FILES)
bad_files["photo"] = ("photo.txt", b"hello")
status, _, html = request("POST", "/register", FIELDS, bad_files)
check("status 400", status == 400, status)
check("extension error shown", "only JPG, JPEG, PNG and PDF" in html)


print("\n== 8. Field validation ==")
bad_phone = dict(FIELDS, phone="12345")
status, _, html = request("POST", "/register", bad_phone, FILES)
check("short phone rejected", status == 400 and "exactly 10 digits" in html)

bad_age = dict(FIELDS, dob="2015-01-01")
status, _, html = request("POST", "/register", bad_age, FILES)
check("under 16 rejected", status == 400 and "at least 16" in html)

bad_percent = dict(FIELDS, tenth_percent="150")
status, _, html = request("POST", "/register", bad_percent, FILES)
check("percentage > 100 rejected", status == 400 and "between 0 and 100" in html)

bad_email = dict(FIELDS, email="not-an-email")
status, _, html = request("POST", "/register", bad_email, FILES)
check("bad email rejected", status == 400 and "valid email" in html)


print("\n== 9. Status lookup ==")
status, _, html = request(
    "POST", "/register/status", {"reference_no": REFERENCE}
)
check("status page loads", status == 200, status)
check("progress shows submitted", "Submitted" in html)
check("progress shows HOD", "With CSE HOD" in html)
check("shows pending label", "waiting for HOD review" in html)

status, _, html = request("GET", f"/register/status?reference_no={REFERENCE}")
check("GET with reference shows result", status == 200 and REFERENCE in html)

status, _, html = request(
    "POST", "/register/status", {"reference_no": "REG-2026-99999"}
)
check("unknown reference shows error", status == 404 and "No application found" in html)


print("\n== 10. Correction + resubmit ==")
conn.execute(
    "update registration set status = 'correction', hod_remarks = ? "
    "where reference_no = ?",
    ("Please attach a clearer marks memo.", REFERENCE),
)
conn.commit()

status, _, html = request("GET", f"/register/status?reference_no={REFERENCE}")
check("correction remarks shown", "clearer marks memo" in html)
check("edit button shown", "Edit and resubmit" in html)

status, _, html = request("GET", f"/register/status/edit/{REFERENCE}")
check("edit form loads", status == 200, status)
check("edit form prefilled", "Test Student" in html)
check("edit shows remarks", "clearer marks memo" in html)

edited = dict(FIELDS, phone="9123456789")
status, location, html = request(
    "POST", f"/register/status/edit/{REFERENCE}", edited, None
)
check("resubmit redirects", status == 303, status)
check(
    "redirect to status result",
    location == f"/register/status?reference_no={REFERENCE}",
    location,
)

row = conn.execute(
    "select phone, status, hod_remarks from registration where reference_no = ?",
    (REFERENCE,),
).fetchone()
check("phone updated", row[0] == "9123456789", row[0])
check("status back to pending", row[1] == "pending", row[1])
check("remarks cleared", row[2] is None, row[2])


print("\n== 11. Approved + roll number ==")
from sqlmodel import Session, select

from app.database import engine
from app.models import (
    Batch,
    Department,
    Registration,
    RegistrationStatus,
    Section,
    Student,
    StudentStatus,
    User,
    Role,
)
from app.security import hash_password

with Session(engine) as session:
    suffix = uuid.uuid4().hex[:6]
    user = User(
        username=f"rolltest-{suffix}@example.com",
        full_name="Test Student",
        email=f"rolltest-{suffix}@example.com",
        password_hash=hash_password("Test@12345"),
        role=Role.student,
        department_id=1,
        created_at=datetime.now(timezone.utc),
    )
    session.add(user)
    session.commit()
    session.refresh(user)

    batch = Batch(department_id=1, start_year=2026, end_year=2030)
    session.add(batch)
    session.commit()
    session.refresh(batch)

    section = Section(
        batch_id=batch.id,
        name="A",
        current_year=1,
        current_semester=1,
    )
    session.add(section)
    session.commit()
    session.refresh(section)

    student = Student(
        user_id=user.id,
        roll_number=f"26CSE{suffix.upper()}",
        full_name="Test Student",
        dob=date(2007, 5, 10),
        gender="Male",
        phone="9123456789",
        email="test.student@example.com",
        parent_name="Test Parent",
        department_id=1,
        batch_id=batch.id,
        section_id=section.id,
        quota="Convener",
        admission_year=2026,
        status=StudentStatus.active,
        created_at=datetime.now(timezone.utc),
    )
    session.add(student)
    session.commit()
    session.refresh(student)

    registration = session.exec(
        select(Registration).where(
            Registration.reference_no == REFERENCE
        )
    ).first()
    registration.status = RegistrationStatus.approved
    registration.student_id = student.id
    session.add(registration)
    session.commit()

    roll_number = student.roll_number

status, _, html = request("GET", f"/register/status?reference_no={REFERENCE}")
check("approved page loads", status == 200, status)
check("approved label shown", "approved" in html.lower())
check("roll number shown", roll_number in html, roll_number)


conn.close()

print("\n----------------------------------")
if failures:
    print(f"{len(failures)} FAILED: {failures}")
    sys.exit(1)

print("All checks passed.")
