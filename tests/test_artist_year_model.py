"""
Tests for the artist×year preference model with ranking metrics,
uncertainty intervals, and leakage-free backtesting.
"""

import pytest

from src.artist_year_model import (
    ArtistYearModel,
    ArtistProfile,
    GlobalYearPreference,
    _weighted_linreg,
    _ndcg_at_k,
    _mean_reciprocal_rank,
    _recall_at_k,
    _precision_at_k,
    _mae,
    _rmse,
    _pearson,
    _check_leakage,
    backtest_artist_year,
    backtest_artist_only,
    backtest_artist_year_vs_artist_only,
)


# ============================================================
# Math helpers
# ============================================================

class TestWeightedLinreg:
    def test_perfect_linear(self):
        xs = [1.0, 2.0, 3.0, 4.0, 5.0]
        ys = [12.0, 14.0, 16.0, 18.0, 20.0]
        slope, intercept, rstd = _weighted_linreg(xs, ys, [1.0]*5, ridge=0.0)
        assert abs(slope - 2.0) < 0.01
        assert abs(intercept - 10.0) < 0.01
        assert rstd < 0.01  # perfect fit → near-zero residual

    def test_single_point(self):
        slope, intercept, rstd = _weighted_linreg([2020.0], [85.0], [1.0])
        assert slope == 0.0
        assert intercept == 85.0

    def test_empty(self):
        slope, intercept, rstd = _weighted_linreg([], [], [])
        assert slope == 0.0

    def test_ridge_pulls_slope_toward_zero(self):
        xs = [1.0, 2.0, 3.0]
        ys = [10.0, 20.0, 30.0]
        slope_no, _, _ = _weighted_linreg(xs, ys, [1.0]*3, ridge=0.0)
        slope_r, _, _ = _weighted_linreg(xs, ys, [1.0]*3, ridge=10.0)
        assert abs(slope_r) < abs(slope_no)


class TestRankingMetrics:
    def test_ndcg_perfect(self):
        """Perfect ranking should give NDCG=1.0."""
        relevance = [100, 95, 90, 85, 80]
        assert abs(_ndcg_at_k(relevance, 5) - 1.0) < 0.01

    def test_ndcg_worst(self):
        """Worst ranking should give low NDCG."""
        relevance = [50, 55, 60, 65, 70]
        score = _ndcg_at_k(relevance, 5)
        assert score < 0.95  # not perfect

    def test_mrr_first_hit(self):
        assert abs(_mean_reciprocal_rank([True, False, False]) - 1.0) < 0.01

    def test_mrr_second_hit(self):
        assert abs(_mean_reciprocal_rank([False, True, False]) - 0.5) < 0.01

    def test_mrr_no_hit(self):
        assert _mean_reciprocal_rank([False, False, False]) == 0.0

    def test_recall_at_k(self):
        relevance = [90, 70, 85, 60, 80]
        # Top-3: [90, 70, 85] — contains 2 of 3 items ≥80
        assert abs(_recall_at_k(relevance, 3, 80.0) - 2/3) < 0.01

    def test_precision_at_k(self):
        relevance = [90, 70, 85, 60, 80]
        # Top-3: [90, 70, 85] — 2 of 3 are ≥80
        assert abs(_precision_at_k(relevance, 3, 80.0) - 2/3) < 0.01


# ============================================================
# Math helpers
# ============================================================

class TestMathHelpers:
    def test_mae(self):
        assert abs(_mae([80, 90], [85, 85]) - 5.0) < 0.01

    def test_rmse(self):
        assert abs(_rmse([80, 90], [85, 85]) - 5.0) < 0.01

    def test_pearson_perfect(self):
        assert abs(_pearson([1, 2, 3], [2, 4, 6]) - 1.0) < 0.01


# ============================================================
# Leakage detection
# ============================================================

class TestLeakageCheck:
    def test_no_leakage_clean_split(self):
        train = [{'artist': 'A', 'year': 2010, 'rating': 80, 'date': '2020-01-01'},
                 {'artist': 'B', 'year': 2015, 'rating': 90, 'date': '2020-06-01'}]
        test = [{'artist': 'C', 'year': 2020, 'rating': 70, 'date': '2021-01-01'}]
        leaked, msg = _check_leakage(train, test)
        assert not leaked
        assert 'No leakage' in msg

    def test_shared_dates_detected(self):
        train = [{'artist': 'A', 'year': 2010, 'rating': 80, 'date': '2020-01-01'}]
        test = [{'artist': 'B', 'year': 2015, 'rating': 90, 'date': '2020-01-01'}]
        leaked, msg = _check_leakage(train, test)
        assert leaked
        assert 'shared review dates' in msg


