"""Idempotent schema migration -- runs on every startup."""
import sqlite3
import os


def migrate(db_path: str):
    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    def has_column(table, column):
        c.execute(f"PRAGMA table_info({table})")
        return column in [row[1] for row in c.fetchall()]

    # registrations: add parent_id, payment_status, payment_method, stripe_session_id
    if not has_column("registrations", "parent_id"):
        c.execute("ALTER TABLE registrations ADD COLUMN parent_id INTEGER REFERENCES parents(id)")
    if not has_column("registrations", "payment_status"):
        c.execute("ALTER TABLE registrations ADD COLUMN payment_status TEXT NOT NULL DEFAULT 'unpaid'")
    if not has_column("registrations", "payment_method"):
        c.execute("ALTER TABLE registrations ADD COLUMN payment_method TEXT")
    if not has_column("registrations", "stripe_session_id"):
        c.execute("ALTER TABLE registrations ADD COLUMN stripe_session_id TEXT")

    # rental_bookings: add parent_id, payment_status, payment_method, stripe_session_id
    if not has_column("rental_bookings", "parent_id"):
        c.execute("ALTER TABLE rental_bookings ADD COLUMN parent_id INTEGER REFERENCES parents(id)")
    if not has_column("rental_bookings", "payment_status"):
        c.execute("ALTER TABLE rental_bookings ADD COLUMN payment_status TEXT NOT NULL DEFAULT 'unpaid'")
    if not has_column("rental_bookings", "payment_method"):
        c.execute("ALTER TABLE rental_bookings ADD COLUMN payment_method TEXT")
    if not has_column("rental_bookings", "stripe_session_id"):
        c.execute("ALTER TABLE rental_bookings ADD COLUMN stripe_session_id TEXT")

    conn.commit()
    conn.close()
    print("Schema migrations complete.")


if __name__ == "__main__":
    db_path = os.getenv("DB_PATH", "data/database.db")
    migrate(db_path)
