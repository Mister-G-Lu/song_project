#!/usr/bin/env python3
"""O(n) post-import duplicate check. Dry-run default; originals always win.

Only appended rows matching a baseline row by full artist+song are removable.
First-side matches are review-only. No years, versions, or CJK are stripped
from song names. Baseline is read from Git, never checked out.
"""
import argparse
import csv
import io
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unicodedata

ROOT = Path(__file__).resolve().parents[1]


def normalize(text):
    text = unicodedata.normalize('NFKD', (text or '').casefold())
    return ''.join(c for c in text if c.isalnum() and not unicodedata.combining(c))


def key(row, first_side=False):
    artist = re.sub(r'^the\s+', '', (row.get('artist') or '').strip(), flags=re.I)
    song = row.get('song') or ''
    if first_side:
        song = song.split(' / ')[0]
    a, s = normalize(artist), normalize(song)
    return (a, s) if a and s else None


def check(before, rows):
    if len(rows) < len(before):
        raise ValueError('Baseline is not an unchanged prefix of this import')
    for old, current in zip(before, rows):
        if old['title'] != current['title']:
            raise ValueError('Baseline title/order mismatch; refusing automatic cleanup')
        if (old.get('rating') or '').strip() and old['rating'] != current['rating']:
            raise ValueError('Original rating changed; refusing automatic cleanup')
    originals = {}
    for i, row in enumerate(before):
        k = key(row)
        if k:
            originals.setdefault(k, i)
    removals = []
    for i in range(len(before), len(rows)):
        match = originals.get(key(rows[i]))
        if match is not None:
            removals.append({'remove_index': i, 'keep_index': match,
                             'removed': rows[i], 'kept': rows[match]})
    # Hash grouping rather than all-pairs fuzzy matching.
    groups = {}
    for i, row in enumerate(rows):
        k = key(row, first_side=True)
        if k:
            groups.setdefault(k, []).append(i)
    review = [indices for indices in groups.values()
              if len(indices) > 1 and any(i >= len(before) for i in indices)]
    return removals, review


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--baseline-ref', default='HEAD')
    ap.add_argument('--apply', action='store_true')
    ap.add_argument('--report', type=Path, required=True)
    args = ap.parse_args()
    path = ROOT / 'data/posts_tails.csv'
    baseline = subprocess.check_output(
        ['git', 'show', f'{args.baseline_ref}:data/posts_tails.csv'], cwd=ROOT).decode('utf-8')
    before = list(csv.DictReader(io.StringIO(baseline)))
    original_bytes = path.read_bytes()
    reader = csv.DictReader(io.StringIO(original_bytes.decode('utf-8')))
    header = reader.fieldnames
    rows = list(reader)
    removals, review = check(before, rows)
    report = {'baseline_ref': args.baseline_ref, 'applied': args.apply,
              'rows_before': len(rows), 'baseline_rows': len(before),
              'removals': removals,
              'review_groups_before': [[{'index': i, **rows[i]} for i in group] for group in review]}
    print(f'{len(rows)} rows checked; {len(removals)} imported duplicates of original entries')
    for item in removals:
        print(f'  Keep {item["kept"]["rating"]}: {item["kept"]["title"]}; '
              f'remove {item["removed"]["rating"]}: {item["removed"]["title"]}')
    if args.apply and removals:
        drop = {x['remove_index'] for x in removals}
        kept = [r for i, r in enumerate(rows) if i not in drop]
        assert kept[:len(before)] == rows[:len(before)]
        buffer = io.StringIO(newline='')
        writer = csv.DictWriter(buffer, fieldnames=header, lineterminator='\n')
        writer.writeheader()
        writer.writerows(kept)
        # Refuse concurrent modifications; keep a byte-for-byte backup.
        if path.read_bytes() != original_bytes:
            raise RuntimeError('Dataset changed during check')
        path.with_suffix('.dedup.bak').write_bytes(original_bytes)
        fd, tmp = tempfile.mkstemp(dir=path.parent, suffix='.csv')
        try:
            with os.fdopen(fd, 'w', encoding='utf-8', newline='') as f:
                f.write(buffer.getvalue())
            os.replace(tmp, path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)
        with path.open(encoding='utf-8', newline='') as f:
            assert list(csv.DictReader(f)) == kept
        second, remaining = check(before, kept)
        assert not second
        report['rows_after'] = len(kept)
        report['review_groups_after'] = [[{'index': i, **kept[i]} for i in group] for group in remaining]
        report['original_rows_unchanged'] = True
        print(f'Applied: {len(kept)} rows; {len(remaining)} first-side groups remain review-only')
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
