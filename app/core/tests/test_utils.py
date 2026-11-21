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


class ScoringHelperTests(SimpleTestCase):
    def _answers(self, pss, gad, phq):
        from core.components import QUESTION_COLS
        out = {}
        for column in QUESTION_COLS:
            out[column] = pss if column.startswith('pss') else gad if column.startswith('gad') else phq
        return out

    def test_scores_and_reverse_items(self):
        from core.utils import scale_scores
        scores = {s['scale']: s for s in scale_scores(self._answers(0, 0, 0))}
        self.assertEqual(scores['PSS-10']['total'], 16)       # four reversed items give 4 each
        self.assertEqual(scores['PSS-10']['level'], 'moderate')
        self.assertEqual((scores['GAD-7']['total'], scores['GAD-7']['level']), (0, 'minimal'))
        self.assertEqual(scores['PHQ-9']['max'], 27)

    def test_severe_levels(self):
        from core.utils import scale_scores
        scores = {s['scale']: s for s in scale_scores(self._answers(4, 3, 3))}
        self.assertEqual(scores['GAD-7']['level'], 'severe')
        self.assertEqual(scores['PHQ-9']['level'], 'severe')

    def test_answer_groups_cover_all_26(self):
        from core.utils import answer_groups
        groups = answer_groups(self._answers(1, 1, 1))
        self.assertEqual([len(g['items']) for g in groups], [10, 7, 9])
        self.assertTrue(groups[2]['items'][-1]['flagged'])
        self.assertFalse(any(i['flagged'] for i in answer_groups(self._answers(1, 1, 0))[2]['items']))


class PercentTests(SimpleTestCase):
    def test_percent(self):
        from core.utils import percent
        self.assertEqual(percent(1, 3), 33)
        self.assertEqual(percent(2, 3), 67)
        self.assertEqual(percent(5, 0), 0)
        self.assertEqual(percent(4, 4), 100)


class SemesterPickerTests(SimpleTestCase):
    def test_pick_semester(self):
        from core.utils import pick_semester
        known = ['Fall 2026', 'Summer 2026']
        self.assertEqual(pick_semester('Summer 2026', known, 'Fall 2026'), 'Summer 2026')
        self.assertEqual(pick_semester("x' OR 1=1", known, 'Fall 2026'), 'Fall 2026')
        self.assertEqual(pick_semester(None, known, None), 'Fall 2026')
        self.assertIsNone(pick_semester(None, [], None))

    def test_empty_overview_shape(self):
        from core.utils import semester_overview_empty
        self.assertEqual(semester_overview_empty()['total'], 0)