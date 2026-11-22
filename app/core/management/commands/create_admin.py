"""
python manage.py create_admin

Creates an Admin IT account, so you can sign in at /admin/login/ the first time.
It asks for a name, an email and a password (the password is typed hidden).
Options let you skip the questions: --name "..." --email "..."
The password is always asked for here, never passed on the command line.
"""
import getpass

from django.contrib.auth.hashers import make_password
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.core.validators import validate_email

from core.components import ROLE_ADMIN
from core.db import connect_db


class Command(BaseCommand):
    help = 'Create an Admin IT user (asks for the password, never prints it).'

    def add_arguments(self, parser):
        parser.add_argument('--name', help='Full name')
        parser.add_argument('--email', help='Email address (used to sign in)')

    def handle(self, *args, **options):
        name = (options['name'] or input('Full name: ')).strip()
        email = (options['email'] or input('Email: ')).strip().lower()
        if not name:
            raise CommandError('A name is required.')
        try:
            validate_email(email)
        except ValidationError:
            raise CommandError(f'"{email}" is not a valid email address.')

        password = getpass.getpass('Password: ')
        if password != getpass.getpass('Password (again): '):
            raise CommandError('The two passwords do not match.')
        try:
            validate_password(password)
        except ValidationError as exc:
            raise CommandError(' '.join(exc.messages))

        conn = connect_db()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO users (role, full_name, email, password) "
                    "SELECT %s, %s, %s, %s WHERE NOT EXISTS (SELECT 1 FROM users WHERE LOWER(email) = %s) "
                    "RETURNING id",
                    (ROLE_ADMIN, name, email, make_password(password), email),
                )
                created = cur.fetchone()
            conn.commit()
        finally:
            conn.close()

        if created is None:
            raise CommandError(f'An account with the email {email} already exists.')
        self.stdout.write(self.style.SUCCESS(f'Admin IT user created. Sign in at /admin/login/ with {email}.'))