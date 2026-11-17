"""Unit tests for core.ml — the model files are replaced by mocks, so these
tests need no database and no .pkl files."""
from unittest import mock

import numpy as np
from django.test import SimpleTestCase

from core import ml


def _fake_scaler():
    scaler = mock.Mock()
    scaler.transform.side_effect = lambda arr: arr
    return scaler


def _fake_model(label=1):
    model = mock.Mock()
    model.predict.return_value = np.array([label])
    return model


class TestPredictLazyLoad(SimpleTestCase):
    """The scaler and SVM are loaded lazily, exactly once."""

    def setUp(self):
        ml._scaler = None
        ml._model = None
        patcher = mock.patch('core.ml.joblib.load')
        self.load = patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(lambda: (setattr(ml, '_scaler', None), setattr(ml, '_model', None)))
        self.scaler, self.model = _fake_scaler(), _fake_model(1)
        self.load.side_effect = lambda path: self.scaler if 'scaler' in str(path) else self.model

    def test_nothing_is_loaded_at_import_time(self):
        self.assertIsNone(ml._scaler)
        self.assertIsNone(ml._model)
        self.load.assert_not_called()

    def test_first_prediction_loads_scaler_and_model(self):
        ml.predict([1] * 26)
        self.assertEqual(self.load.call_count, 2)
        self.assertIs(ml._scaler, self.scaler)
        self.assertIs(ml._model, self.model)

    def test_second_prediction_does_not_reload(self):
        ml.predict([1] * 26)
        ml.predict([2] * 26)
        self.assertEqual(self.load.call_count, 2)

    def test_wrong_answer_count_raises_and_loads_nothing(self):
        for bad in ([1] * 25, [1] * 27, []):
            with self.subTest(length=len(bad)):
                with self.assertRaises(ValueError):
                    ml.predict(bad)
        self.load.assert_not_called()

    def test_returns_the_label_for_each_class(self):
        for code, label in ((0, 'Stable'), (1, 'Challenged'), (2, 'Critical')):
            with self.subTest(label=label):
                self.model.predict.return_value = np.array([code])
                self.assertEqual(ml.predict([1] * 26), label)

    def test_unknown_class_code_falls_back_to_stable(self):
        self.model.predict.return_value = np.array([9])
        self.assertEqual(ml.predict([1] * 26), 'Stable')

    def test_answers_are_scaled_as_one_row_of_26_floats(self):
        ml.predict(list(range(26)))
        (passed,), _ = self.scaler.transform.call_args
        self.assertEqual(passed.shape, (1, 26))
        self.assertEqual(passed.dtype, float)