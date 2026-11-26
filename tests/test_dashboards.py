"""Tests for role dashboard data, scoping, and access guards."""

import unittest
from datetime import date

from fastapi import HTTPException
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine, select
from starlette.requests import Request

from app.deps import require_role
from app.main import app
from app.models import Role, User
from app.routers.hod import hod_dashboard
from app.routers.management import dashboard as management_dashboard
from app.routers.mentor import mentor_dashboard
from app.routers.student import student_dashboard
from app.routers.trainer import trainer_dashboard
from app.services.dashboard_data import (
    hod_dashboard_data,
    management_dashboard_data,
    mentor_dashboard_data,
    student_dashboard_data,
    trainer_dashboard_data,
)
from app.services.role_menus import build_role_menu
from scripts.seed import seed_demo_data


class DashboardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        seed_demo_data(cls.engine, today=date(2026, 11, 26))

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()

    def get_user(self, session, username):
        return session.exec(
            select(User).where(User.username == username)
        ).first()

    def test_management_metrics_are_database_backed(self):
        with Session(self.engine) as session:
            data = management_dashboard_data(session)

        self.assertEqual(data["total_students"], 500)
        self.assertEqual(data["total_departments"], 5)
        self.assertEqual(data["pending_registrations"], 30)
        self.assertEqual(data["students_per_year"], 125)
        self.assertEqual(len(data["department_rows"]), 5)
        self.assertTrue(
            all(row["student_count"] == 100 for row in data["department_rows"])
        )
        self.assertTrue(
            all(row["pending_count"] == 6 for row in data["department_rows"])
        )

    def test_hod_metrics_are_scoped_to_own_department(self):
        with Session(self.engine) as session:
            cse_hod = self.get_user(session, "hod.cse@college.edu")
            ece_hod = self.get_user(session, "hod.ece@college.edu")
            cse = hod_dashboard_data(session, cse_hod.department_id)
            ece = hod_dashboard_data(session, ece_hod.department_id)

        for data in (cse, ece):
            self.assertEqual(data["student_count"], 100)
            self.assertEqual(data["section_count"], 8)
            self.assertEqual(data["mentor_group_count"], 8)
            self.assertEqual(data["pending_count"], 6)
            self.assertEqual(data["unassigned_sections"], [])

        cse_department_ids = {
            row["section"].id for row in cse["section_rows"]
        }
        ece_department_ids = {
            row["section"].id for row in ece["section_rows"]
        }
        self.assertTrue(cse_department_ids.isdisjoint(ece_department_ids))

    def test_mentor_and_trainer_dashboards_use_their_own_assignments(self):
        with Session(self.engine) as session:
            mentor = self.get_user(session, "mentor.cse.2026a@college.edu")
            mentor_data = mentor_dashboard_data(session, mentor)
            trainer = self.get_user(session, "trainer1@college.edu")
            trainer_data = trainer_dashboard_data(session, trainer)

        self.assertEqual(mentor_data["group"].name, "CSE 2026 A")
        self.assertEqual(mentor_data["student_count"], 13)
        self.assertTrue(
            all(
                student.mentor_group_id == mentor_data["group"].id
                for student in mentor_data["students"]
            )
        )
        self.assertEqual(trainer_data["assignment_count"], 40)
        self.assertTrue(
            all(
                row["assignment"].teacher_user_id == trainer.id
                for row in trainer_data["assignments"]
            )
        )

    def test_student_dashboard_has_expected_profile_and_notice(self):
        with Session(self.engine) as session:
            student_user = self.get_user(session, "26CSE001")
            data = student_dashboard_data(session, student_user)

        self.assertEqual(data["first_name"], "Ravi")
        self.assertEqual(data["student"].roll_number, "26CSE001")
        self.assertEqual(data["department"].code, "CSE")
        self.assertEqual(data["section"].name, "A")
        self.assertEqual(data["mentor_group"].name, "CSE 2026 A")
        self.assertEqual(data["mentor"].username, "mentor.cse.2026a@college.edu")
        self.assertEqual(data["latest_notice"].title, "Library week and mentor meetup")

    def test_each_role_menu_contains_only_that_role(self):
        management_menu = build_role_menu("management")
        hod_menu = build_role_menu("hod")
        student_menu = build_role_menu("student")

        self.assertTrue(all("/management" in item["url"] or "/admin" in item["url"]
                            for item in management_menu))
        self.assertTrue(all(item["url"].startswith("/hod") for item in hod_menu))
        self.assertTrue(all(item["url"].startswith("/student")
                            for item in student_menu))
        self.assertTrue(
            any(item.get("disabled") and item.get("day_label") == "Day 2"
                for item in student_menu)
        )

    def test_role_guard_rejects_a_student_from_another_dashboard(self):
        with Session(self.engine) as session:
            student = self.get_user(session, "26CSE001")
            request = Request(
                {
                    "type": "http",
                    "method": "GET",
                    "path": "/hod",
                    "headers": [],
                    "app": app,
                }
            )
            checker = require_role(Role.hod)
            with self.assertRaises(HTTPException) as raised:
                checker(request, student)

        self.assertEqual(raised.exception.status_code, 403)
        self.assertIn("different role", raised.exception.detail)

    def test_all_role_dashboard_templates_render(self):
        with Session(self.engine) as session:
            request = Request(
                {
                    "type": "http",
                    "method": "GET",
                    "path": "/dashboard-test",
                    "headers": [],
                    "app": app,
                }
            )
            cases = (
                (
                    management_dashboard,
                    "management@college.edu",
                    "management",
                ),
                (hod_dashboard, "hod.cse@college.edu", "hod"),
                (mentor_dashboard, "mentor.cse.2026a@college.edu", "mentor"),
                (trainer_dashboard, "trainer1@college.edu", "trainer"),
                (student_dashboard, "26CSE001", "student_user"),
            )
            for route, username, keyword in cases:
                user = self.get_user(session, username)
                response = route(
                    request=request,
                    session=session,
                    **{keyword: user},
                )
                self.assertEqual(response.status_code, 200)
                self.assertIn(b"GIST SMS", response.body)


if __name__ == "__main__":
    unittest.main()
