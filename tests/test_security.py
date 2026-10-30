import os
import re
import tempfile
import unittest
from pathlib import Path


class InsecureVersionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_directory = tempfile.TemporaryDirectory()
        database_path = str(Path(cls.temp_directory.name) / "test.db")
        os.environ["DATABASE_PATH"] = database_path

        import database

        database.DATABASE_PATH = database_path

        import app

        cls.app_module = app
        cls.app = app.app
        cls.app.config.update(TESTING=True)
        app.init_db()

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

    def register(self, email, display_name):
        page = self.client.get("/register")
        response = self.client.post(
            "/register",
            data={
                "csrf_token": self.csrf_token(page),
                "display_name": display_name,
                "email": email,
                "password": "coursework-password-123",
            },
        )
        self.assertEqual(response.status_code, 302)

    def login(self, email):
        page = self.client.get("/login")
        response = self.client.post(
            "/login",
            data={
                "csrf_token": self.csrf_token(page),
                "email": email,
                "password": "coursework-password-123",
            },
        )
        self.assertEqual(response.status_code, 302)

    def make_admin(self, email):
        result = self.app.test_cli_runner().invoke(args=["make-admin", email])
        self.assertEqual(result.exit_code, 0, result.output)

    def test_password_is_stored_and_shown_in_admin_page(self):
        self.register("admin@example.com", "Admin")
        connection = self.app_module.open_database()
        password = connection.execute(
            "SELECT password FROM users WHERE email = ?", ("admin@example.com",)
        ).fetchone()["password"]
        connection.close()
        self.assertEqual(password, "coursework-password-123")

        self.make_admin("admin@example.com")
        self.login("admin@example.com")
        page = self.client.get("/admin/users")
        self.assertEqual(page.status_code, 200)
        self.assertIn(b"Password: coursework-password-123", page.data)

    def test_search_input_changes_the_sql_results(self):
        self.register("member@example.com", "Member")
        self.register("admin@example.com", "Admin")
        self.make_admin("admin@example.com")
        self.login("admin@example.com")

        page = self.client.get("/admin/users?search=%27%20OR%201%3D1%20--")
        self.assertEqual(page.status_code, 200)
        self.assertIn(b"member@example.com", page.data)

    def test_user_content_is_rendered_as_html(self):
        self.register("member@example.com", "Member")
        self.login("member@example.com")
        page = self.client.get("/profile")
        self.client.post(
            "/profile",
            data={
                "csrf_token": self.csrf_token(page),
                "display_name": "Member",
                "biography": "<script>alert(1)</script>",
            },
        )
        page = self.client.get("/profile")
        self.assertIn(b"<script>alert(1)</script>", page.data)

        self.register("admin@example.com", "Admin")
        self.make_admin("admin@example.com")
        self.login("admin@example.com")
        page = self.client.get(
            "/admin/users?search=%3Cimg%20src%3Dx%3E"
            "&notice=%3Cscript%3Ealert(1)%3C%2Fscript%3E"
        )
        self.assertEqual(page.status_code, 200)
        self.assertIn(b"Search results for: <img src=x>", page.data)
        self.assertIn(b".innerHTML = notice ||", page.data)


if __name__ == "__main__":
    unittest.main()
