"""Tests for the Admin IT helpers that need no database."""
from django.test import SimpleTestCase

from core.views.admin import _like_pattern


class LikePatternTests(SimpleTestCase):
    def test_plain_text_is_wrapped(self):
        self.assertEqual(_like_pattern('anna'), '%anna%')

    def test_wildcards_typed_by_a_person_are_escaped(self):
        self.assertEqual(_like_pattern('50%'), '%50\\%%')
        self.assertEqual(_like_pattern('a_b'), '%a\\_b%')
        self.assertEqual(_like_pattern('c\\d'), '%c\\\\d%')


class NewUserFormTests(SimpleTestCase):
    def form(self, **overrides):
        from django.http import QueryDict
        data = {'role': 'authority', 'full_name': 'Dr Rina', 'email': ' Rina@Example.com ', 'specialization': ''}
        data.update(overrides)
        q = QueryDict(mutable=True)
        q.update(data)
        return q

    def test_valid_authority(self):
        from core.views.admin import clean_new_user_form
        values, errors = clean_new_user_form(self.form())
        self.assertEqual(errors, {})
        self.assertEqual(values['email'], 'rina@example.com')       # trimmed and lower-cased

    def test_professional_needs_a_specialization(self):
        from core.views.admin import clean_new_user_form
        self.assertIn('specialization', clean_new_user_form(self.form(role='professional'))[1])
        self.assertEqual(clean_new_user_form(self.form(role='professional', specialization='Anxiety'))[1], {})

    def test_students_cannot_be_created_here(self):
        from core.views.admin import clean_new_user_form
        self.assertIn('role', clean_new_user_form(self.form(role='student'))[1])
        self.assertIn('role', clean_new_user_form(self.form(role=''))[1])

    def test_bad_email_and_name(self):
        from core.views.admin import clean_new_user_form
        _, errors = clean_new_user_form(self.form(email='nope', full_name='  '))
        self.assertEqual(set(errors), {'email', 'full_name'})


class PasswordLinkTokenTests(SimpleTestCase):
    def test_round_trip_and_single_use(self):
        from core.utils import make_password_link_token, password_link_matches, read_password_link_token
        token = make_password_link_token(7, '!unusable')
        uid, fp = read_password_link_token(token)
        self.assertEqual(uid, 7)
        self.assertTrue(password_link_matches(fp, '!unusable'))
        self.assertFalse(password_link_matches(fp, 'pbkdf2_sha256$new-hash'))     # password changed -> link dead

    def test_garbage_and_tampered_tokens_are_rejected(self):
        from core.utils import make_password_link_token, read_password_link_token
        self.assertIsNone(read_password_link_token('garbage'))
        self.assertIsNone(read_password_link_token(make_password_link_token(1, 'x') + 'x'))

    def test_expired_token_is_rejected(self):
        from unittest import mock
        from core.utils import make_password_link_token, read_password_link_token
        token = make_password_link_token(1, 'x')
        with mock.patch('core.utils.PASSWORD_LINK_TTL_SECONDS', -1):
            self.assertIsNone(read_password_link_token(token))