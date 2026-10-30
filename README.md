# Secure Profile System

A small Flask and SQLite application for demonstrating secure application
development. It includes account registration and login, profile editing, and
basic administrator user management.

## Run locally

1. Install Python 3.10 or newer.
2. Create and activate a virtual environment:

   ```powershell
   python -m venv .venv
   .venv\Scripts\Activate.ps1
   ```

3. Install Flask:

   ```powershell
   python -m pip install -r requirements.txt
   ```

4. Set a local secret key and start the application:

   ```powershell
   $env:SECRET_KEY = python -c "import secrets; print(secrets.token_hex(32))"
   python -m flask --app app run
   ```

5. Open <http://127.0.0.1:5000>.

The SQLite database is created automatically at
`database/insecure_users.db`. It is local application data and should not be
committed.

## Make an administrator

Register an account, then run this command with its email address:

```powershell
python -m flask --app app make-admin user@example.com
```

The command promotes an existing account; the application does not include a
default administrator account or password.

## Current features

- Account registration with plaintext passwords in this demonstration branch
- Login and logout
- Profile display name and biography editing
- Administrator search and account activation controls
- CSRF checks on forms and basic security event logging

The assignment requires separate secure and insecure versions, maintained on
the local `secure` and `insecure` branches. This branch deliberately
demonstrates SQL injection, reflected/DOM/stored XSS, and plaintext password
exposure. Use only local test data; do not expose this version to the internet
or use real credentials. It uses `database/insecure_users.db` so its schema
stays separate from the secure branch's local database.

## Development settings

For local HTTP development, leave `SESSION_COOKIE_SECURE` unset. Set it to `1`
only when serving the application over HTTPS. Do not enable Flask debug mode on
an untrusted network.

## Run the tests

The basic application tests use Python's built-in `unittest` module:

```powershell
python -m unittest discover -s tests -v
```
