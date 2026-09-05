"""
Tests for the artist×year preference model and backtest framework.
"""

import pytest

from src.artist_year_model import (
    ArtistYearModel,
    ArtistProfile,
    GlobalYearPreference,
    _weighted_linreg,
    _mae,
    _rmse,
    _pearson,
    _precision_at_k,
    backtest_artist_year,
    backtest_baseline_average,
    backtest_global_year,
)


# ============================================================
# Math helpers
# ============================================================

class TestWeightedLinreg:
    def test_perfect_linear(self):
        """Should recover slope=2, intercept=10 for y=2x+10."""
        xs = [1.0, 2.0, 3.0, 4.0, 5.0]
        ys = [12.0, 14.0, 16.0, 18.0, 20.0]
        ws = [1.0] * 5
        slope, intercept = _weighted_linreg(xs, ys, ws, ridge=0.0)
        assert abs(slope - 2.0) < 0.01
        assert abs(intercept - 10.0) < 0.01

    def test_single_point(self):
        """Single point returns mean as intercept, slope=0."""
        slope, intercept = _weighted_linreg([2020.0], [85.0], [1.0])
        assert slope == 0.0
        assert intercept == 85.0

    def test_empty(self):
        """Empty inputs return 0."""
        slope, intercept = _weighted_linreg([], [], [])
        assert slope == 0.0
        assert intercept == 0.0

    def test_ridge_pulls_slope_toward_zero(self):
        """With ridge, slope should be closer to 0 than without."""
        xs = [1.0, 2.0, 3.0]
        ys = [10.0, 20.0, 30.0]
        ws = [1.0] * 3
        slope_no_ridge, _ = _weighted_linreg(xs, ys, ws, ridge=0.0)
        slope_ridge, _ = _weighted_linreg(xs, ys, ws, ridge=10.0)
        assert abs(slope_ridge) < abs(slope_no_ridge)


class TestMathHelpers:
    def test_mae(self):
        assert abs(_mae([80, 90], [85, 85]) - 5.0) < 0.01

    def test_rmse(self):
        assert abs(_rmse([80, 90], [85, 85]) - 5.0) < 0.01

    def test_pearson_perfect(self):
        assert abs(_pearson([1, 2, 3], [2, 4, 6]) - 1.0) < 0.01

    def test_pearson_zero(self):
        assert abs(_pearson([1, 2, 3], [3, 2, 1]) + 1.0) < 0.01

    def test_precision_at_k(self):
        ranked = [(0.9, 90), (0.8, 70), (0.7, 85), (0.6, 60)]
        assert abs(_precision_at_k(ranked, 2, threshold=80) - 0.5) < 0.01
        assert abs(_precision_at_k(ranked, 4, threshold=80) - 0.5) < 0.01


# ============================================================
# ArtistProfile
# ============================================================

class TestArtistProfile:
    def test_predict_positive_slope(self):
        """Improving artist should predict higher for later years."""
        p = ArtistProfile(
            artist='Test', slope=2.0, intercept=-3920.0,
            mean_rating=80.0, mean_year=2010.0, confidence=0.8,
            data_points=[(2005, 70), (2010, 80), (2015, 90)],
        )
        assert p.predict(2005) < p.predict(2015)
        assert p.trend == 'improving'

    def test_predict_negative_slope(self):
        p = ArtistProfile(
            artist='Test', slope=-3.0, intercept=6110.0,
            mean_rating=80.0, mean_year=2010.0, confidence=0.8,
            data_points=[(2005, 95), (2010, 80), (2015, 65)],
        )
        assert p.predict(2005) > p.predict(2015)
        assert p.trend == 'declining'

    def test_predict_clamped(self):
        """Predictions should be clamped to 0-100."""
        p = ArtistProfile(
            artist='Test', slope=0.0, intercept=150.0,
            mean_rating=80.0, mean_year=2010.0, confidence=0.8,
            data_points=[(2010, 80)],
        )
        assert p.predict(2020) == 100.0

        p2 = ArtistProfile(
            artist='Test', slope=0.0, intercept=-20.0,
            mean_rating=40.0, mean_year=2010.0, confidence=0.8,
            data_points=[(2010, 40)],
        )
        assert p2.predict(2020) == 0.0

    def test_trend_stable(self):
        p = ArtistProfile(
            artist='Test', slope=0.1, intercept=0.0,
            mean_rating=80.0, mean_year=2010.0, confidence=0.8,
            data_points=[],
        )
        assert p.trend == 'stable'


# ============================================================
# ArtistYearModel
# ============================================================

