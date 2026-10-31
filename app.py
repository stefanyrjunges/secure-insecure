import hmac
import os
import secrets
import sqlite3
from functools import wraps
import click
from flask import Flask, abort, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash
from database import init_db, log_event, open_database

app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.environ.get("SECRET_KEY") or secrets.token_hex(32),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("SESSION_COOKIE_SECURE") == "1",
)

def csrf_token():
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_urlsafe(32)
    return session["csrf_token"]

app.jinja_env.globals["csrf_token"] = csrf_token

def check_csrf_token():
    token = session.get("csrf_token", "")
    submitted_token = request.form.get("csrf_token", "")
    if not token or not hmac.compare_digest(token, submitted_token):
        abort(400)

def login_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return view(*args, **kwargs)

    return wrapped_view

@app.route("/")
def index():
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        check_csrf_token()
        display_name = request.form.get("display_name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if not display_name or len(display_name) > 80:
            flash("Enter a display name of up to 80 characters.")
        elif len(email) > 254 or "@" not in email or " " in email:
            flash("Enter a valid email address.")
        elif len(password) < 12 or len(password) > 128:
            flash("Your password must be between 12 and 128 characters.")
        else:
            connection = open_database()
            try:
                with connection:
                    cursor = connection.execute(
                        """
                        INSERT INTO users (email, password_hash, display_name)
                        VALUES (?, ?, ?)
                        """,
                        (email, generate_password_hash(password), display_name),
                    )
                    log_event(connection, cursor.lastrowid, "registration")
            except sqlite3.IntegrityError:
                flash("An account with that email address already exists.")
            else:
                connection.close()
                flash("Your account has been created. You can now log in.")
                return redirect(url_for("login"))
            connection.close()

    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        check_csrf_token()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        connection = open_database()
        user = connection.execute(
            "SELECT id, password_hash FROM users WHERE email = ? AND is_active = 1",
            (email,),
        ).fetchone()

        if user is None or not check_password_hash(user["password_hash"], password):
            log_event(connection, user["id"] if user else None, "login_failure")
            connection.commit()
            connection.close()
            flash("The email or password is incorrect.")
            return render_template("login.html"), 401

        log_event(connection, user["id"], "login_success")
        connection.commit()
        connection.close()
        session.clear()
        session["user_id"] = user["id"]
        return redirect(url_for("dashboard"))

    return render_template("login.html")

@app.route("/logout", methods=["POST"])
@login_required
def logout():
    check_csrf_token()
    connection = open_database()
    log_event(connection, session["user_id"], "logout")
    connection.commit()
    connection.close()
    session.clear()
    return redirect(url_for("login"))

@app.route("/dashboard")
@login_required
def dashboard():
    connection = open_database()
    user = connection.execute(
        "SELECT display_name, role FROM users WHERE id = ? AND is_active = 1",
        (session["user_id"],),
    ).fetchone()
    connection.close()

    if user is None:
        session.clear()
        return redirect(url_for("login"))

    return render_template(
        "dashboard.html",
        display_name=user["display_name"],
        is_admin=user["role"] == "admin",
    )

@app.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    connection = open_database()
    user = connection.execute(
        "SELECT display_name, biography FROM users WHERE id = ? AND is_active = 1",
        (session["user_id"],),
    ).fetchone()

    if user is None:
        connection.close()
        session.clear()
        return redirect(url_for("login"))

    if request.method == "POST":
        check_csrf_token()
        display_name = request.form.get("display_name", "").strip()
        biography = request.form.get("biography", "").strip()

        if not display_name or len(display_name) > 80:
            flash("Enter a display name of up to 80 characters.")
        elif len(biography) > 500:
            flash("Your biography must be 500 characters or fewer.")
        else:
            with connection:
                connection.execute(
                    "UPDATE users SET display_name = ?, biography = ? WHERE id = ?",
                    (display_name, biography, session["user_id"]),
                )
                log_event(connection, session["user_id"], "profile_updated")
            flash("Your profile has been updated.")
            connection.close()
            return redirect(url_for("profile"))

    connection.close()
    return render_template("profile.html", user=user)

@app.route("/admin/users", methods=["GET", "POST"])
@login_required
def admin_users():
    connection = open_database()
    current_user = connection.execute(
        "SELECT role, is_active FROM users WHERE id = ?",
        (session["user_id"],),
    ).fetchone()

    if current_user is None or current_user["role"] != "admin":
        connection.close()
        abort(403)

    if request.method == "POST":
        check_csrf_token()
        user_id = request.form.get("user_id", type=int)
        if user_id is None or user_id == session["user_id"]:
            connection.close()
            abort(400)

        target = connection.execute(
            "SELECT id, is_active FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        if target is None:
            connection.close()
            abort(404)

        new_status = 0 if target["is_active"] else 1
        with connection:
            connection.execute(
                "UPDATE users SET is_active = ? WHERE id = ?",
                (new_status, user_id),
            )
            log_event(connection, session["user_id"], "user_status_changed")
        flash("The account status has been updated.")
        connection.close()
        return redirect(url_for("admin_users", search=request.args.get("search", "")))

    search = request.args.get("search", "").strip()
    users = connection.execute(
        """
        SELECT id, email, display_name, role, is_active, created_at
        FROM users
        WHERE email LIKE ? OR display_name LIKE ?
        ORDER BY id
        """,
        (f"%{search}%", f"%{search}%"),
    ).fetchall()
    connection.close()
    return render_template("admin.html", users=users, search=search)

@app.cli.command("make-admin")
@click.argument("email")
def make_admin(email):
    """Make an existing account an administrator."""
    connection = open_database()
    user = connection.execute(
        "SELECT id FROM users WHERE email = ?", (email.strip().lower(),)
    ).fetchone()
    if user is None:
        connection.close()
        raise click.ClickException("No account found with that email address.")

    with connection:
        connection.execute("UPDATE users SET role = 'admin' WHERE id = ?", (user["id"],))
        log_event(connection, user["id"], "administrator_role_granted")
    connection.close()
    click.echo("Administrator role granted.")

init_db()

if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1")