# ============================================================
# ArtistProfile with uncertainty
# ============================================================

class TestArtistProfile:
    def test_predict_positive_slope(self):
        p = ArtistProfile(
            artist='Test', slope=2.0, intercept=-3920.0,
            mean_rating=80.0, mean_year=2010.0, confidence=0.8,
            data_points=[(2005, 70), (2010, 80), (2015, 90)],
            year_min=2005, year_max=2015,
        )
        assert p.predict(2005) < p.predict(2015)
        assert p.trend == 'improving'

    def test_predict_negative_slope(self):
        p = ArtistProfile(
            artist='Test', slope=-3.0, intercept=6110.0,
            mean_rating=80.0, mean_year=2010.0, confidence=0.8,
            data_points=[(2005, 95), (2010, 80), (2015, 65)],
            year_min=2005, year_max=2015,
        )
        assert p.predict(2005) > p.predict(2015)
        assert p.trend == 'declining'

    def test_predict_clamped(self):
        p = ArtistProfile(
            artist='Test', slope=0.0, intercept=150.0,
            mean_rating=80.0, mean_year=2010.0, confidence=0.8,
            data_points=[(2010, 80)], year_min=2010, year_max=2010,
        )
        assert p.predict(2020) == 100.0

    def test_predict_interval_widens_with_extrapolation(self):
        p = ArtistProfile(
            artist='Test', slope=1.0, intercept=-1930.0,
            residual_std=5.0, mean_rating=80.0, mean_year=2012.0,
            confidence=0.8, data_points=[(2010, 80), (2012, 82), (2014, 84)],
            year_min=2010, year_max=2014,
        )
        lo_in, hi_in = p.predict_interval(2012)
        lo_out, hi_out = p.predict_interval(2030)
        width_in = hi_in - lo_in
        width_out = hi_out - lo_out
        assert width_out > width_in, "Interval should widen for extrapolation"

    def test_predict_interval_widens_with_sparsity(self):
        p_sparse = ArtistProfile(
            artist='A', slope=1.0, intercept=-1930.0,
            residual_std=5.0, mean_rating=80.0, mean_year=2012.0,
            confidence=0.4, data_points=[(2010, 80), (2014, 84)],
            year_min=2010, year_max=2014,
        )
        p_dense = ArtistProfile(
            artist='B', slope=1.0, intercept=-1930.0,
            residual_std=5.0, mean_rating=80.0, mean_year=2012.0,
            confidence=0.9, data_points=[(2010,80),(2011,81),(2012,82),
                                          (2013,83),(2014,84),(2015,85),
                                          (2016,86),(2017,87),(2018,88)],
            year_min=2010, year_max=2018,
        )
        lo_s, hi_s = p_sparse.predict_interval(2012)
        lo_d, hi_d = p_dense.predict_interval(2012)
        assert (hi_s - lo_s) > (hi_d - lo_d), "Sparse artist should have wider interval"


# ============================================================
# ArtistYearModel
# ============================================================

class TestArtistYearModel:
    def _year_fn(self, title):
        import re
        m = re.search(r'\b(20\d{2})\b', title)
        return int(m.group(1)) if m else None

    def test_build_and_predict(self):
        entries = [
            {'artist': 'Band A', 'rating': '90', 'title': 'Song1 (2010)', 'date': '2020-01-01'},
            {'artist': 'Band A', 'rating': '80', 'title': 'Song2 (2015)', 'date': '2020-06-01'},
            {'artist': 'Band A', 'rating': '70', 'title': 'Song3 (2020)', 'date': '2021-01-01'},
        ]
        model = ArtistYearModel()
        model.build(entries, self._year_fn)
        assert 'Band A' in model.artist_profiles
        assert model.predict('Band A', 2010) > model.predict('Band A', 2020)

    def test_predict_with_interval(self):
        entries = [
            {'artist': 'Band A', 'rating': '90', 'title': 'Song1 (2010)', 'date': '2020-01-01'},
            {'artist': 'Band A', 'rating': '80', 'title': 'Song2 (2015)', 'date': '2020-06-01'},
            {'artist': 'Band A', 'rating': '70', 'title': 'Song3 (2020)', 'date': '2021-01-01'},
        ]
        model = ArtistYearModel()
        model.build(entries, self._year_fn)
        pred, (lo, hi) = model.predict_with_interval('Band A', 2015)
        assert lo <= pred <= hi
        assert 0 <= lo <= 100
        assert 0 <= hi <= 100

    def test_unknown_artist_uses_global(self):
        entries = [
            {'artist': 'Known', 'rating': '90', 'title': 'Song (2010)', 'date': '2020-01-01'},
        ]
        model = ArtistYearModel()
        model.build(entries, self._year_fn)
        pred = model.predict('Unknown', 2015)
        assert 0 <= pred <= 100

    def test_summary_includes_interval(self):
        entries = [
            {'artist': 'A', 'rating': '80', 'title': 'X (2010)', 'date': '2020-01-01'},
            {'artist': 'A', 'rating': '90', 'title': 'Y (2015)', 'date': '2021-01-01'},
        ]
        model = ArtistYearModel()
        model.build(entries, self._year_fn)
        summary = model.get_artist_summary()
        assert len(summary) == 1
        assert 'interval_2024' in summary[0]
        assert 'residual_std' in summary[0]


