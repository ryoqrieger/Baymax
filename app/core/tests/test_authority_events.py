"""Tests for the event form validation (no database needed)."""
from datetime import date

from django.http import QueryDict
from django.test import SimpleTestCase

from core.views.authority import clean_event_form

TODAY = date(2026, 11, 21)


def form(**overrides):
    data = {'title': 'Yoga', 'venue': 'Hall 1', 'description': '', 'date': '2026-11-25', 'time': '10:30'}
    data.update(overrides)
    q = QueryDict(mutable=True)
    q.update(data)
    return q


class CleanEventFormTests(SimpleTestCase):
    def test_valid_form(self):
        values, errors = clean_event_form(form(), TODAY)
        self.assertEqual(errors, {})
        self.assertEqual(values['date_value'], date(2026, 11, 25))
        self.assertEqual(values['time_value'].hour, 10)

    def test_today_is_allowed_yesterday_is_not(self):
        self.assertEqual(clean_event_form(form(date='2026-11-21'), TODAY)[1], {})
        self.assertIn('date', clean_event_form(form(date='2026-11-20'), TODAY)[1])

    def test_required_fields_and_whitespace(self):
        _, errors = clean_event_form(form(title='   ', venue='', date='', time=''), TODAY)
        self.assertEqual(set(errors), {'title', 'venue', 'date', 'time'})

    def test_bad_date_and_time_text(self):
        _, errors = clean_event_form(form(date='tomorrow', time='25:99'), TODAY)
        self.assertEqual(set(errors), {'date', 'time'})

    def test_length_limits(self):
        _, errors = clean_event_form(form(title='x' * 201, venue='y' * 201, description='z' * 1001), TODAY)
        self.assertEqual(set(errors), {'title', 'venue', 'description'})
        self.assertEqual(clean_event_form(form(title='x' * 200), TODAY)[1], {})