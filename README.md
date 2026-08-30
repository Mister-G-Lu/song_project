# 🎵 TasteScope — Music Taste Analyzer & Recommender

> **3,214 rated songs · 1,601 artists · 9 years of reviews · 23 genres · 95.5% genre coverage**

A personal music intelligence dashboard that analyzes your listening history, discovers your taste patterns, and recommends songs you'll love — all running locally with zero external dependencies.

## 🚀 Quick Start

**Prerequisites:** Python 3.10+

```bash
# Install dependencies
pip install -r requirements.txt

# Start the server
python run.py

# Open in browser
open http://localhost:5000
```

## 📊 Features

| View | Purpose |
|------|---------|
| **Dashboard** | Overview stats, rating distribution, genre breakdown, top artists |
| **Recommender** | Personalized song suggestions across 5 categories |
| **Blind Spots** | Genres you rate highly but rarely listen to |
| **Constellation** | Interactive D3.js artist similarity network |
| **Evolution** | How your taste has changed over 9 years |
| **Weekly Discovery** | Curated picks refreshed every week |
| **History** | Full searchable, filterable, sortable review history |
| **Challenges** | Critically acclaimed songs outside your listening zone |
| **Quick Add** | FAB button or `A` key to log songs as you discover them |

### Key Capabilities

- **Smart genre classification** — 4-tier cascade: keywords → artist propagation → curated mapping → Wikidata/MusicBrainz
- **Letter-grade extraction** — Infers numeric ratings from "B+" or "loved it"
- **O(1) duplicate detection** — Normalized song signatures prevent duplicates
- **Listened tracking** — Mark recommendations as listened/not listened
- **Spotify integration** — Optional: search tracks, get metadata
- **Weekly digest email** — Automated Monday picks via SMTP

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  Browser (index.html + 12 JS modules)                       │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  CDN: Chart.js · D3.js · Google Fonts                │   │
│  │  JS:  utils.js → shared helpers                      │   │
│  │       app.js → init, error handling                 │   │
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
│  Flask Backend (app.py) — 20+ API endpoints                 │
│  ┌─────────────────────┐  ┌──────────────────────────────┐ │
│  │  TasteEngine         │  │  SpotifyHelper               │ │
│  │  src/taste_engine.py │  │  src/spotify_helper.py       │ │
│  └─────────────────────┘  └──────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
              ┌──────────────────────────┐
              │  data/posts_tails.csv     │  ← Your song database
              └──────────────────────────┘
```

## 📁 Project Structure

```
├── app.py                    # Flask backend with all API routes
├── run.py                    # Server entry point
├── requirements.txt          # Python dependencies
│
├── src/                      # Core engine modules
│   ├── taste_engine.py       # Main engine (stats, recs, genres, challenges)
│   ├── spotify_helper.py     # Spotify Web API wrapper
│   ├── backfill.py           # Rating recovery from letter grades/tone
│   ├── challenge_db.py       # Challenge song database
│   └── genre_data.py         # Genre classification data
│
├── static/                   # Frontend assets
│   ├── css/styles.css        # Consolidated stylesheet
│   └── js/                   # 12 JavaScript modules
│
├── templates/
│   └── index.html            # Single-page app HTML
│
├── data/                     # Your taste data
│   ├── posts_tails.csv       # Song database (source of truth)
│   ├── ban_list.json         # Blocked genres/artists/songs
│   ├── challenge_db.json     # Challenge songs database
│   └── ...                   # Other data files
│
├── scripts/                  # Utility scripts
│   ├── export_static.py      # Build static site for GitHub Pages
│   ├── weekly_digest.py      # Send weekly email digest
│   └── export_data_to_json.py
│
├── tests/                    # Python backend tests (125+ tests)
├── cypress/                  # E2E browser tests (6 specs)
└── .github/workflows/        # CI/CD workflows
```

## 🔧 API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/stats` | Dashboard statistics |
| GET | `/api/recommendations` | Personalized recommendations |
| GET | `/api/blind-spots` | Genre blind spots |
| GET | `/api/constellation` | Artist network graph |
| GET | `/api/evolution` | Taste evolution over time |
| GET | `/api/weekly-discovery` | Weekly curated picks |
| GET | `/api/challenges` | Songs outside your zone |
| GET | `/api/songs` | Paginated song list |
| GET | `/api/search-history` | Full-text search |
| POST | `/api/add-song` | Add a single song |
| POST | `/api/batch-add` | Add multiple songs |
| POST | `/api/import-songs` | Import from pasted text |
| POST | `/api/check-song` | Check if song exists (O(1)) |
| POST | `/api/mark-listened` | Mark song as listened |

## 🧪 Testing

```bash
# Python tests
python -m pytest tests/ -v

# E2E tests
python run_e2e_tests.py

# Static site tests
npm run test:e2e:static
```

## 🚀 Deployment

### GitHub Pages (Static)
```bash
python scripts/export_static.py --out docs
# Push to GitHub with Pages enabled
```

### PythonAnywhere (Live)
1. Clone repo, install dependencies
2. Point WSGI at `app.py`
3. Set environment variables for Spotify/SMTP

### Render / Fly.io
- Free tier available for always-on hosting
- See README sections for detailed setup

## 📊 Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `PORT` | No | Flask server port (default: 5000) |
| `SPOTIFY_CLIENT_ID` | No | Spotify Web API client ID |
| `SPOTIFY_CLIENT_SECRET` | No | Spotify Web API client secret |
| `SMTP_USER` | For digest | SMTP login for weekly email |
| `SMTP_PASS` | For digest | SMTP app password |
| `MAIL_TO` | No | Recipient for weekly digest |

## 🗺️ Roadmap

### ✅ Completed
- [x] Genre coverage indicator
- [x] D3 constellation with edge limits
- [x] Challenge mode toggle (Opposite Taste vs Blind Spots)
- [x] Loading overlay before async fetch
- [x] CDN fallback guards
- [x] Backfill system
- [x] Challenge DB (184 entries, 22 genres)
- [x] Cypress E2E suite
- [x] Listened tracking
- [x] Weekly digest email

### 🔜 Next
- [ ] CI pipeline with GitHub Actions
- [ ] Automated Spotify playlist generation
- [ ] Taste snapshot comparison
- [ ] Last.fm / ListenBrainz import
- [ ] Artist image fetching

### 🎯 Long Term
- [ ] ML recommendation engine
- [ ] PWA / Mobile support
- [ ] Multi-user support
- [ ] Music theory analysis
- [ ] Concert discovery integration

## 📚 Documentation

- [Design Decisions](DECISIONS.md) — ADRs for notable architecture choices
- [API Documentation](#api-endpoints) — All available endpoints
- [Deployment Guide](#deployment) — Hosting options and setup

## 🛠️ Tech Stack

| Layer | Technology |
|-------|------------|
| **Backend** | Python 3.12 + Flask |
| **Frontend** | Vanilla JS (no framework) |
| **Charts** | Chart.js 4.x |
| **Graph** | D3.js 7.x |
| **Database** | CSV file (portable, human-readable) |
| **CSS** | Custom dark theme with CSS variables |
| **Testing** | pytest + Cypress |

## 📄 License

**Unlicensed** — personal project. Free to use, modify, and adapt for your own music taste analysis.

---

Built with ❤️ for music lovers who want to understand their taste better.