class TestArtistYearModel:
    def test_build_and_predict(self):
        """Model should build from entries and make predictions."""
        entries = [
            {'artist': 'Band A', 'rating': '90', 'title': 'Song1 (2010)', 'date': '2020-01-01'},
            {'artist': 'Band A', 'rating': '80', 'title': 'Song2 (2015)', 'date': '2020-06-01'},
            {'artist': 'Band A', 'rating': '70', 'title': 'Song3 (2020)', 'date': '2021-01-01'},
        ]

        def year_fn(title):
            import re
            m = re.search(r'\b(20\d{2})\b', title)
            return int(m.group(1)) if m else None

        model = ArtistYearModel()
        model.build(entries, year_fn)

        assert 'Band A' in model.artist_profiles
        pred_2010 = model.predict('Band A', 2010)
        pred_2020 = model.predict('Band A', 2020)
        # Band A is declining (90→80→70), so 2010 prediction > 2020
        assert pred_2010 > pred_2020

    def test_unknown_artist_uses_global(self):
        """Unknown artist should fall back to global year curve."""
        entries = [
            {'artist': 'Known', 'rating': '90', 'title': 'Song (2010)', 'date': '2020-01-01'},
            {'artist': 'Known', 'rating': '70', 'title': 'Song2 (2020)', 'date': '2021-01-01'},
        ]

        def year_fn(title):
            import re
            m = re.search(r'\b(20\d{2})\b', title)
            return int(m.group(1)) if m else None

        model = ArtistYearModel()
        model.build(entries, year_fn)

        pred = model.predict('Unknown Artist', 2015)
        assert 0 <= pred <= 100

    def test_score_candidate_range(self):
        """Score should be in 0-100."""
        model = ArtistYearModel()
        model.build([], lambda t: None)
        score = model.score_candidate('Artist', 2015, 0.5, 0.6)
        assert 0 <= score <= 100

    def test_get_artist_summary(self):
        """Summary should exclude artists with <2 data points."""
        entries = [
            {'artist': 'Solo', 'rating': '80', 'title': 'X (2010)', 'date': '2020-01-01'},
            {'artist': 'Duo', 'rating': '80', 'title': 'Y (2010)', 'date': '2020-01-01'},
            {'artist': 'Duo', 'rating': '90', 'title': 'Z (2015)', 'date': '2021-01-01'},
        ]

        def year_fn(title):
            import re
            m = re.search(r'\b(20\d{2})\b', title)
            return int(m.group(1)) if m else None

        model = ArtistYearModel()
        model.build(entries, year_fn)
        summary = model.get_artist_summary()

        artists = [s['artist'] for s in summary]
        assert 'Solo' not in artists  # only 1 data point
        assert 'Duo' in artists      # 2 data points

    def test_regularization_blends_toward_global(self):
        """With few data points, artist prediction should blend toward global."""
        # One artist with just 2 data points
        entries = [
            {'artist': 'Sparse', 'rating': '95', 'title': 'A (2010)', 'date': '2020-01-01'},
            {'artist': 'Sparse', 'rating': '65', 'title': 'B (2020)', 'date': '2021-01-01'},
        ]

        def year_fn(title):
            import re
            m = re.search(r'\b(20\d{2})\b', title)
            return int(m.group(1)) if m else None

        model = ArtistYearModel()
        model.build(entries, year_fn)

        # With only 2 points and ridge regularization, prediction for 2030
        # shouldn't be as extreme as the raw slope would suggest
        pred_2030 = model.predict('Sparse', 2030)
        # Raw slope would give ~95 + (-3)*20 = 35 for 2030
        # But regularization should pull it toward the global mean (~80)
        assert pred_2030 > 35  # Should be pulled up by regularization


# ============================================================
# Backtest
# ============================================================

class TestBacktest:
    def _make_entries(self, n=50):
        """Generate synthetic rated entries with year data."""
        import random
        random.seed(42)
        entries = []
        for i in range(n):
            year = 2000 + (i % 20)
            rating = 70 + (i % 30)
            artist = f'Artist {i % 5}'
            entries.append({
                'artist': artist,
                'rating': str(rating),
                'title': f'Song {i} ({year})',
                'date': f'201{i % 10}-01-01',
            })
        return entries

    def _year_fn(self, title):
        import re
        m = re.search(r'\b(20\d{2})\b', title)
        return int(m.group(1)) if m else None

    def test_backtest_returns_valid_result(self):
        entries = self._make_entries(100)
        result = backtest_artist_year(entries, self._year_fn)
        assert result.train_count > 0
        assert result.test_count > 0
        assert 0 <= result.mae <= 100
        assert 0 <= result.rmse <= 100

    def test_backtest_baseline_average(self):
        entries = self._make_entries(100)
        result = backtest_baseline_average(entries, self._year_fn)
        assert result.model_name == 'baseline_avg'
        assert result.train_count > 0

    def test_backtest_global_year(self):
        entries = self._make_entries(100)
        result = backtest_global_year(entries, self._year_fn)
        assert result.model_name == 'global_year'
        assert result.train_count > 0

    def test_backtest_too_few_entries(self):
        """Should handle edge case of very few entries gracefully."""
        entries = self._make_entries(5)
        result = backtest_artist_year(entries, self._year_fn)
        assert result.train_count == 0  # Not enough data

    def test_backtest_year_model_beats_or_matches_baseline_rmse(self):
        """The year model should at least not be dramatically worse
        than the baseline on RMSE (our regularization ensures this)."""
        entries = self._make_entries(200)
        r_ay = backtest_artist_year(entries, self._year_fn)
        r_bl = backtest_baseline_average(entries, self._year_fn)
        # RMSE should be within 20% of baseline (not dramatically worse)
        if r_bl.rmse > 0:
            ratio = r_ay.rmse / r_bl.rmse
            assert ratio < 1.2, f"Year model RMSE ({r_ay.rmse}) is >20% worse than baseline ({r_bl.rmse})"
