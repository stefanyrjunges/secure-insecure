import os
import re
import tempfile
import unittest
from pathlib import Path


class SecureVersionTests(unittest.TestCase):
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
                "password": "correct-horse-battery",
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
                "password": "correct-horse-battery",
            },
        )
        self.assertEqual(response.status_code, 302)

    def make_admin(self, email):
        result = self.app.test_cli_runner().invoke(args=["make-admin", email])
        self.assertEqual(result.exit_code, 0, result.output)

    def test_password_is_hashed_and_not_shown_to_admin(self):
        self.register("admin@example.com", "Admin")
        connection = self.app_module.open_database()
        password_hash = connection.execute(
            "SELECT password_hash FROM users WHERE email = ?",
            ("admin@example.com",),
        ).fetchone()["password_hash"]
        connection.close()
        self.assertNotEqual(password_hash, "correct-horse-battery")

        self.make_admin("admin@example.com")
        self.login("admin@example.com")
        page = self.client.get("/admin/users")
        self.assertEqual(page.status_code, 200)
        self.assertNotIn(b"correct-horse-battery", page.data)
        self.assertNotIn(b"Password:", page.data)

    def test_search_does_not_interpret_sql(self):
        self.register("member@example.com", "Member")
        self.register("admin@example.com", "Admin")
        self.make_admin("admin@example.com")
        self.login("admin@example.com")

        page = self.client.get("/admin/users?search=%27%20OR%201%3D1%20--")
        self.assertEqual(page.status_code, 200)
        self.assertIn(b"No users found.", page.data)
        self.assertNotIn(b"member@example.com", page.data)

    def test_user_content_is_escaped_and_dom_output_is_safe(self):
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
        self.assertIn(b"&lt;script&gt;alert(1)&lt;/script&gt;", page.data)
        self.assertNotIn(b"<script>alert(1)</script>", page.data)

        self.register("admin@example.com", "Admin")
        self.make_admin("admin@example.com")
        self.login("admin@example.com")
        page = self.client.get(
            "/admin/users?search=%3Cscript%3Ealert(1)%3C%2Fscript%3E"
            "&notice=%3Cscript%3Ealert(1)%3C%2Fscript%3E"
        )
        self.assertEqual(page.status_code, 200)
        self.assertIn(b".textContent = notice ||", page.data)
        self.assertNotIn(b"Search results for: <script>", page.data)
        self.assertNotIn(b".innerHTML = notice", page.data)


if __name__ == "__main__":
    unittest.main()
