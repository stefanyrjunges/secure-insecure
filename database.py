import os
import sqlite3


DATABASE_PATH = os.environ.get(
    "DATABASE_PATH",
    os.path.join(os.path.dirname(__file__), "database", "insecure_users.db"),
)


def open_database():
    os.makedirs(os.path.dirname(DATABASE_PATH), exist_ok=True)
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def init_db():
    connection = open_database()
    with connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL UNIQUE,
                password TEXT NOT NULL,
                display_name TEXT NOT NULL,
                biography TEXT NOT NULL DEFAULT '',
                role TEXT NOT NULL DEFAULT 'user',
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            """
        )
    connection.close()
