"""
Shared test fixtures.

The Flask app is instantiated at import time against the real
data/posts_tails.csv. Without isolation, every test that hits an add-song /
batch-add / quick-add route appends rows to the REAL data file, polluting the
user's stats (this previously added ~800 fake rows like
"Test Song (Test Artist, 2024)").

This autouse fixture swaps the app's engine to a throwaway copy of the CSV for
the whole session, then restores the original afterwards.
"""

import os
import shutil
import tempfile

import pytest


@pytest.fixture(scope='session', autouse=True)
def _hermetic_data():
    import app as app_module
    from src.taste_engine import TasteEngine

    real_path = app_module.taste_engine.csv_path
    tmp_dir = tempfile.mkdtemp(prefix='tastespec_data_')
    tmp_path = os.path.join(tmp_dir, 'posts_tails.csv')
    shutil.copy(real_path, tmp_path)

    original_engine = app_module.taste_engine
    app_module.taste_engine = TasteEngine(tmp_path)
    try:
        yield
    finally:
        app_module.taste_engine = original_engine
        shutil.rmtree(tmp_dir, ignore_errors=True)
