"""
scrape_wordpress.py - Fetch full review text from favesongs.wordpress.com
for entries where the CSV tail is truncated and no rating signal exists.

Uses the WordPress.com REST API (public, no auth needed).

Usage:
    python scrape_wordpress.py                     # Show preview of matches
    python scrape_wordpress.py --apply             # Write recovered ratings to CSV

Output:
    Creates recovered_ratings.json with all matches found
    With --apply, writes recovered ratings to the CSV
"""

import csv
import json
import os
import re
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime

API_BASE = "https://public-api.wordpress.com/rest/v1.1/sites/favesongs.wordpress.com/posts"
GRADE_MAP = {'A+': 98, 'A': 95, 'A-': 92, 'B+': 88, 'B': 85, 'B-': 82, 'C+': 78, 'C': 75, 'D': 65, 'F': 50}
GRADE_PATTERN = re.compile(r'\b([A-F][+-]?)\b')
NUM_RATING_PATTERN = re.compile(r'(\d{1,3})\s*/\s*100|(\d{1,2})\s*/\s*10|(\d{1,3})\s*%')
RATING_CONTEXT_PATTERN = re.compile(r'(?:rating|score|grade|overall|my\s*rating)[:\s]*(\d{1,3})', re.IGNORECASE)

def fetch_posts(page=1, per_page=100):
    """Fetch a page of posts from the WordPress.com API."""
    url = f"{API_BASE}?number={per_page}&page={page}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "MusicTasteAnalyzer/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            return data.get('posts', []), data.get('found', 0)
    except urllib.error.HTTPError as e:
        print(f"  HTTP Error {e.code}: {e.reason}", flush=True)
        return [], 0
    except Exception as e:
        print(f"  Error fetching page {page}: {e}", flush=True)
        return [], 0

def extract_rating_from_post(post_content, post_title):
    """Extract a rating from the full post content.
    Returns (rating_value, source_description) or (None, None).
    """
    combined = (post_content + ' ' + post_title)[:5000]
    
    # 1. Check for explicit numerical rating with context
    for m in RATING_CONTEXT_PATTERN.finditer(combined):
        val = int(m.group(1))
        if 0 <= val <= 100:
            return val, f"explicit_rating({val})"
    
    # 2. Check for x/100 or x/10 or x%
    for m in NUM_RATING_PATTERN.finditer(combined):
        for group_idx in range(1, 4):
            val = m.group(group_idx)
            if val:
                val = int(val)
                if group_idx == 2:  # x/10 → scale to 100
                    val = val * 10
                if 0 <= val <= 100:
                    return val, f"numeric({val})"
    
    # 3. Check for letter grades with context
    for m in GRADE_PATTERN.finditer(combined):
        g = m.group(1).upper()
        if g in GRADE_MAP:
            ctx_before = combined[max(0, m.start()-30):m.start()].lower()
            is_plus_minus = len(g) > 1
            has_context = any(kw in ctx_before for kw in [
                'score', 'rating', 'grade', 'got ', 'gave ', 'is ', 'was ',
                'overall', 'final', 'my '
            ])
            if is_plus_minus or has_context:
                return GRADE_MAP[g], f"letter_grade({g})"
    
    # 4. Bonus: Check embedded HTML/markdown patterns
    # Sometimes ratings appear as: <strong>85</strong> or **85**
    html_rating = re.search(r'<(?:strong|b)>(\d{2,3})</(?:strong|b)>', combined)
    if html_rating:
        val = int(html_rating.group(1))
        if 0 <= val <= 100:
            return val, "html_rating"
    
    return None, None

def normalize_title(title):
    """Normalize a title for fuzzy matching."""
    t = title.lower().strip()
    t = re.sub(r'[^\w\s-]', '', t)
    t = re.sub(r'\s+', ' ', t).strip()
    return t

def load_csv_entries():
    """Load all entries from the CSV, returning unrated ones."""
    # Try to load from the data/ directory (project root relative)
    csv_paths = ['../data/posts_tails.csv', 'data/posts_tails.csv', 'posts_tails.csv']
    csv_path = None
    for p in csv_paths:
        if os.path.exists(p):
            csv_path = p
            break
    if not csv_path:
        print('ERROR: Could not find posts_tails.csv. Tried:', csv_paths, flush=True)
        sys.exit(1)
    
    rows = []
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    
    unrated = []
    for i, r in enumerate(rows):
        if not r.get('rating', '').strip():
            unrated.append({
                'index': i,
                'date': r.get('date', ''),
                'title': r.get('title', ''),
                'tail': r.get('tail', '')[:150],
                'title_norm': normalize_title(r.get('title', ''))
            })
    
    return rows, unrated

