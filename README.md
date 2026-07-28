# 🎵 TasteScope — Music Taste Analyzer & Recommender

> **3,088 songs · 1,307 artists · 10 years of reviews · 23 genres · 85% genre coverage**

A personal music intelligence dashboard that analyzes your listening history, discovers your taste patterns, and recommends songs you'll love — all running locally with zero external dependencies.

## Contents

- [Quick Start](#quick-start)
- [What It Does](#what-it-does)
- [Architecture](#architecture)
- [Project Structure](#project-structure)
- [Development Guide](#development-guide)
- [Testing](#testing)
- [Adding Songs](#adding-songs)
- [Genre Classification Pipeline](#genre-classification-pipeline)
- [Troubleshooting](#troubleshooting)
- [Environment Variables](#environment-variables)
- [Future Roadmap](#future-roadmap)
- [Tech Stack](#tech-stack)
- [Data](#data)

---

## Quick Start

**Prerequisites:** Python 3.10+, Node.js 18+ (for E2E tests only), pip.

```bash
# 1. Install Python dependencies
pip install -r requirements.txt

# 2. Start the server
python run.py

# 3. Open in browser
open http://localhost:5000
```

That's it. Your personal music dashboard is running.

---

## What It Does

| View | Purpose |
|---|---|
| **Dashboard** | Overview stats, rating distribution chart, genre breakdown, top artists table, recent reviews, backfill preview |
| **Recommender** | Personalized song suggestions across 5 categories based on your taste profile |
| **Blind Spots** | Genres you rate highly but rarely listen to — unexplored goldmines |
| **Constellation** | Interactive D3.js force-directed graph of artists, color-coded by genre |
| **Evolution** | How your taste has changed over 10 years — rating trends, yearly breakdowns, genre shifts |
| **Weekly Discovery** | Curated picks that match your taste, refreshed every week |
| **History** | Full searchable, filterable, sortable history of every review |
| **Challenges** | Critically acclaimed songs outside your listening zones, tiered by difficulty |
| **Quick Add** | FAB button or `A` key to log songs as you discover them |

### Key Features

- **Smart genre classification** — Review text keyword matching + curated artist mapping (~200 artists) + Wikidata SPARQL batch lookup + MusicBrainz fallback. 85% of songs automatically categorized.
- **Letter-grade extraction** — If you wrote "B+" or "loved it," the engine infers a numeric rating automatically.
- **Tone inference** — Positive/negative/neutral review sentiment mapped to ratings.
- **O(1) duplicate detection** — Normalized song signatures prevent duplicate entries.
- **Spotify integration** — Optional: search tracks, get metadata (set `SPOTIFY_CLIENT_ID` and `SPOTIFY_CLIENT_SECRET`).
- **Keyboard-friendly** — Press `1`–`8` to switch views. Press `A` to quick-add.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  Browser (index.html + 11 JS modules)                       │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  CDN: Chart.js · D3.js · Google Fonts                │   │
│  │  JS:  utils.js → shared helpers                      │   │
│  │       app.js → init, keyboard shortcuts              │   │
│  │       dashboard.js → stats, charts, backfill        │   │
│  │       recommender.js → rec cards                     │   │
│  │       blindspots.js → genre gap analysis             │   │
│  │       constellation.js → D3 force graph              │   │
│  │       evolution.js → Chart.js time series            │   │
│  │       weekly.js → weekly picks                       │   │
│  │       history.js → search, sort, paginate            │   │
│  │       challenge.js → tiered challenges               │   │
│  │       quickadd.js → modal, form, validation          │   │
│  └─────────────────────────────────────────────────────┘   │
│                           │ HTTP fetch                      │
└───────────────────────────┼─────────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  Flask Backend (app.py) — 15+ API endpoints                 │
│  ┌─────────────────────┐  ┌──────────────────────────────┐ │
│  │  TasteEngine         │  │  SpotifyHelper               │ │
│  │  src/taste_engine.py │  │  src/spotify_helper.py       │ │
│  │                      │  │                              │ │
│  │  ├─ CSV data loader  │  │  ├─ spotipy integration      │ │
│  │  ├─ Genre classifier │  │  ├─ track search + metadata  │ │
│  │  ├─ Recommender      │  │  └─ graceful offline mode    │ │
│  │  ├─ Evolution engine │  │                              │ │
│  │  ├─ Constellation    │  └──────────────────────────────┘ │
│  │  ├─ Weekly discovery │                                     │
│  │  ├─ Challenge gen    │  External APIs:                     │
│  │  ├─ Backfill system  │  ├─ Wikidata SPARQL (batch genre)   │
│  │  └─ Dedup layer      │  ├─ MusicBrainz (fallback genre)    │
│  └─────────────────────┘  └─ Spotify Web API (optional)       │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
              ┌──────────────────────────┐
              │  data/posts_tails.csv     │  ← Your song database
              │  [date, rating, title,    │
              │   review_text]            │
              │                           │
              │  3,088 rows · 2017–2026   │
              └──────────────────────────┘
```

### Data Flow

1. **CSV** → `TasteEngine` loads all rows into memory at startup
2. **API endpoints** query the engine, return JSON responses
3. **Frontend JS** fetches from APIs, renders DOM elements + Chart.js/D3.js visualizations
4. **Quick-add / import** POST endpoints append to the CSV and trigger an engine reload

### API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| GET | `/` | HTML page |
| GET | `/api/stats` | Dashboard statistics |
| GET | `/api/recommendations?style=all` | Personalized recommendations |
| GET | `/api/blind-spots` | Genre blind spots |
| GET | `/api/constellation` | Artist network graph data |
| GET | `/api/evolution` | Taste evolution over time |
| GET | `/api/weekly-discovery` | Weekly curated picks |
| GET | `/api/challenges?count=20` | Songs outside your listening zone |
| GET | `/api/songs?sort=&limit=&offset=&search=&min_rating=` | Paginated song list |
| GET | `/api/search-history?q=` | Full-text search through reviews |
| GET | `/api/backfill-preview?method=all` | Preview rating recovery |
| GET | `/api/known-songs` | Dedup signatures for client-side check |
| GET | `/api/export` | Full data export as JSON |
| GET | `/api/spotify-status` | Spotify connection status |
| GET | `/api/search-spotify?title=&artist=` | Search Spotify (if configured) |
| POST | `/api/add-song` | Add a single song |
| POST | `/api/batch-add` | Add multiple songs |
| POST | `/api/import-songs` | Import from pasted text |
| POST | `/api/check-song` | Check if song exists (O(1)) |
| POST | `/api/backfill-ratings` | Apply backfill to CSV |
| POST | `/api/reclassify-genres` | Re-run genre classification |

---

## Project Structure

```
├── app.py                    # Flask backend with all API routes
├── run.py                    # Server entry point
├── requirements.txt          # Python dependencies
├── package.json              # Node.js deps (Cypress E2E tests)
│
├── src/
│   ├── taste_engine.py       # Core engine (stats, recs, genres, challenges)
│   └── spotify_helper.py     # Spotify Web API wrapper
│
├── templates/
│   └── index.html            # Single-page app HTML
│
├── static/
│   ├── css/
│   │   └── style.css         # Full app stylesheet (~2000 lines)
│   └── js/
│       ├── app.js            # Init, keyboard shortcuts, error handling
│       ├── utils.js          # Shared helpers (showToast, escapeHtml, debounce)
│       ├── dashboard.js      # Stats grid, charts, backfill panel
│       ├── recommender.js    # Recommendation cards
│       ├── blindspots.js     # Genre blind spot analysis
│       ├── constellation.js  # D3.js force-directed graph
│       ├── evolution.js      # Chart.js time series
│       ├── weekly.js         # Weekly discovery picks
│       ├── history.js        # Searchable, filterable song history
│       ├── challenge.js      # Tiered music challenges
│       └── quickadd.js       # Quick-add modal + form
│
├── data/
│   └── posts_tails.csv       # Your song database (the source of truth)
│
├── tests/                    # Python backend tests
│   ├── test_taste_engine.py  # 98 tests — engine, stats, recs, challenges, genre
│   ├── test_app.py           # 52 tests — API endpoints
│   └── test_spotify_helper.py# 20 tests — Spotify wrapper
│
├── cypress/                  # E2E browser tests
│   ├── config.js             # Cypress configuration
│   ├── support/e2e.js        # Custom commands (waitForView, navigateToView)
│   └── e2e/
│       ├── smoke.cy.js       # 9 tests — loading, static files, nav structure
│       ├── dashboard.cy.js   # 11 tests — stats, charts, tables
│       ├── history.cy.js     # 8 tests — search, sort, filter (intercept-based)
│       ├── navigation.cy.js  # 10 tests — sidebar, keyboard shortcuts
│       ├── quickadd.cy.js    # 8 tests — modal, form, validation, submit
│       ├── views.cy.js       # 15 tests — all specialized views render
│       ├── api_integration.cy.js # 18 tests — API response contract checks
│       └── errors.cy.js      # 30+ tests — network errors, edge cases, resilience
│
├── run_e2e_tests.py          # Test runner: starts Flask + runs Cypress
├── start_server_and_test.sh  # Shell equivalent
└── README.md                 # This file
```

## Troubleshooting

| Problem | Likely Cause | Fix |
|---|---|---|
| `Address already in use` on port 5000 | Another process is using the port | Find it: `netstat -ano \| findstr :5000`, then `taskkill /PID <PID> /F` |
| `'cypress' is not recognized` | Cypress binary not installed | Run `npx cypress install` from the project root |
| CSV shows garbled characters | UTF-8 encoding issue on Windows | Save CSV as UTF-8 with BOM, or set `PYTHONUTF8=1` env var |
| `pip install` fails with build errors | Missing C++ build tools | Install [Microsoft C++ Build Tools](https://visualstudio.microsoft.com/visual-cpp-build-tools/) |
| Charts don't render (blank canvases) | Chart.js CDN blocked or slow | Check browser console for network errors. Try a different DNS or load Chart.js locally |
| "No results" when you know data exists | Search is case-insensitive but checks against parsed titles | Check the CSV row format matches `"Song Name (Artist, Year)"` |
| Dashboard shows 0 songs | CSV path is wrong | Verify `data/posts_tails.csv` exists relative to `app.py` |
| Spotify search returns errors | Missing or invalid credentials | Set `SPOTIFY_CLIENT_ID` and `SPOTIFY_CLIENT_SECRET` env vars |
| Constraint loads slowly | MusicBrainz API rate limiting | Skip MusicBrainz with `POST /api/reclassify-genres {"use_musicbrainz": false}` |
| E2E tests fail because server isn't running | Tests run before server is ready | Use `python run_e2e_tests.py` which waits for the server, or set a longer timeout |

---

| Variable | Required | Default | Description |
|---|---|---|---|
| `PORT` | No | `5000` | Flask server port |
| `SPOTIFY_CLIENT_ID` | No | — | Spotify Web API client ID (for track search) |
| `SPOTIFY_CLIENT_SECRET` | No | — | Spotify Web API client secret |

Without Spotify credentials, the app runs fully but skips live track search. Genre classification, recommendations, and all other features work offline.

---

## Development Guide

### Adding a New API Endpoint

1. Define a method in `src/taste_engine.py` that returns a dict (or `src/spotify_helper.py` for Spotify calls)
2. Add a route in `app.py` following the existing pattern:
   ```python
   @app.route('/api/my-new-endpoint')
   def my_new_endpoint():
       result = taste_engine.my_method()
       return jsonify(result)
   ```
3. Add tests in `tests/test_app.py` (endpoint) and `tests/test_taste_engine.py` (engine method)
4. Add E2E contract test in `cypress/e2e/api_integration.cy.js`

### Adding a New Frontend View

1. Create a new JS file in `static/js/yourview.js` following the `async function loadYourView() { ... }` pattern
2. Add an HTML section in `templates/index.html` with `id="view-yourview"` and `class="view"`
3. Add a sidebar nav item in the HTML matching the existing structure
4. Register the view in the keyboard shortcut handler in `static/js/app.js`
5. Import the script in the HTML before `app.js`
6. Add tests in `cypress/e2e/views.cy.js`

### Debug Mode

```bash
# In app.py, change to:
app.run(debug=True, host='0.0.0.0', port=port)
# Or set FLASK_ENV=development
```

Debug mode enables auto-reload on file changes and shows detailed error pages.

### Code Style

- **Python**: PEP 8. Tests use `pytest` with `unittest.mock` for external APIs.
- **JavaScript**: ES6+ modules (vanilla, no framework). Functions prefixed with `load`/`render`/`open`/`close`. Error handlers use `try/catch` with `showToast()` for user feedback.
- **CSS**: CSS custom properties (`--bg-primary`, `--text-primary`, etc.) for theming. Dark theme by default. Responsive grid layout.

---

## Testing

### Python Backend Tests (183 tests)

```bash
# Run all tests
python -m pytest tests/ -v

# Run a specific test file
python -m pytest tests/test_taste_engine.py -v

# Skip slow MusicBrainz tests
python -m pytest tests/ --ignore=tests/test_musicbrainz.py

# Run with coverage
python -m pytest tests/ --cov=src
```

### Cypress E2E Tests (8 specs, 90+ tests)

```bash
# Terminal 1: Start the Flask server
python run.py

# Terminal 2: Run all E2E tests headlessly
npx cypress run --headless --browser chrome

# Run a single spec
npx cypress run --headless --spec "cypress/e2e/dashboard.cy.js"

# Open interactive test runner
npx cypress open

# Or use the automated runner (starts server + runs tests)
python run_e2e_tests.py
python run_e2e_tests.py cypress/e2e/smoke.cy.js
```

**Note**: On first Cypress run, you may need to install the binary:
```bash
npx cypress install
```

### Test Coverage Map

| Category | Tests | What's verified |
|---|---|---|
| **Smoke** | 9 | All views load, static files reachable, nav structure correct |
| **Dashboard** | 11 | 8 stat cards, Chart.js renders, top artists, reviews, backfill |
| **History** | 8 | Search with intercept waits, sort, filter, pagination |
| **Navigation** | 10 | Sidebar clicks, keyboard shortcuts `1`–`8`, modifier key guard |
| **Quick Add** | 8 | Modal open/close, validation, form submit, rating bounds |
| **Views** | 15 | Recommender, Blind Spots, Constellation, Evolution, Weekly, Challenge |
| **API Contracts** | 18 | Every endpoint returns expected response shape |
| **Errors** | 30+ | 500s, network failures, XSS, long strings, empty data, boundary values |
| **Python** | 183 | Engine math, stats, dedup, backfill, genre classification, recommendations |

---

## Adding Songs

### The CSV Format

Your song database lives at `data/posts_tails.csv`. Each row is:

```
date,rating,title,review_text
```

- **date**: ISO format (`2024-03-15`)
- **rating**: Numeric 0–100, or letter grade (A–F), or empty
- **title**: Format `"Song Name (Artist, Year)"` or `"Artist - Song"`
- **review_text**: Your review (used for genre classification and tone inference)

### Ways to Add

1. **Quick-Add button** (`+` FAB or press `A`) — modal form, auto-appends to CSV
2. **Batch import** — Paste multiple formatted lines into the import dialog
3. **Direct CSV edit** — Open the CSV in any editor, add rows, restart the server
4. **API** — `POST /api/add-song` or `POST /api/batch-add` with JSON body

### Artist Title Format Best Practice

```
Shape of You (Ed Sheeran, 2017)
```

The parser extracts "Ed Sheeran" as the artist from the parenthetical. This format maximizes genre classification accuracy because artist-level genre propagation can then apply to ALL songs by that artist.

---

## Genre Classification Pipeline

Songs are classified through a 4-tier cascade. The first match wins:

```
1. Keyword matching → scans review text for "pop", "rock", "classical", etc.
2. Artist propagation → if ANY song by artist X is classified, ALL songs by X inherit it
3. Curated artist mapping → ~200 well-known artists pre-mapped to genres
4. Wikidata SPARQL → batch query for remaining unknown artists (free, no auth)
5. MusicBrainz fallback → sequential API lookups (slow, rate-limited to 1/sec)
```

**Current coverage: 85.0%** (2,624 of 3,088 songs classified across 23 genres).

---

## Future Roadmap

### ✅ Recently Completed

- [x] **Genre coverage indicator** — Dashboard now shows "Genre Coverage" stat card (color-coded green/yellow/red at ≥85%/≥70%/<70%)
- [x] **D3 constellation edge limit** — Browser-freeze fix: similarity edges capped at top 80 artists × 5 connections (was O(n²) = 380K+ potential edges)
- [x] **Challenge mode toggle** — Opposite Taste vs Blind Spots modes, tier-guaranteeing dedup, genre alias mapping (130 aliases)
- [x] **Loading overlay before async fetch** — Empty-content flash eliminated across all views
- [x] **CDN fallback guards** — Chart.js / D3.js failures caught gracefully instead of hard-crashing
- [x] **Backfill system** — Letter-grade extraction + tone inference recovers missing ratings
- [x] **Challenge DB** — 184 entries across 22 genres, 4 difficulty tiers, opposite-taste targeting
- [x] **Cypress E2E suite** — 8 specs, 90+ tests covering smoke, nav, API contracts, errors, all views
- [x] **Python test suite** — 211 tests across engine, API endpoints, Spotify helper
- [x] **Project restructuring** — Clean separation: `src/` (engine), `static/` (frontend), `tests/` (backend), `cypress/` (E2E)

### Short Term (next)

- [ ] **CI pipeline** — GitHub Actions workflow: run Python tests + Cypress E2E on every push
- [ ] **GitHub Actions badge** — Add status badge to README once CI is live
- [ ] **Automated playlist generation** — Export weekly discovery picks as Spotify playlist via API
- [ ] **Email newsletter (self-hosted)** — Weekly digest email with your top picks, taste insights, and challenges
- [ ] **Taste snapshot comparison** — Compare this week's stats vs last month: "You explored 3 new genres!"

### Medium Term

- [ ] **Last.fm / ListenBrainz import** — Auto-import listening history from external services to enrich the dataset
- [ ] **Artist image fetching** — Show album art and artist photos in recommender, history, and constellation views
- [ ] **Smart shuffle** — Queue of songs that fit your current taste mood (e.g., "something energetic like your 90+ rated songs")
- [ ] **Taste similarity** — Compare your taste profile with friends' exports (share your `stats.json`)
- [ ] **Listening streaks** — Track review frequency, longest streaks, peak periods — heatmap calendar view
- [ ] **Mood mapping** — Tag songs with mood keywords (upbeat, chill, dark, energetic) from NLP review analysis
- [ ] **Genre confidence scores** — Show how confidently each song was classified (keyword match tier vs MusicBrainz vs curated)
- [ ] **Custom genre merging** — Merge similar genres (e.g., "Electronic/Dance" + "Disco/Funk" into one) via UI settings
- [ ] **"Discovery debt" indicator** — Artists you've rated highly but only listened to 1–2 songs: "you owe them more listens"

### Long Term

- [ ] **ML recommendation engine** — Train a lightweight model on your ratings vs. audio features (valence, energy, tempo, danceability)
- [ ] **PWA / Mobile** — Offline-capable progressive web app with service worker for mobile access
- [ ] **Multi-user support** — Shared instance for family/friend taste comparison and challenge battles
- [ ] **Music theory analysis** — Key, BPM, chord progression analysis of your preferred songs via acoustid/analyzer APIs
- [ ] **Concert discovery** — Alert when artists you love announce shows near you (Songkick / Bandsintown integration)
- [ ] **Real-time collaboration** — Shared playlists, group challenges, taste debates

### Ideas to Explore

- **"What if I liked X more?"** — Alternative-timeline taste simulation: what would your top 10 look like if you weighted a genre differently?
- **Taste biography** — Auto-generate a narrative of your musical journey: "In 2019 you discovered J-Pop... by 2022 you were a connoisseur with 410 songs"
- **Genre cartography** — Interactive map of genres with your taste as a highlighted territory, showing migration paths between genres
- **Listening calendar** — GitHub-style contribution heatmap but for your daily review activity over the full 10-year span
- **Rating calibration** — Detect rating drift: are you getting harsher or more generous over time? Show adjusted ratings to normalize
- **"Obscure gems" radar** — Find songs you rated 90+ that have fewer than 1M Spotify listens — hidden gems in your own collection

---

## Tech Stack

| Layer | Technology | Purpose |
|---|---|---|
| **Backend** | Python 3.12 + Flask | API server, data processing |
| **Frontend** | Vanilla JS (no framework) | Single-page app |
| **Charts** | Chart.js 4.x | Bar/doughnut/line charts |
| **Graph** | D3.js 7.x | Force-directed artist constellation |
| **Database** | CSV file | Portable, human-readable, git-friendly |
| **CSS** | Custom (dark theme) | Inter font, CSS variables, grid layout |
| **Testing** | pytest + Cypress | Python backend + browser E2E |
| **External APIs** | Wikidata SPARQL, MusicBrainz, Spotify (optional) | Genre lookup, track metadata |

### Why CSV?

Your song data lives in a plain CSV file — no database server, no migrations, no schema locking. You can edit it in Excel, commit it to git, diff your changes, and share it with friends. The engine loads it entirely into memory at startup (~3,000 rows is trivial).

---

## Data

- **3,088 songs** reviewed from 2017 to 2026 (10 years)
- **2,274 rated songs** (74% have a numeric rating)
- **1,307 unique artists**
- **Average rating: 81.2/100**
- **85.0% genre coverage** across 23 genres
- **Top genres**: Pop (728), J-Pop/Anime (410), Rock (334), Soundtrack/Score (220), Electronic/Dance (164)
- **Highest-rated genre (avg)**: Blues (94.0), Disco/Funk (88.6), Classical/Instrumental (87.0), Eurovision (87.3)

---

## Contributing

This is a personal project, but suggestions and ideas are always welcome. Open an issue or reach out if:
- You find a bug
- You have an idea for a new feature
- You want to adapt the engine for your own music collection

---

## Deployment

The app runs on Flask's built-in server via `python run.py` — fine for local/personal use.

For **production** (sharing with friends, running 24/7), use a WSGI server:

```bash
# Install
pip install waitress

# Serve (replaces python run.py)
waitress-serve --host=0.0.0.0 --port=5000 app:app
```

Or with Docker:
```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY . .
RUN pip install -r requirements.txt
EXPOSE 5000
CMD ["waitress-serve", "--host=0.0.0.0", "--port=5000", "app:app"]
```

---

## License

**Unlicensed** — personal project. Free to use, modify, and adapt for your own music taste analysis.
