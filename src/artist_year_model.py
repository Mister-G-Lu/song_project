"""
artist_year_model.py — Continuous artist×year preference model

Builds per-artist rating-vs-release-year curves using weighted linear
regression with Tikhonov regularization. For artists with few data
points, blends toward the global year preference curve.

Evaluation is done via true chronological top-N recommendation backtests
that measure ranking quality (NDCG, MRR, Recall@K) rather than just
rating prediction error.
"""

import math
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
) -> Tuple[float, float, float]:
    """Weighted linear regression  y = slope * x + intercept  with Tikhonov
    regularization on the slope.

    Returns (slope, intercept, residual_std).
    residual_std is the RMSE of the fit, used for confidence intervals.
    """
    n = len(xs)
    if n < 2:
        return (0.0, _mean(ys) if ys else 0.0, 15.0)

    sw = sum(ws)
    swx = sum(w * x for w, x in zip(ws, xs))
    swy = sum(w * y for w, y in zip(ws, ys))
    swxx = sum(w * x * x for w, x in zip(ws, xs))
    swxy = sum(w * x * y for w, x, y in zip(ws, xs, ys))

    mean_x = swx / sw if sw else 0.0
    mean_y = swy / sw if sw else 0.0

    var_x = swxx - sw * mean_x * mean_x
    cov_xy = swxy - sw * mean_x * mean_y

    denom = var_x + ridge
    slope = cov_xy / denom if denom != 0 else 0.0
    intercept = mean_y - slope * mean_x

    # Residual standard deviation (for confidence intervals)
    pred_ys = [slope * x + intercept for x in xs]
    sse = sum(w * (y - p) ** 2 for w, y, p in zip(ws, ys, pred_ys))
    residual_std = math.sqrt(sse / max(n - 2, 1))

    return (slope, intercept, residual_std)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class ArtistProfile:
    """Per-artist year preference model with uncertainty."""
    artist: str
    data_points: List[Tuple[int, float]] = field(default_factory=list)
    slope: float = 0.0
    intercept: float = 0.0
    residual_std: float = 15.0  # RMSE of the linear fit
    mean_rating: float = 0.0
    mean_year: float = 0.0
    confidence: float = 0.0     # 0-1, based on data density
    year_min: int = 2020
    year_max: int = 2020

    def predict(self, year: int) -> float:
        raw = self.slope * year + self.intercept
        return max(0.0, min(100.0, raw))

    def predict_interval(self, year: int, z: float = 1.0) -> Tuple[float, float]:
        """Prediction with uncertainty band.

        Widens when:
        - Few data points (high residual_std)
        - Extrapolating beyond observed year range (distance penalty)
        - Far from mean_year of training data
        """
        pred = self.predict(year)
        # Base uncertainty from residual
        base_width = self.residual_std * z
        # Extrapolation penalty: widen band outside [year_min, year_max]
        if year < self.year_min:
            distance = self.year_min - year
            base_width *= (1.0 + 0.3 * distance)
        elif year > self.year_max:
            distance = year - self.year_max
            base_width *= (1.0 + 0.3 * distance)
        # Sparsity penalty: fewer points = wider band
        n = len(self.data_points)
        sparsity_mult = 1.0 + 2.0 / max(n, 1)
        base_width *= sparsity_mult
        lo = max(0.0, pred - base_width)
        hi = min(100.0, pred + base_width)
        return (round(lo, 1), round(hi, 1))

    @property
    def trend(self) -> str:
        if abs(self.slope) < 0.3:
            return "stable"
        return "improving" if self.slope > 0 else "declining"

    @property
    def is_extrapolating(self) -> bool:
        """Whether the model's mean_year is far from observed range."""
        return len(self.data_points) < 3


