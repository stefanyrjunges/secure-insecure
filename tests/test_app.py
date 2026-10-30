import os
import re
import tempfile
import unittest
from pathlib import Path

class ApplicationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_directory = tempfile.TemporaryDirectory()
        os.environ["DATABASE_PATH"] = str(Path(cls.temp_directory.name) / "test.db")

        import app

        cls.app_module = app
        cls.app = app.app
        cls.app.config.update(TESTING=True)

    @classmethod
    def tearDownClass(cls):
        cls.temp_directory.cleanup()

    def setUp(self):
        connection = self.app_module.open_database()
        with connection:
            connection.execute("DELETE FROM security_events")
            connection.execute("DELETE FROM users")
        connection.close()
        self.client = self.app.test_client()

    def csrf_token(self, response):
        match = re.search(rb'name="csrf_token" value="([^"]+)"', response.data)
        self.assertIsNotNone(match)
        return match.group(1).decode()

    def register(self, email="student@example.com", display_name="Student"):
        page = self.client.get("/register")
        token = self.csrf_token(page)
        response = self.client.post(
            "/register",
            data={
                "csrf_token": token,
                "display_name": display_name,
                "email": email,
                "password": "correct-horse-battery",
            },
        )
        return response, token

    def login(self, email="student@example.com"):
        page = self.client.get("/login")
        return self.client.post(
            "/login",
            data={
                "csrf_token": self.csrf_token(page),
                "email": email,
                "password": "correct-horse-battery",
            },
        )

    def test_registration_and_login(self):
        response, _ = self.register()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.login().status_code, 302)
        self.assertIn(b"Student.", self.client.get("/dashboard").data)

    def test_profile_can_be_updated(self):
        self.register()
        self.login()
        page = self.client.get("/profile")
        response = self.client.post(
            "/profile",
            data={
                "csrf_token": self.csrf_token(page),
                "display_name": "Updated Student",
                "biography": "A short coursework biography.",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn(b"A short coursework biography.", self.client.get("/profile").data)

    def test_admin_page_requires_admin_role(self):
        self.register()
        self.login()
        self.assertEqual(self.client.get("/admin/users").status_code, 403)
        self.assertEqual(self.client.get("/admin/events").status_code, 403)

        result = self.app.test_cli_runner().invoke(
            args=["make-admin", "student@example.com"]
        )
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(self.client.get("/admin/users").status_code, 200)
        events_page = self.client.get("/admin/events")
        self.assertEqual(events_page.status_code, 200)
        self.assertIn(b"registration", events_page.data)
        self.assertIn(b"login_success", events_page.data)

    def test_disabled_admin_cannot_reach_admin_pages(self):
        self.register()
        self.login()
        result = self.app.test_cli_runner().invoke(
            args=["make-admin", "student@example.com"]
        )
        self.assertEqual(result.exit_code, 0, result.output)

        connection = self.app_module.open_database()
        with connection:
            connection.execute(
                "UPDATE users SET is_active = 0 WHERE email = ?",
                ("student@example.com",),
            )
        connection.close()

        self.assertEqual(self.client.get("/admin/users").status_code, 403)
        self.assertEqual(self.client.get("/admin/events").status_code, 403)

    def test_form_requires_csrf_token(self):
        response = self.client.post(
            "/register",
            data={
                "display_name": "Student",
                "email": "student@example.com",
                "password": "correct-horse-battery",
            },
        )
        self.assertEqual(response.status_code, 400)


if __name__ == "__main__":
    unittest.main()
