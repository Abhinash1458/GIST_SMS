"""Role-specific navigation definitions.

A user only ever receives the menu for their own role. Future-day features
are represented as disabled links so the information architecture is visible
without pretending that the feature is already available.
"""

from __future__ import annotations


ROLE_HOME = {
    "management": "/management",
    "hod": "/hod",
    "mentor": "/mentor",
    "trainer": "/trainer",
    "student": "/student",
}


def _item(
    label: str,
    url: str,
    key: str,
    active: str,
    *,
    badge=None,
    disabled: bool = False,
    day_label: str | None = None,
) -> dict:
    return {
        "label": label,
        "url": url,
        "active": active == key,
        "badge": badge,
        "disabled": disabled,
        "day_label": day_label,
    }


def build_role_menu(
    role: str,
    active: str = "",
    *,
    pending_count: int = 0,
) -> list[dict]:
    """Build the navigation for exactly one role."""
    if role == "management":
        return [
            _item("Dashboard", "/management", "dashboard", active),
            _item("Departments", "/admin/department/list", "departments", active),
            _item("Students", "/admin/student/list", "students", active),
            _item(
                "Registrations",
                "/admin/registration/list",
                "registrations",
                active,
                badge=pending_count or None,
            ),
            _item("Admin screens", "/admin", "admin", active),
        ]

    if role == "hod":
        return [
            _item("Dashboard", "/hod", "dashboard", active),
            _item(
                "Registrations",
                "/hod/registrations",
                "registrations",
                active,
                badge=pending_count or None,
            ),
            _item("Students", "/hod/students", "students", active),
            _item("Mentor groups", "/hod/mentor-groups", "mentor-groups", active),
            _item("Subjects", "/hod/subjects", "subjects", active),
            _item(
                "Leave requests",
                "/hod/leave-requests",
                "leave-requests",
                active,
                disabled=True,
                day_label="Day 2",
            ),
        ]

    if role == "mentor":
        return [
            _item("Dashboard", "/mentor", "dashboard", active),
            _item("My students", "/mentor", "students", active),
            _item(
                "Mark attendance",
                "/mentor",
                "attendance",
                active,
                disabled=True,
                day_label="Day 2",
            ),
        ]

    if role == "trainer":
        return [
            _item("Dashboard", "/trainer", "dashboard", active),
            _item(
                "Teaching assignments",
                "/trainer",
                "assignments",
                active,
            ),
            _item(
                "Enter marks",
                "/trainer",
                "marks",
                active,
                disabled=True,
                day_label="Day 3",
            ),
        ]

    if role == "student":
        return [
            _item("Dashboard", "/student", "dashboard", active),
            _item("My details", "/student", "details", active),
            _item(
                "Attendance",
                "/student",
                "attendance",
                active,
                disabled=True,
                day_label="Day 2",
            ),
            _item(
                "Results",
                "/student",
                "results",
                active,
                disabled=True,
                day_label="Day 3",
            ),
            _item("Notices", "/student", "notices", active),
        ]

    return []