# ============================================================
# Backtest
# ============================================================

class TestBacktest:
    def _make_entries(self, n=100):
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
                'date': f'201{i % 10}-{(i%12)+1:02d}-01',
            })
        return entries

    def _year_fn(self, title):
        import re
        m = re.search(r'\b(20\d{2})\b', title)
        return int(m.group(1)) if m else None

    def test_backtest_artist_year(self):
        result = backtest_artist_year(self._make_entries(100), self._year_fn)
        assert result.train_count > 0
        assert result.test_count > 0
        assert 0 <= result.ndcg_at_5 <= 1.0
        assert 0 <= result.ndcg_at_10 <= 1.0
        assert 0 <= result.mrr <= 1.0

    def test_backtest_artist_only(self):
        result = backtest_artist_only(self._make_entries(100), self._year_fn)
        assert result.model_name == 'artist_only'
        assert result.train_count > 0

    def test_comparison_same_split(self):
        """Both models in the comparison should use identical train/test splits."""
        result = backtest_artist_year_vs_artist_only(self._make_entries(200), self._year_fn)
        assert 'artist_only' in result
        assert 'artist_year' in result
        assert 'delta' in result
        assert result['artist_only']['train_count'] == result['artist_year']['train_count']
        assert result['artist_only']['test_count'] == result['artist_year']['test_count']

    def test_no_leakage_in_comparison(self):
        """The comparison should detect no leakage with synthetic data."""
        result = backtest_artist_year_vs_artist_only(self._make_entries(200), self._year_fn)
        assert not result['leakage']['detected']

    def test_comparison_has_ranking_metrics(self):
        """Both models should have NDCG, MRR, recall, precision."""
        result = backtest_artist_year_vs_artist_only(self._make_entries(200), self._year_fn)
        for key in ('artist_only', 'artist_year'):
            r = result[key]
            for metric in ('ndcg_at_5', 'ndcg_at_10', 'mrr', 'recall_at_10',
                           'precision_at_5', 'precision_at_10'):
                assert metric in r, f"Missing {metric} in {key}"
                assert 0 <= r[metric] <= 1.0, f"{metric} out of range in {key}"

    def test_too_few_entries(self):
        result = backtest_artist_year_vs_artist_only(self._make_entries(5), self._year_fn)
        assert 'error' in result

    def test_year_model_not_dramatically_worse_ndcg(self):
        """Artist+Year NDCG should not be >30% worse than artist-only."""
        result = backtest_artist_year_vs_artist_only(self._make_entries(200), self._year_fn)
        d = result['delta']['ndcg_at_10']
        if d['artist_only'] > 0:
            ratio = d['artist_year'] / d['artist_only']
            assert ratio > 0.7, (
                f"Artist+Year NDCG@10 ({d['artist_year']}) is >30% worse "
                f"than artist-only ({d['artist_only']})"
            )

    def test_split_info_present(self):
        result = backtest_artist_year_vs_artist_only(self._make_entries(200), self._year_fn)
        assert 'split_info' in result
        si = result['split_info']
        assert si['train_count'] > 0
        assert si['test_count'] > 0
        assert si['train_date_range'][0] <= si['train_date_range'][1]
        assert si['test_date_range'][0] <= si['test_date_range'][1]
