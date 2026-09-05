"""
artist_year_model.py — Continuous artist×year preference model

Builds per-artist rating-vs-release-year curves using weighted linear
regression with Tikhonov regularization. For artists with few data
points, blends toward the global year preference curve.

Also provides a backtest harness that trains on older ratings and
predicts newer ones to measure whether year-aware scoring improves
hit rate over a simple artist-average baseline.
"""

import math
import random
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mean(xs: List[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def _weighted_linreg(
    xs: List[float],
    ys: List[float],
    ws: List[float],
    ridge: float = 1.0,
) -> Tuple[float, float]:
    """Weighted linear regression  y = slope * x + intercept  with Tikhonov
    regularization on the slope (pulls toward slope=0, i.e. the global mean).

    Returns (slope, intercept).
    """
    if len(xs) < 2:
        return (0.0, _mean(ys) if ys else 0.0)

    sw = sum(ws)
    swx = sum(w * x for w, x in zip(ws, xs))
    swy = sum(w * y for w, y in zip(ws, ys))
    swxx = sum(w * x * x for w, x in zip(ws, xs))
    swxy = sum(w * x * y for w, x, y in zip(ws, xs, ys))

    mean_x = swx / sw if sw else 0.0
    mean_y = swy / sw if sw else 0.0

    var_x = swxx - sw * mean_x * mean_x
    cov_xy = swxy - sw * mean_x * mean_y

    # Ridge: add penalty to diagonal
    denom = var_x + ridge
    slope = cov_xy / denom if denom != 0 else 0.0
    intercept = mean_y - slope * mean_x

    return (slope, intercept)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class ArtistProfile:
    """Per-artist year preference model."""
    artist: str
    data_points: List[Tuple[int, float]] = field(default_factory=list)  # (year, rating)
    slope: float = 0.0          # rating change per year
    intercept: float = 0.0      # rating at year 0 (meaningless alone)
    mean_rating: float = 0.0    # simple average
    mean_year: float = 0.0      # average release year of rated songs
    confidence: float = 0.0     # 0-1, based on data density

    def predict(self, year: int) -> float:
        """Predict rating for a song from this artist released in `year`."""
        raw = self.slope * year + self.intercept
        return max(0.0, min(100.0, raw))

    @property
    def trend(self) -> str:
        """Human-readable trend label."""
        if abs(self.slope) < 0.3:
            return "stable"
        return "improving" if self.slope > 0 else "declining"


@dataclass
class GlobalYearPreference:
    """Smoothed global rating preference by release year."""
    curve: Dict[int, float] = field(default_factory=dict)  # year → predicted rating
    mean_rating: float = 80.0

    def predict(self, year: int) -> float:
        """Get the global preference score for a given year."""
        return self.curve.get(year, self.mean_rating)


# ---------------------------------------------------------------------------
# Main model
# ---------------------------------------------------------------------------

class ArtistYearModel:
    """Continuous artist×year preference model.

    For each artist with ≥3 rated songs across different years, fits a
    weighted linear regression: rating = slope × year + intercept.

    For artists with 1-2 data points, blends toward the global year curve
    using Tikhonov regularization.

    The global curve itself is a smoothed average across all rated songs
    grouped by release year.
    """

    # Minimum data points to trust an artist's own slope
    MIN_POINTS_FOR_ARTIST_SLOPE = 3
    # Ridge penalty strength (higher = more regularization toward global)
    RIDGE_BASE = 5.0

    def __init__(self):
        self.artist_profiles: Dict[str, ArtistProfile] = {}
        self.global_pref = GlobalYearPreference()
        self._build_complete = False

    def build(self, rated_entries: List[Dict], release_year_fn) -> None:
        """Build the model from rated entries.

        Args:
            rated_entries: list of dicts with 'artist', 'rating', 'title', 'date'
            release_year_fn: callable(title) -> Optional[int] that resolves release year
        """
        # 1. Collect (year, rating) per artist
        artist_data: Dict[str, List[Tuple[int, float]]] = defaultdict(list)
        global_by_year: Dict[int, List[float]] = defaultdict(list)

        for r in rated_entries:
            artist = (r.get('artist') or '').strip()
            if not artist:
                continue
            title = r.get('title', '')
            rating = int(r['rating']) if r.get('rating') else None
            if rating is None:
                continue
            year = release_year_fn(title)
            if year and 1950 <= year <= 2026:
                artist_data[artist].append((year, rating))
                global_by_year[year].append(rating)

        # 2. Build global year preference curve (smoothed)
        self._build_global_curve(global_by_year)

        # 3. Build per-artist profiles
        for artist, points in artist_data.items():
            profile = self._fit_artist(artist, points)
            self.artist_profiles[artist] = profile

        self._build_complete = True

    def _build_global_curve(self, by_year: Dict[int, List[float]]) -> None:
        """Build smoothed global year preference curve using weighted
        moving average with bandwidth = 3 years."""
        if not by_year:
            self.global_pref = GlobalYearPreference(curve={}, mean_rating=80.0)
            return

        all_years = sorted(by_year.keys())
        all_ratings = [r for rs in by_year.values() for r in rs]
        self.global_pref.mean_rating = _mean(all_ratings)

        curve = {}
        bandwidth = 3  # ±3 years window

        for y in all_years:
            window = []
            for dy in range(-bandwidth, bandwidth + 1):
                yr = y + dy
                if yr in by_year:
                    # Weight by inverse distance (closer years matter more)
                    weight = 1.0 / (1.0 + abs(dy))
                    for rating in by_year[yr]:
                        window.append((rating, weight))

            if window:
                total_w = sum(w for _, w in window)
                weighted_avg = sum(r * w for r, w in window) / total_w
                curve[y] = round(weighted_avg, 1)

        self.global_pref.curve = curve

    def _fit_artist(self, artist: str, points: List[Tuple[int, float]]) -> ArtistProfile:
        """Fit a weighted linear regression for one artist.

        Uses review-date recency as weight (newer reviews count more)
        and regularizes toward the global slope when data is sparse.
        """
        years = [y for y, _ in points]
        ratings = [r for _, r in points]
        mean_rating = _mean(ratings)
        mean_year = _mean(years)

        n = len(points)

        # Confidence: log-scaled data density (3→0.5, 10→0.8, 40→0.95)
        confidence = min(1.0, math.log(n + 1) / math.log(41))

        if n < 2:
            return ArtistProfile(
                artist=artist,
                data_points=points,
                slope=0.0,
                intercept=mean_rating,
                mean_rating=mean_rating,
                mean_year=mean_year,
                confidence=confidence,
            )

        # Equal weights per data point (year-level, not review-level)
        ws = [1.0] * n

        # Ridge penalty: stronger when fewer data points
        ridge = self.RIDGE_BASE / max(1.0, n - 1)

        slope, intercept = _weighted_linreg(years, ratings, ws, ridge=ridge)

        return ArtistProfile(
            artist=artist,
            data_points=points,
            slope=slope,
            intercept=intercept,
            mean_rating=mean_rating,
            mean_year=mean_year,
            confidence=confidence,
        )

    def predict(self, artist: str, year: int) -> float:
        """Predict the user's likely rating for a song by `artist`
        released in `year`.

        Blends artist-specific prediction with global year preference
        based on the artist's data confidence.
        """
        profile = self.artist_profiles.get(artist)
        global_pred = self.global_pref.predict(year)

        if profile is None or profile.confidence < 0.1:
            return global_pred

        artist_pred = profile.predict(year)

        # Blend: high confidence → trust artist curve; low → trust global
        alpha = profile.confidence  # 0 = global only, 1 = artist only
        blended = alpha * artist_pred + (1.0 - alpha) * global_pred

        return max(0.0, min(100.0, round(blended, 1)))

    def score_candidate(self, artist: str, year: int,
                        genre_affinity: float = 0.5,
                        acclaim: float = 0.6) -> float:
        """Score a candidate song using year preference + genre + acclaim.

        This is the year-aware replacement for the current scoring formula.
        Returns a 0-100 score.
        """
        year_pref = self.predict(artist, year)
        # Normalize year preference to 0-1
        year_score = year_pref / 100.0
        # Blend: 40% year preference, 30% genre affinity, 30% acclaim
        score = 0.40 * year_score + 0.30 * genre_affinity + 0.30 * acclaim
        return round(score * 100, 1)

    def get_artist_summary(self) -> List[Dict]:
        """Return artist profiles as serializable dicts for the API."""
        result = []
        for artist, p in sorted(
            self.artist_profiles.items(),
            key=lambda x: -x[1].confidence,
        ):
            if len(p.data_points) < 2:
                continue  # Skip artists with too little data
            years = [y for y, _ in p.data_points]
            result.append({
                'artist': artist,
                'slope': round(p.slope, 2),
                'trend': p.trend,
                'mean_rating': round(p.mean_rating, 1),
                'mean_year': round(p.mean_year, 1),
                'year_min': min(years),
                'year_max': max(years),
                'song_count': len(p.data_points),
                'confidence': round(p.confidence, 2),
                'predicted_ratings': {
                    str(y): round(p.predict(y), 1)
                    for y in range(min(years), max(years) + 1)
                },
            })
        return result

    def get_global_curve(self) -> Dict:
        """Return the global year preference curve for the API."""
        return {
            'mean_rating': round(self.global_pref.mean_rating, 1),
            'curve': {str(k): v for k, v in sorted(self.global_pref.curve.items())},
        }


# ---------------------------------------------------------------------------
# Backtest
# ---------------------------------------------------------------------------

@dataclass
class BacktestResult:
    """Results of a backtest run."""
    model_name: str
    train_count: int
    test_count: int
    # Per-prediction accuracy
    mae: float = 0.0           # mean absolute error
    rmse: float = 0.0          # root mean squared error
    correlation: float = 0.0   # Pearson r
    # Ranking quality
    hit_rate_80: float = 0.0   # % of test songs rated ≥80 that model predicted ≥75
    hit_rate_90: float = 0.0   # % of test songs rated ≥90 that model predicted ≥85
    precision_at_5: float = 0.0  # of top-5 predicted, how many are actually ≥80
    precision_at_10: float = 0.0
    # Coverage
    coverage: float = 0.0      # % of test songs the model could predict for


def backtest_artist_year(
    rated_entries: List[Dict],
    release_year_fn,
    train_ratio: float = 0.7,
    seed: int = 42,
) -> BacktestResult:
    """Backtest the artist-year model against historical ratings.

    Strategy: chronological split. Train on the earliest `train_ratio`
    of entries (by review date), predict the rest.

    Returns accuracy metrics comparing predictions to actual ratings.
    """
    # Collect entries with year data
    entries_with_year = []
    for r in rated_entries:
        title = r.get('title', '')
        rating = r.get('rating')
        if not rating:
            continue
        year = release_year_fn(title)
        if year and 1950 <= year <= 2026:
            entries_with_year.append({
                'artist': (r.get('artist') or '').strip(),
                'year': year,
                'rating': int(rating),
                'date': r.get('date', ''),
            })

    if len(entries_with_year) < 20:
        return BacktestResult(model_name='artist_year', train_count=0, test_count=0)

    # Sort by review date (chronological split)
    entries_with_year.sort(key=lambda x: x.get('date', ''))

    split_idx = int(len(entries_with_year) * train_ratio)
    train = entries_with_year[:split_idx]
    test = entries_with_year[split_idx:]

    # Build model on training data only
    # We need to adapt the build method to work with pre-parsed entries
    model = ArtistYearModel()
    _build_model_from_entries(model, train)

    # Predict on test data
    predictions = []
    actuals = []
    for entry in test:
        pred = model.predict(entry['artist'], entry['year'])
        predictions.append(pred)
        actuals.append(entry['rating'])

    if not predictions:
        return BacktestResult(model_name='artist_year', train_count=len(train), test_count=len(test))

    # Compute metrics
    mae = _mae(predictions, actuals)
    rmse = _rmse(predictions, actuals)
    corr = _pearson(predictions, actuals)

    # Hit rate: of test songs rated ≥80, how many did we predict ≥75?
    high_rated = [(p, a) for p, a in zip(predictions, actuals) if a >= 80]
    hit_80 = sum(1 for p, a in high_rated if p >= 75) / len(high_rated) if high_rated else 0.0

    very_high = [(p, a) for p, a in zip(predictions, actuals) if a >= 90]
    hit_90 = sum(1 for p, a in very_high if p >= 85) / len(very_high) if very_high else 0.0

    # Precision@K: of the K highest predicted, how many are actually ≥80?
    ranked = sorted(zip(predictions, actuals), key=lambda x: -x[0])
    prec5 = _precision_at_k(ranked, 5, threshold=80)
    prec10 = _precision_at_k(ranked, 10, threshold=80)

    return BacktestResult(
        model_name='artist_year',
        train_count=len(train),
        test_count=len(test),
        mae=mae,
        rmse=rmse,
        correlation=corr,
        hit_rate_80=hit_80,
        hit_rate_90=hit_90,
        precision_at_5=prec5,
        precision_at_10=prec10,
        coverage=1.0,
    )


def backtest_baseline_average(
    rated_entries: List[Dict],
    release_year_fn,
    train_ratio: float = 0.7,
) -> BacktestResult:
    """Baseline: predict each test song as the artist's average from training.

    This is what the current system effectively does (artist average × genre).
    """
    entries_with_year = []
    for r in rated_entries:
        title = r.get('title', '')
        rating = r.get('rating')
        if not rating:
            continue
        year = release_year_fn(title)
        if year and 1950 <= year <= 2026:
            entries_with_year.append({
                'artist': (r.get('artist') or '').strip(),
                'year': year,
                'rating': int(rating),
                'date': r.get('date', ''),
            })

    if len(entries_with_year) < 20:
        return BacktestResult(model_name='baseline_avg', train_count=0, test_count=0)

    entries_with_year.sort(key=lambda x: x.get('date', ''))
    split_idx = int(len(entries_with_year) * train_ratio)
    train = entries_with_year[:split_idx]
    test = entries_with_year[split_idx:]

    # Build artist averages from training data
    artist_avgs: Dict[str, List[float]] = defaultdict(list)
    global_avg_ratings = []
    for e in train:
        artist_avgs[e['artist']].append(e['rating'])
        global_avg_ratings.append(e['rating'])
    global_avg = _mean(global_avg_ratings)

    artist_means = {a: _mean(rs) for a, rs in artist_avgs.items()}

    predictions = []
    actuals = []
    for entry in test:
        pred = artist_means.get(entry['artist'], global_avg)
        predictions.append(pred)
        actuals.append(entry['rating'])

    if not predictions:
        return BacktestResult(model_name='baseline_avg', train_count=len(train), test_count=len(test))

    mae = _mae(predictions, actuals)
    rmse = _rmse(predictions, actuals)
    corr = _pearson(predictions, actuals)

    high_rated = [(p, a) for p, a in zip(predictions, actuals) if a >= 80]
    hit_80 = sum(1 for p, a in high_rated if p >= 75) / len(high_rated) if high_rated else 0.0

    very_high = [(p, a) for p, a in zip(predictions, actuals) if a >= 90]
    hit_90 = sum(1 for p, a in very_high if p >= 85) / len(very_high) if very_high else 0.0

    ranked = sorted(zip(predictions, actuals), key=lambda x: -x[0])
    prec5 = _precision_at_k(ranked, 5, threshold=80)
    prec10 = _precision_at_k(ranked, 10, threshold=80)

    return BacktestResult(
        model_name='baseline_avg',
        train_count=len(train),
        test_count=len(test),
        mae=mae,
        rmse=rmse,
        correlation=corr,
        hit_rate_80=hit_80,
        hit_rate_90=hit_90,
        precision_at_5=prec5,
        precision_at_10=prec10,
        coverage=1.0,
    )


def backtest_global_year(
    rated_entries: List[Dict],
    release_year_fn,
    train_ratio: float = 0.7,
) -> BacktestResult:
    """Baseline: predict using only the global year preference curve
    (no artist-specific information)."""
    entries_with_year = []
    for r in rated_entries:
        title = r.get('title', '')
        rating = r.get('rating')
        if not rating:
            continue
        year = release_year_fn(title)
        if year and 1950 <= year <= 2026:
            entries_with_year.append({
                'artist': (r.get('artist') or '').strip(),
                'year': year,
                'rating': int(rating),
                'date': r.get('date', ''),
            })

    if len(entries_with_year) < 20:
        return BacktestResult(model_name='global_year', train_count=0, test_count=0)

    entries_with_year.sort(key=lambda x: x.get('date', ''))
    split_idx = int(len(entries_with_year) * train_ratio)
    train = entries_with_year[:split_idx]
    test = entries_with_year[split_idx:]

    # Build global year curve from training data
    by_year: Dict[int, List[float]] = defaultdict(list)
    for e in train:
        by_year[e['year']].append(e['rating'])

    # Smoothed curve
    all_ratings = [r for rs in by_year.values() for r in rs]
    global_mean = _mean(all_ratings)
    curve = {}
    bandwidth = 3
    for y in sorted(by_year.keys()):
        window = []
        for dy in range(-bandwidth, bandwidth + 1):
            yr = y + dy
            if yr in by_year:
                weight = 1.0 / (1.0 + abs(dy))
                for rating in by_year[yr]:
                    window.append((rating, weight))
        if window:
            total_w = sum(w for _, w in window)
            curve[y] = sum(r * w for r, w in window) / total_w

    predictions = []
    actuals = []
    for entry in test:
        pred = curve.get(entry['year'], global_mean)
        predictions.append(pred)
        actuals.append(entry['rating'])

    if not predictions:
        return BacktestResult(model_name='global_year', train_count=len(train), test_count=len(test))

    mae = _mae(predictions, actuals)
    rmse = _rmse(predictions, actuals)
    corr = _pearson(predictions, actuals)

    high_rated = [(p, a) for p, a in zip(predictions, actuals) if a >= 80]
    hit_80 = sum(1 for p, a in high_rated if p >= 75) / len(high_rated) if high_rated else 0.0

    very_high = [(p, a) for p, a in zip(predictions, actuals) if a >= 90]
    hit_90 = sum(1 for p, a in very_high if p >= 85) / len(very_high) if very_high else 0.0

    ranked = sorted(zip(predictions, actuals), key=lambda x: -x[0])
    prec5 = _precision_at_k(ranked, 5, threshold=80)
    prec10 = _precision_at_k(ranked, 10, threshold=80)

    return BacktestResult(
        model_name='global_year',
        train_count=len(train),
        test_count=len(test),
        mae=mae,
        rmse=rmse,
        correlation=corr,
        hit_rate_80=hit_80,
        hit_rate_90=hit_90,
        precision_at_5=prec5,
        precision_at_10=prec10,
        coverage=1.0,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _build_model_from_entries(model: 'ArtistYearModel', entries: List[Dict]) -> None:
    """Build an ArtistYearModel from pre-parsed entries."""
    artist_data: Dict[str, List[Tuple[int, float]]] = defaultdict(list)
    by_year: Dict[int, List[float]] = defaultdict(list)

    for e in entries:
        artist = e['artist']
        year = e['year']
        rating = e['rating']
        artist_data[artist].append((year, rating))
        by_year[year].append(rating)

    model._build_global_curve(by_year)
    for artist, points in artist_data.items():
        model.artist_profiles[artist] = model._fit_artist(artist, points)
    model._build_complete = True


def _mae(preds: List[float], actuals: List[float]) -> float:
    return sum(abs(p - a) for p, a in zip(preds, actuals)) / len(preds) if preds else 0.0


def _rmse(preds: List[float], actuals: List[float]) -> float:
    if not preds:
        return 0.0
    return math.sqrt(sum((p - a) ** 2 for p, a in zip(preds, actuals)) / len(preds))


def _pearson(xs: List[float], ys: List[float]) -> float:
    n = len(xs)
    if n < 2:
        return 0.0
    mx, my = _mean(xs), _mean(ys)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    dy = math.sqrt(sum((y - my) ** 2 for y in ys))
    if dx == 0 or dy == 0:
        return 0.0
    return num / (dx * dy)


def _precision_at_k(ranked: List[Tuple[float, float]], k: int, threshold: float) -> float:
    """Of the top-K predicted, what fraction are actually ≥ threshold?"""
    top_k = ranked[:k]
    if not top_k:
        return 0.0
    hits = sum(1 for _, a in top_k if a >= threshold)
    return hits / len(top_k)