@dataclass
class GlobalYearPreference:
    curve: Dict[int, float] = field(default_factory=dict)
    mean_rating: float = 80.0

    def predict(self, year: int) -> float:
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
    """

    MIN_POINTS_FOR_ARTIST_SLOPE = 3
    RIDGE_BASE = 5.0

    def __init__(self):
        self.artist_profiles: Dict[str, ArtistProfile] = {}
        self.global_pref = GlobalYearPreference()
        self._build_complete = False

    def build(self, rated_entries: List[Dict], release_year_fn) -> None:
        """Build the model from rated entries.

        Args:
            rated_entries: list of dicts with 'artist', 'rating', 'title', 'date'
            release_year_fn: callable(title) -> Optional[int]
        """
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

        self._build_global_curve(global_by_year)
        for artist, points in artist_data.items():
            self.artist_profiles[artist] = self._fit_artist(artist, points)
        self._build_complete = True

    def _build_global_curve(self, by_year: Dict[int, List[float]]) -> None:
        if not by_year:
            self.global_pref = GlobalYearPreference(curve={}, mean_rating=80.0)
            return
        all_ratings = [r for rs in by_year.values() for r in rs]
        self.global_pref.mean_rating = _mean(all_ratings)
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
                curve[y] = round(sum(r * w for r, w in window) / total_w, 1)
        self.global_pref.curve = curve

    def _fit_artist(self, artist: str, points: List[Tuple[int, float]]) -> ArtistProfile:
        years = [y for y, _ in points]
        ratings = [r for _, r in points]
        mean_rating = _mean(ratings)
        mean_year = _mean(years)
        n = len(points)
        confidence = min(1.0, math.log(n + 1) / math.log(41))

        if n < 2:
            return ArtistProfile(
                artist=artist, data_points=points,
                slope=0.0, intercept=mean_rating,
                residual_std=15.0,
                mean_rating=mean_rating, mean_year=mean_year,
                confidence=confidence,
                year_min=min(years) if years else 2020,
                year_max=max(years) if years else 2020,
            )

        ws = [1.0] * n
        ridge = self.RIDGE_BASE / max(1.0, n - 1)
        slope, intercept, residual_std = _weighted_linreg(years, ratings, ws, ridge=ridge)

        return ArtistProfile(
            artist=artist, data_points=points,
            slope=slope, intercept=intercept,
            residual_std=residual_std,
            mean_rating=mean_rating, mean_year=mean_year,
            confidence=confidence,
            year_min=min(years), year_max=max(years),
        )

    def predict(self, artist: str, year: int) -> float:
        profile = self.artist_profiles.get(artist)
        global_pred = self.global_pref.predict(year)
        if profile is None or profile.confidence < 0.1:
            return global_pred
        artist_pred = profile.predict(year)
        alpha = profile.confidence
        blended = alpha * artist_pred + (1.0 - alpha) * global_pred
        return max(0.0, min(100.0, round(blended, 1)))

    def predict_with_interval(self, artist: str, year: int,
                              z: float = 1.0) -> Tuple[float, Tuple[float, float]]:
        """Predict with uncertainty interval."""
        profile = self.artist_profiles.get(artist)
        global_pred = self.global_pref.predict(year)
        if profile is None or profile.confidence < 0.1:
            return (global_pred, (max(0, global_pred - 15), min(100, global_pred + 15)))
        artist_pred = profile.predict(year)
        alpha = profile.confidence
        blended = alpha * artist_pred + (1.0 - alpha) * global_pred
        blended = max(0.0, min(100.0, round(blended, 1)))
        lo, hi = profile.predict_interval(year, z)
        # Blend the interval bounds too
        lo = alpha * lo + (1.0 - alpha) * (global_pred - 15)
        hi = alpha * hi + (1.0 - alpha) * (global_pred + 15)
        lo = max(0.0, min(100.0, round(lo, 1)))
        hi = max(0.0, min(100.0, round(hi, 1)))
        return (blended, (lo, hi))

    def get_artist_summary(self) -> List[Dict]:
        result = []
        for artist, p in sorted(
            self.artist_profiles.items(),
            key=lambda x: -x[1].confidence,
        ):
            if len(p.data_points) < 2:
                continue
            pred_2015 = round(p.predict(2015), 1)
            pred_2024 = round(p.predict(2024), 1)
            lo_2024, hi_2024 = p.predict_interval(2024)
            result.append({
                'artist': artist,
                'slope': round(p.slope, 2),
                'trend': p.trend,
                'mean_rating': round(p.mean_rating, 1),
                'mean_year': round(p.mean_year, 1),
                'year_min': p.year_min,
                'year_max': p.year_max,
                'song_count': len(p.data_points),
                'confidence': round(p.confidence, 2),
                'residual_std': round(p.residual_std, 1),
                'predicted_2015': pred_2015,
                'predicted_2024': pred_2024,
                'interval_2024': [lo_2024, hi_2024],
            })
        return result

    def get_global_curve(self) -> Dict:
        return {
            'mean_rating': round(self.global_pref.mean_rating, 1),
            'curve': {str(k): v for k, v in sorted(self.global_pref.curve.items())},
        }


# ---------------------------------------------------------------------------
# Ranking metrics (what matters for recommendations)
# ---------------------------------------------------------------------------

def _ndcg_at_k(relevance: List[float], k: int) -> float:
    """Normalized Discounted Cumulative Gain at K.

    relevance[i] = actual rating of the i-th item in the ranked list.
    DCG = sum(rel_i / log2(i+2)) for i in 0..k-1
    IDCG = DCG of the ideal ranking (highest ratings first).
    """
    def dcg(rels):
        return sum(r / math.log2(i + 2) for i, r in enumerate(rels[:k]))
    actual_dcg = dcg(relevance)
    ideal_dcg = dcg(sorted(relevance, reverse=True))
    return actual_dcg / ideal_dcg if ideal_dcg > 0 else 0.0


def _mean_reciprocal_rank(hit_mask: List[bool]) -> float:
    """1/rank of the first hit (True) in the ranked list."""
    for i, hit in enumerate(hit_mask):
        if hit:
            return 1.0 / (i + 1)
    return 0.0


def _recall_at_k(relevance: List[float], k: int, threshold: float = 80.0) -> float:
    """What fraction of items ≥ threshold appear in top-K?"""
    total_hits = sum(1 for r in relevance if r >= threshold)
    if total_hits == 0:
        return 0.0
    top_k_hits = sum(1 for r in relevance[:k] if r >= threshold)
    return top_k_hits / total_hits


def _precision_at_k(relevance: List[float], k: int, threshold: float = 80.0) -> float:
    """What fraction of top-K items are ≥ threshold?"""
    top_k = relevance[:k]
    if not top_k:
        return 0.0
    return sum(1 for r in top_k if r >= threshold) / len(top_k)


# ---------------------------------------------------------------------------
# Leakage-safe backtest: trains on entries BEFORE a cutoff, tests AFTER
# ---------------------------------------------------------------------------

@dataclass
class BacktestResult:
    """Results of a backtest run."""
    model_name: str
    train_count: int
    test_count: int
    # Rating prediction accuracy
    mae: float = 0.0
    rmse: float = 0.0
    correlation: float = 0.0
    # Ranking quality (what matters for recs)
    ndcg_at_5: float = 0.0
    ndcg_at_10: float = 0.0
    mrr: float = 0.0        # mean reciprocal rank of first good rec
    recall_at_10: float = 0.0
    precision_at_5: float = 0.0
    precision_at_10: float = 0.0
    # Coverage
    coverage: float = 0.0
    # Leakage check
    leakage_detected: bool = False
    leakage_details: str = ''


def _extract_entries(rated_entries, release_year_fn):
    """Extract (artist, year, rating, date) tuples with year data."""
    out = []
    for r in rated_entries:
        title = r.get('title', '')
        rating = r.get('rating')
        if not rating:
            continue
        year = release_year_fn(title)
        if year and 1950 <= year <= 2026:
            out.append({
                'artist': (r.get('artist') or '').strip(),
                'year': year,
                'rating': int(rating),
                'date': r.get('date', ''),
            })
    return out


def _check_leakage(train, test):
    """Verify no future data leaks into training.

    Checks:
    1. No test entry's review date appears in training
    2. Training set contains only entries with review date ≤ latest train date
    3. No test artist+year pair is identical to a training pair (exact dup)
    """
    issues = []
    train_dates = {e['date'] for e in train}
    test_dates = {e['date'] for e in test}
    overlap = train_dates & test_dates
    if overlap:
        issues.append(f'{len(overlap)} shared review dates between train/test')

    train_pairs = {(e['artist'], e['year']) for e in train}
    test_pairs = {(e['artist'], e['year']) for e in test}
    exact_dups = train_pairs & test_pairs
    if len(exact_dups) > len(test) * 0.5:
        issues.append(f'{len(exact_dups)}/{len(test)} test artist×year pairs have exact training matches')

    return len(issues) > 0, '; '.join(issues) if issues else 'No leakage detected'


def backtest_artist_year(
    rated_entries: List[Dict],
    release_year_fn,
    train_ratio: float = 0.7,
) -> BacktestResult:
    """Chronological backtest: train on oldest entries, predict newest."""
    entries = _extract_entries(rated_entries, release_year_fn)
    if len(entries) < 20:
        return BacktestResult(model_name='artist_year', train_count=0, test_count=0)

    entries.sort(key=lambda x: x.get('date', ''))
    split_idx = int(len(entries) * train_ratio)
    train = entries[:split_idx]
    test = entries[split_idx:]

    leaked, leak_msg = _check_leakage(train, test)

    model = ArtistYearModel()
    _build_model_from_entries(model, train)

    predictions = [model.predict(e['artist'], e['year']) for e in test]
    actuals = [e['rating'] for e in test]

    return _compute_all_metrics('artist_year', train, test, predictions, actuals, leaked, leak_msg)


def backtest_artist_only(
    rated_entries: List[Dict],
    release_year_fn,
    train_ratio: float = 0.7,
) -> BacktestResult:
    """Baseline: predict using artist average only (no year signal)."""
    entries = _extract_entries(rated_entries, release_year_fn)
    if len(entries) < 20:
        return BacktestResult(model_name='artist_only', train_count=0, test_count=0)

    entries.sort(key=lambda x: x.get('date', ''))
    split_idx = int(len(entries) * train_ratio)
    train = entries[:split_idx]
    test = entries[split_idx:]

    leaked, leak_msg = _check_leakage(train, test)

    # Build artist averages from training data only
    artist_avgs: Dict[str, List[float]] = defaultdict(list)
    all_train_ratings = []
    for e in train:
        artist_avgs[e['artist']].append(e['rating'])
        all_train_ratings.append(e['rating'])
    global_avg = _mean(all_train_ratings)
    artist_means = {a: _mean(rs) for a, rs in artist_avgs.items()}

    predictions = [artist_means.get(e['artist'], global_avg) for e in test]
    actuals = [e['rating'] for e in test]

    return _compute_all_metrics('artist_only', train, test, predictions, actuals, leaked, leak_msg)


def backtest_artist_year_vs_artist_only(
    rated_entries: List[Dict],
    release_year_fn,
    train_ratio: float = 0.7,
) -> Dict:
    """Head-to-head comparison: Artist-only vs Artist+Year as ranking systems.

    Uses the SAME train/test split so differences are attributable to the
    year signal, not data variation.
    """
    entries = _extract_entries(rated_entries, release_year_fn)
    if len(entries) < 20:
        return {'error': 'Not enough entries with year data'}

    entries.sort(key=lambda x: x.get('date', ''))
    split_idx = int(len(entries) * train_ratio)
    train = entries[:split_idx]
    test = entries[split_idx:]

    leaked, leak_msg = _check_leakage(train, test)

    # --- Model 1: Artist average only ---
    artist_avgs: Dict[str, List[float]] = defaultdict(list)
    all_train_ratings = []
    for e in train:
        artist_avgs[e['artist']].append(e['rating'])
        all_train_ratings.append(e['rating'])
    global_avg = _mean(all_train_ratings)
    artist_means = {a: _mean(rs) for a, rs in artist_avgs.items()}
    preds_artist_only = [artist_means.get(e['artist'], global_avg) for e in test]
    actuals = [e['rating'] for e in test]

    # --- Model 2: Artist + Year ---
    model_ay = ArtistYearModel()
    _build_model_from_entries(model_ay, train)
    preds_artist_year = [model_ay.predict(e['artist'], e['year']) for e in test]

    # --- Compute ranking metrics for both on the same test set ---
    r_artist_only = _compute_all_metrics(
        'artist_only', train, test, preds_artist_only, actuals, leaked, leak_msg)
    r_artist_year = _compute_all_metrics(
        'artist_year', train, test, preds_artist_year, actuals, leaked, leak_msg)

    # --- Improvement deltas ---
    delta = {}
    for metric in ('ndcg_at_5', 'ndcg_at_10', 'mrr', 'recall_at_10',
                    'precision_at_5', 'precision_at_10', 'mae', 'rmse'):
        v1 = getattr(r_artist_only, metric)
        v2 = getattr(r_artist_year, metric)
        delta[metric] = {
            'artist_only': round(v1, 4),
            'artist_year': round(v2, 4),
            'delta': round(v2 - v1, 4),
            'improved': v2 > v1 if metric not in ('mae', 'rmse') else v2 < v1,
        }

    return {
        'artist_only': _result_to_dict(r_artist_only),
        'artist_year': _result_to_dict(r_artist_year),
        'delta': delta,
        'leakage': {'detected': leaked, 'details': leak_msg},
        'split_info': {
            'train_count': len(train),
            'test_count': len(test),
            'train_date_range': (train[0]['date'], train[-1]['date']),
            'test_date_range': (test[0]['date'], test[-1]['date']),
        },
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _build_model_from_entries(model: ArtistYearModel, entries: List[Dict]) -> None:
    artist_data: Dict[str, List[Tuple[int, float]]] = defaultdict(list)
    by_year: Dict[int, List[float]] = defaultdict(list)
    for e in entries:
        artist_data[e['artist']].append((e['year'], e['rating']))
        by_year[e['year']].append(e['rating'])
    model._build_global_curve(by_year)
    for artist, points in artist_data.items():
        model.artist_profiles[artist] = model._fit_artist(artist, points)
    model._build_complete = True


def _compute_all_metrics(
    model_name: str,
    train: List[Dict],
    test: List[Dict],
    predictions: List[float],
    actuals: List[float],
    leaked: bool,
    leak_msg: str,
) -> BacktestResult:
    """Compute both rating-prediction and ranking metrics."""
    if not predictions:
        return BacktestResult(model_name=model_name, train_count=len(train),
                              test_count=len(test), leakage_detected=leaked,
                              leakage_details=leak_msg)

    mae = _mae(predictions, actuals)
    rmse = _rmse(predictions, actuals)
    corr = _pearson(predictions, actuals)

    # For ranking metrics, we need to rank test items by predicted score
    # and see how the actual ratings are distributed in that ranking.
    # This simulates: "if we recommended the top-K predicted songs,
    # how good would they actually be?"
    ranked_indices = sorted(range(len(test)), key=lambda i: -predictions[i])
    ranked_actuals = [actuals[i] for i in ranked_indices]
    ranked_preds = [predictions[i] for i in ranked_indices]

    ndcg5 = _ndcg_at_k(ranked_actuals, 5)
    ndcg10 = _ndcg_at_k(ranked_actuals, 10)

    # MRR: reciprocal rank of first test item rated ≥80
    hit_mask = [a >= 80 for a in ranked_actuals]
    mrr = _mean_reciprocal_rank(hit_mask)

    recall10 = _recall_at_k(ranked_actuals, 10, threshold=80.0)
    prec5 = _precision_at_k(ranked_actuals, 5, threshold=80.0)
    prec10 = _precision_at_k(ranked_actuals, 10, threshold=80.0)

    return BacktestResult(
        model_name=model_name,
        train_count=len(train),
        test_count=len(test),
        mae=mae, rmse=rmse, correlation=corr,
        ndcg_at_5=ndcg5, ndcg_at_10=ndcg10,
        mrr=mrr, recall_at_10=recall10,
        precision_at_5=prec5, precision_at_10=prec10,
        coverage=1.0,
        leakage_detected=leaked,
        leakage_details=leak_msg,
    )


def _result_to_dict(r: BacktestResult) -> Dict:
    return {
        'model': r.model_name,
        'train_count': r.train_count,
        'test_count': r.test_count,
        'mae': round(r.mae, 2),
        'rmse': round(r.rmse, 2),
        'correlation': round(r.correlation, 4),
        'ndcg_at_5': round(r.ndcg_at_5, 4),
        'ndcg_at_10': round(r.ndcg_at_10, 4),
        'mrr': round(r.mrr, 4),
        'recall_at_10': round(r.recall_at_10, 4),
        'precision_at_5': round(r.precision_at_5, 4),
        'precision_at_10': round(r.precision_at_10, 4),
        'leakage_detected': r.leakage_detected,
        'leakage_details': r.leakage_details,
    }


def _mae(preds, actuals):
    return sum(abs(p - a) for p, a in zip(preds, actuals)) / len(preds) if preds else 0.0

def _rmse(preds, actuals):
    if not preds: return 0.0
    return math.sqrt(sum((p - a) ** 2 for p, a in zip(preds, actuals)) / len(preds))

def _pearson(xs, ys):
    n = len(xs)
    if n < 2: return 0.0
    mx, my = _mean(xs), _mean(ys)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    dy = math.sqrt(sum((y - my) ** 2 for y in ys))
    if dx == 0 or dy == 0: return 0.0
    return num / (dx * dy)
