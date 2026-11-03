import os
import re
import tempfile
import unittest
from pathlib import Path

class ApplicationTests(unittest.TestCase):
    # Create one temporary database for the application test
    @classmethod
    def setUpClass(cls):
        cls.temp_directory = tempfile.TemporaryDirectory()
        # Keep test records separate from the application's normal database
        os.environ["DATABASE_PATH"] = str(Path(cls.temp_directory.name) / "test.db")

        import app

        cls.app_module = app
        cls.app = app.app
        cls.app.config.update(TESTING=True)

    # Remove the temporary database after all application tests finish
    @classmethod
    def tearDownClass(cls):
        cls.temp_directory.cleanup()

    # Clear previous records and create a test client before each test
    def setUp(self):
        connection = self.app_module.open_database()
        with connection:
            # Remove users and events so each test starts from the same state
            connection.execute("DELETE FROM security_events")
            connection.execute("DELETE FROM users")
        connection.close()
        self.client = self.app.test_client()

    # Extract the CSRF token needed for protected form submissions
    def csrf_token(self, response):
        # Forms will need to include the token created when the page was requested
        match = re.search(rb'name="csrf_token" value="([^"]+)"', response.data)
        self.assertIsNotNone(match)
        return match.group(1).decode()

    # Register a user through the application's registration form
    def register(self, email="student@example.com", display_name="Student"):
        page = self.client.get("/register")
        token = self.csrf_token(page)
        # Submit valid form data and return the response for the test to inspect
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

    # Log in a registered user and return login response
    def login(self, email="student@example.com"):
        page = self.client.get("/login")
        # Use the page's CSRF token to imitate a valid browser login
        return self.client.post(
            "/login",
            data={
                "csrf_token": self.csrf_token(page),
                "email": email,
                "password": "correct-horse-battery",
            },
        )

    # Verify a user can register+log in+reach the dashboard
    def test_registration_and_login(self):
        response, _ = self.register()
        # Registration and login need to redirect after succeeding
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.login().status_code, 302)
        # A successful login need to grant access to the dashboard
        self.assertIn(b"Student.", self.client.get("/dashboard").data)

    # Verify an authenticated user can update and reload their profile
    def test_profile_can_be_updated(self):
        self.register()
        self.login()
        page = self.client.get("/profile")
        # Update profile fields and check that the request was successful
        response = self.client.post(
            "/profile",
            data={
                "csrf_token": self.csrf_token(page),
                "display_name": "Updated Student",
                "biography": "A short coursework biography.",
            },
        )
        self.assertEqual(response.status_code, 302)
        # Reload the page to verify the change was saved in the database
        self.assertIn(b"A short coursework biography.", self.client.get("/profile").data)

    # Verify only administrators can access the admin page and events are logged
    def test_admin_page_requires_admin_role(self):
        self.register()
        self.login()
        # A normal authenticated user can't reach administrator features
        self.assertEqual(self.client.get("/admin/users").status_code, 403)

        # Promote the account then confirm the same page becomes available
        result = self.app.test_cli_runner().invoke(
            args=["make-admin", "student@example.com"]
        )
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(self.client.get("/admin/users").status_code, 200)

        # Read the audit log to verify important account actions were recorded
        connection = self.app_module.open_database()
        event_types = [
            row["event_type"]
            for row in connection.execute(
                "SELECT event_type FROM security_events"
            ).fetchall()
        ]
        connection.close()
        self.assertIn("registration", event_types)
        self.assertIn("login_success", event_types)

    # Verify a disabled administrator can't access admin pages
    def test_disabled_admin_cannot_reach_admin_pages(self):
        self.register()
        self.login()
        # First give the user admin privileges so the disabled state is isolated
        result = self.app.test_cli_runner().invoke(
            args=["make-admin", "student@example.com"]
        )
        self.assertEqual(result.exit_code, 0, result.output)

        connection = self.app_module.open_database()
        with connection:
            # Disable the account to test authorisation after deactivation
            connection.execute(
                "UPDATE users SET is_active = 0 WHERE email = ?",
                ("student@example.com",),
            )
        connection.close()

        # A disabled administrator need to be denied even if the session already exists
        self.assertEqual(self.client.get("/admin/users").status_code, 403)

    # Verify protected forms reject requests without a CSRF token
    def test_form_requires_csrf_token(self):
        # Omit the token on purpose to confirm forged form submissions are rejected
        response = self.client.post(
            "/register",
            data={
                "display_name": "Student",
                "email": "student@example.com",
                "password": "correct-horse-battery",
            },
        )
        self.assertEqual(response.status_code, 400)

    # Verify security headers are added and private pages aren't cached
    def test_security_headers_and_cache_control(self):
        response = self.client.get("/login")

        # Check the browser protections were added to normal HTTP responses
        self.assertEqual(
            response.headers["Content-Security-Policy"],
            "default-src 'self'; base-uri 'self'; object-src 'none'; "
            "frame-ancestors 'none'; form-action 'self'",
        )
        self.assertEqual(response.headers["X-Frame-Options"], "DENY")
        self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(
            response.headers["Referrer-Policy"], "strict-origin-when-cross-origin"
        )
        self.assertEqual(
            response.headers["Cache-Control"],
            "no-cache, no-store, must-revalidate",
        )
        self.assertNotIn("Strict-Transport-Security", response.headers)

        # HSTS need to be returned only when the request uses HTTPS
        secure_response = self.client.get("/login", base_url="https://localhost")
        self.assertEqual(
            secure_response.headers["Strict-Transport-Security"],
            "max-age=31536000",
        )

        static_response = self.client.get("/static/css/style.css")
        # Static files will need the cache and MIME-sniffing protection
        self.assertEqual(
            static_response.headers["Cache-Control"],
            "no-cache, no-store, must-revalidate",
        )
        self.assertEqual(static_response.headers["X-Content-Type-Options"], "nosniff")
        static_response.close()


if __name__ == "__main__":
    unittest.main()
