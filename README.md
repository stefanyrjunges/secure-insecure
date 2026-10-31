# Secure Profile System

A small application using Flask and SQLite to demonstrate secure application development. It includes account registration and login, profile editing and basic administrator user management.

## Requirements

1. Install Python (3.10 or newer)
2. Create and activate a virtual environment:

   ```powershell
   python -m venv .venv
   .venv\Scripts\Activate.ps1
   ```

3. Install Flask:

   ```powershell
   python -m pip install -r requirements.txt
   ```

4. Set a local secret key and start the application. Flask uses the key to sign session cookies to hold login state and CSRF token:

   ```powershell
   $env:SECRET_KEY = python -c "import secrets; print(secrets.token_hex(32))"
   python -m flask --app app run
   ```

5. Open <http://127.0.0.1:5000>.

The SQLite database is created automatically at `database/users.db`.

## Make an administrator

Register an account, then run this command with an email address already registered:

```powershell
python -m flask --app app make-admin user@example.com
```

The application does not include a default administrator account or password, so running this command will promote an existing account.

## Current features

- Account registration with hashed passwords
- Login and logout
- Profile display name and biography editing
- Administrator search and account activation controls
- CSRF checks on forms and basic security event logging

There are two separate secure and insecure versions. The local `secure` and `insecure` branches contain those versions.

## Run and compare both versions

Open PowerShell in the project folder. Install the requirements once, then
follow the steps below for each version. Stop the Flask server with `Ctrl+C`
before switching branches. A running server continues using the code it loaded
when it started, even if Git has switched to another branch.

Run the secure version:

```powershell
git switch secure
git branch --show-current
python -m unittest discover -s tests -v
python -m flask --app app run --host 127.0.0.1 --port 5000
```

Check that the branch command prints `secure`, then open
<http://127.0.0.1:5000> in your browser.

To run the insecure version, first stop the server with `Ctrl+C`, then run:

```powershell
git switch insecure
git branch --show-current
python -m unittest discover -s tests -v
python -m flask --app app run --host 127.0.0.1 --port 5000
```

Check that the branch command prints `insecure`, then open the same address.
The secure and insecure versions use separate database files. Register a
test account on each branch. Use made-up credentials, and keep the insecure
version on your local computer.

If Git will not switch branches because of local changes, save those changes
before switching; do not discard them.

## Development settings

For local HTTP development, leave `SESSION_COOKIE_SECURE` unset.
