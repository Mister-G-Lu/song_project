#!/usr/bin/env python3
"""
check_component_coverage.py — the standing 80% coverage gate.

Runs the full pytest suite under coverage and enforces TWO layers:

  1. Global floor: .coveragerc sets fail_under = 80 over src/* + app.py,
     so total coverage below 80% fails the run.
  2. Per-component floors: every component must individually clear its
     floor (80% by default). Without this, a big module (taste_engine is
     ~63% of all statements) can mask a regression in a small one.

Exit codes:
  0 — all floors met
  1 — global floor breached
  2 — one or more per-component floors breached

Usage:
  python scripts/check_component_coverage.py            # full gate
  python scripts/check_component_coverage.py --no-tests # report on last .coverage data
  python scripts/check_component_coverage.py --floor 85 # temporary stricter floor
"""
import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Per-component floors. Everything defaults to FLOOR (80); a component may
# opt into a HIGHER floor here once it reliably exceeds it. Never lower a
# floor to make a failing run pass — add tests or use `# pragma: no cover`
# on genuinely unreachable lines instead.
DEFAULT_FLOOR = 80.0
COMPONENT_FLOORS = {
    'spotify_helper.py': 80.0,
    'taste_engine.py': 80.0,
    'discovery.py': 80.0,
    'artist_year_model.py': 80.0,
    'app.py': 80.0,
    # Small components already far above the floor — pinned so regressions
    # surface immediately.
    'backfill.py': 95.0,
    'outliers.py': 95.0,
    'challenge_db.py': 95.0,
    'genre_data.py': 95.0,
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--no-tests', action='store_true',
                        help='report on an existing .coverage file instead of running pytest')
    parser.add_argument('--floor', type=float, default=DEFAULT_FLOOR,
                        help='default per-component floor (default 80)')
    parser.add_argument('--cov-file', default='.coverage',
                        help='path to the coverage data file')
    args = parser.parse_args()

    if not args.no_tests:
        print('Running full test suite under coverage '
              '(this takes ~10 minutes)...', flush=True)
        result = subprocess.run(
            [sys.executable, '-m', 'pytest', 'tests/', '-q',
             '--cov=src', '--cov=app', '--cov-report='],
            cwd=str(ROOT),
        )
        if result.returncode != 0:
            print('\n[gate] TESTS FAILED — fix failing tests before '
                  'coverage is evaluated.', flush=True)
            return 1

    import json
    from coverage import Coverage
    cov = Coverage(data_file=str(ROOT / args.cov_file), config_file=str(ROOT / '.coveragerc'))
    cov.load()
    data = cov.get_data()
    measured = sorted({str(p) for p in data.measured_files()})

    failures = []
    rows = []
    for path in measured:
        rel = str(Path(path).relative_to(ROOT)).replace('\\', '/')
        name = Path(path).name
        try:
            _, executable, _, missing, _ = cov.analysis2(path)
        except Exception:
            continue
        total = len(executable)
        missed = len(missing)
        pct = 100.0 if total == 0 else round(100.0 * (total - missed) / total, 1)
        floor = COMPONENT_FLOORS.get(name, args.floor)
        rows.append((rel, total, missed, pct, floor))
        if pct < floor:
            failures.append((rel, pct, floor))

    print(f'\n{"Component":<38}{"Stmts":>8}{"Miss":>6}{"Cover":>8}{"Floor":>7}')
    print('-' * 67)
    tot = sum(r[1] for r in rows)
    miss = sum(r[2] for r in rows)
    for rel, total, missed, pct, floor in rows:
        mark = '' if pct >= floor else '  << BELOW FLOOR'
        print(f'{rel:<38}{total:>8}{missed:>6}{pct:>7.1f}%{floor:>6.0f}%{mark}')
    print('-' * 67)
    overall = 100.0 if tot == 0 else round(100.0 * (tot - miss) / tot, 1)
    print(f'{"TOTAL":<38}{tot:>8}{miss:>6}{overall:>7.1f}%  (global floor 80%)')

    if failures:
        print('\n[gate] PER-COMPONENT FAILURES:')
        for rel, pct, floor in failures:
            print(f'  {rel}: {pct}% < floor {floor:.0f}%')
        print('\nAdd tests for the components above (or justify `# pragma: no cover` '
              'for unreachable lines). Do NOT lower the floor.')
        return 2

    print('\n[gate] PASS — global and per-component floors met.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
