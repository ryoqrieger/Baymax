"""
Database access for Baymax's custom tables (raw psycopg2, no ORM).

This module contains exactly two functions, by architecture rule.
"""
import psycopg2
from django.conf import settings
from psycopg2.extras import RealDictCursor


def connect_db():
    """
    Open a new PostgreSQL connection that returns rows as dictionaries.

    Connection details come from settings.DATABASES['default'], which is built
    from DATABASE_URL (Neon) or the DB_* variables (local) — see settings.py.
    The caller is responsible for closing the connection.
    """
    cfg = settings.DATABASES['default']
    return psycopg2.connect(
        dbname=cfg['NAME'],
        user=cfg['USER'],
        password=cfg['PASSWORD'],
        host=cfg['HOST'],
        port=cfg['PORT'] or None,
        connect_timeout=10,
        cursor_factory=RealDictCursor,
        **cfg.get('OPTIONS', {}),
    )


def get_current_semester(cursor):
    """Return the name of the active semester (e.g. 'Fall 2026'), or None."""
    cursor.execute(
        "SELECT semester FROM semester_schedule WHERE is_current = TRUE LIMIT 1"
    )
    row = cursor.fetchone()
    return row['semester'] if row else None