def main():
    apply_mode = '--apply' in sys.argv
    
    print("=" * 60, flush=True)
    print("  WordPress Scraper — favesongs.wordpress.com", flush=True)
    print("=" * 60, flush=True)
    
    # Load CSV entries
    print("\nLoading CSV entries...", flush=True)
    all_rows, unrated_entries = load_csv_entries()
    print(f"  Total entries: {len(all_rows)}", flush=True)
    print(f"  Unrated entries: {len(unrated_entries)}", flush=True)
    
    # Build lookup by date then by normalized title
    unrated_by_date = {}
    for e in unrated_entries:
        date = e['date']
        if date not in unrated_by_date:
            unrated_by_date[date] = []
        unrated_by_date[date].append(e)
    
    # Fetch all posts from WordPress
    print("\nFetching posts from WordPress API...", flush=True)
    all_posts = []
    page = 1
    total_found = 0
    while True:
        posts, found = fetch_posts(page)
        if not posts:
            break
        all_posts.extend(posts)
        total_found = found
        print(f"  Page {page}: fetched {len(posts)} posts (total so far: {len(all_posts)})", flush=True)
        if len(all_posts) >= found:
            break
        page += 1
        time.sleep(0.3)  # Rate limiting
    
    print(f"\n  Total posts fetched: {len(all_posts)} (of {total_found})", flush=True)
    
    # Match posts to unrated entries
    print("\nMatching posts to unrated entries...", flush=True)
    
    # Build a lookup by date
    posts_by_date = {}
    for post in all_posts:
        post_date = post.get('date', '')[:10]
        if post_date not in posts_by_date:
            posts_by_date[post_date] = []
        posts_by_date[post_date].append(post)
    
    recovered = []
    for e in unrated_entries:
        date = e['date']
        candidates = posts_by_date.get(date, [])
        
        for post in candidates:
            post_title = post.get('title', '')
            post_content = post.get('content', '')
            
            # Try exact match first
            if normalize_title(post_title) == e['title_norm']:
                rating, source = extract_rating_from_post(post_content, post_title)
                recovered.append({
                    **e,
                    'post_title': post_title,
                    'full_content': post_content[:500],
                    'rating': rating,
                    'source': source,
                    'tail_length': len(e.get('tail', ''))
                })
                break
            
            # Try fuzzy match: post title contains CSV title or vice versa
            if len(e['title_norm']) > 10 and (
                e['title_norm'] in normalize_title(post_title) or 
                normalize_title(post_title) in e['title_norm']
            ):
                rating, source = extract_rating_from_post(post_content, post_title)
                recovered.append({
                    **e,
                    'post_title': post_title,
                    'full_content': post_content[:500],
                    'rating': rating,
                    'source': source or 'fuzzy_match',
                    'tail_length': len(e.get('tail', ''))
                })
                break
    
    # Report results
    print(f"\n{'='*60}", flush=True)
    print(f"  MATCHES FOUND: {len(recovered)}", flush=True)
    print(f"{'='*60}", flush=True)
    
    with_ratings = [r for r in recovered if r['rating'] is not None]
    print(f"  With extractable ratings: {len(with_ratings)}", flush=True)
    
    # Show sample matches
    for r in recovered[:15]:
        rating_str = f"Rating: {r['rating']} ({r['source']})" if r['rating'] else "No rating found"
        print(f"\n  [{r['date']}] CSV: {r['title']}", flush=True)
        print(f"    WP: {r['post_title']}", flush=True)
        print(f"    {rating_str}", flush=True)
        if r['full_content']:
            preview = r['full_content'][:150]
            print(f"    Full: {preview}...", flush=True)
    
    if len(recovered) > 15:
        print(f"\n  ... and {len(recovered) - 15} more matches", flush=True)
    
    # Save to file
    output = {
        'total_unrated': len(unrated_entries),
        'total_matches': len(recovered),
        'with_ratings': len(with_ratings),
        'recovered': with_ratings,
        'fuzzy_only': [r for r in recovered if r['rating'] is None],
    }
    
    with open('recovered_ratings.json', 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"\nSaved full results to recovered_ratings.json", flush=True)
    
    # Apply mode: write recovered ratings to CSV
    if apply_mode:
        print(f"\n{'='*60}", flush=True)
        print("  APPLY MODE: Writing recovered ratings to CSV", flush=True)
        print(f"{'='*60}", flush=True)
        
        changes = 0
        for r in with_ratings:
            if r['rating'] is not None:
                idx = r['index']
                all_rows[idx]['rating'] = str(r['rating'])
                changes += 1
                if changes <= 5:
                    print(f"  ✓ [{r['date']}] {r['title']} → {r['rating']} ({r['source']})", flush=True)
        
        if changes > 5:
            print(f"  ... and {changes - 5} more changes", flush=True)
        
        if changes > 0:
            with open('posts_tails.csv', 'w', encoding='utf-8', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=['date', 'rating', 'title', 'tail'])
                writer.writeheader()
                writer.writerows(all_rows)
            print(f"\n✅ Wrote {changes} ratings to posts_tails.csv!", flush=True)
        else:
            print("No changes to write.", flush=True)
    else:
        print(f"\nRun with --apply to write recovered ratings to CSV.", flush=True)

if __name__ == '__main__':
    main()
