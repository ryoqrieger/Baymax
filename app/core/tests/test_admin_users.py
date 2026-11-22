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