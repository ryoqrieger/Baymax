from django.test import RequestFactory, SimpleTestCase

from core.utils import get_page_range, parse_page, total_pages_for


class PaginationTests(SimpleTestCase):
    def test_small_list_shows_every_page(self):
        self.assertEqual(get_page_range(1, 3), [1, 2, 3])

    def test_single_page(self):
        self.assertEqual(get_page_range(1, 1), [1])

    def test_gaps_on_both_sides(self):
        self.assertEqual(get_page_range(10, 20), [1, None, 8, 9, 10, 11, 12, None, 20])

    def test_near_start_and_end(self):
        self.assertEqual(get_page_range(1, 20), [1, 2, 3, None, 20])
        self.assertEqual(get_page_range(20, 20), [1, None, 18, 19, 20])

    def test_total_pages(self):
        self.assertEqual(total_pages_for(0), 1)
        self.assertEqual(total_pages_for(10), 1)
        self.assertEqual(total_pages_for(11), 2)

    def test_parse_page_is_safe(self):
        rf = RequestFactory()
        for raw, expected in [('3', 3), ('abc', 1), ('0', 1), ('-4', 1), ('', 1), ('2.5', 1)]:
            self.assertEqual(parse_page(rf.get('/', {'page': raw})), expected, raw)
        self.assertEqual(parse_page(rf.get('/')), 1)