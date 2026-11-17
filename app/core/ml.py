"""
Machine-learning module: classify 26 questionnaire answers as
Stable / Challenged / Critical with the trained SVM.

The scaler and model are loaded once per process, on the first prediction
(a Singleton), not at import time. Importing this module is therefore cheap
and never touches the files.
"""
import joblib
import numpy as np
from django.conf import settings

_scaler = None   # Singleton — loaded once
_model = None    # Singleton — loaded once
_LABEL_MAP = {0: 'Stable', 1: 'Challenged', 2: 'Critical'}
_ANSWER_COUNT = 26


def _load_models():
    global _scaler, _model
    if _scaler is None or _model is None:
        _scaler = joblib.load(settings.SCALER_PATH)
        _model = joblib.load(settings.SVM_PATH)


def predict(answers: list) -> str:
    """Return 'Stable', 'Challenged' or 'Critical' for 26 numeric answers."""
    if len(answers) != _ANSWER_COUNT:
        raise ValueError(f'Expected {_ANSWER_COUNT} answers, got {len(answers)}')
    _load_models()
    arr = np.array(answers, dtype=float).reshape(1, _ANSWER_COUNT)
    scaled = _scaler.transform(arr)
    raw = _model.predict(scaled)[0]
    return _LABEL_MAP.get(int(raw), 'Stable')