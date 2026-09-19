# Music Taste Master Doc — For GPT Brainstorming

> **Purpose:** Give ChatGPT context it can't derive from raw CSV data alone.
> The data lives in a Flask+JS web app (Freebuff) with 5,068 rated songs across
> ~950 artists. This doc explains *what the numbers mean*.

---

## 1. Rating Scale Context

The dataset has **two rating scales mixed together:**

| Source | Scale | Songs | Granularity |
|--------|-------|-------|-------------|
| Original (RateYourMusic-style reviews, 2017–2026) | 0–100 | ~2,350 | Fine-grained (72, 83, 91, etc.) |
| RYM bulk import (Sept 2026) | 1–10 × 10 = 0–100 | ~2,720 | Coarse (only multiples of 10: 50, 60, 70, 80, 90) |

**How to interpret scores:**
- **90–100:** Genuinely loved. These are the songs I'd put on a "best of" playlist.
- **80–89:** Strong enjoy. Would replay, but not obsessed.
- **70:** This is the RYM "good" default — means "I liked it, it's solid." In the original data, 70 means "above average but not special."
- **60:** RYM "decent" or original "meh, it's fine."
- **50 and below:** Original data only (RYM doesn't go this low). Below 50 = actively disliked.
- **1–10:** Hated it. These are real ratings, not errors — often protest ratings against mumble rap.

**The 1,423 songs rated exactly 70 are RYM imports.** They inflate the middle of the distribution. When analyzing, mentally separate them: the original data is ~80 avg, the RYM data is ~70 avg.

---

## 2. Who I Am as a Listener

### The Core Identity
I'm a **melody-first, production-obsessed listener.** I care about:
- **Instrumental craft** — orchestration, arrangement, sound design
- **Emotional arc** — songs that take me somewhere, build, resolve
- **Vocal performance** — technical ability and emotional delivery matter equally
- **Production quality** — polished > raw, always

### What I Love (High Avg + High Count)
These aren't just liked — they're *consistently* rated high across many songs:

| Artist | Songs | Avg | Why |
|--------|-------|-----|-----|
| Lawrence | 48 | 100.0 | Perfect indie-pop. Every song hits. My #1 artist. |
| Joe Hisaishi | 24 | 93.2 | Studio Ghibli composer. Piano + orchestra + nostalgia. |
| Yu-Peng Chen | 7 | 97.9 | Genshin Impact soundtrack. Orchestral + Chinese folk. |
| HOYO-MiX | 23 | 85.9 | miHoYo game soundtracks (Honkai, Genshin). |
| Will Wood | 16 | 90.6 | Theatrical, genre-defying, unhinged piano rock. |
| Taylor Davis | 7 | 93.3 | Violin covers + originals. Classical crossover. |
| Within Temptation | 9 | 91.1 | Symphonic metal, female vocals. |
| Lindsey Stirling | 43 | 84.9 | Violin + electronic + dance. A foundational artist. |
| Owl City | 12 | 85.0 | Synth-pop, dreamy, nostalgic. |
| Carly Rae Jepsen | 19 | 82.3 | Pure pop joy. |

### What I Hate (the "Never Again" List)
| Artist | Songs | Avg | Why |
|--------|-------|-----|-----|
| Playboi Carti | 20 | 1.0 | Mumble rap, no melody, no effort. |
| Lil Yachty | 21 | 2.4 | Same. |
| Young Thug | 21 | 3.6 | Same. |
| Lil Uzi Vert | 22 | 3.7 | Same. |
| 100 gecs | 3 | 23.3 | Hyperpop noise. |
| AJR | 3 | 20.0 | Cringe, try-hard, derivative. |

**The pattern:** I don't dislike genres — I dislike *laziness*. Rap itself is fine (Eminem avg 76.9, Kendrick exists). It's the mumble/no-melody subset I can't stand.

### The Most Inconsistent Artists (I'm Torn)
| Artist | Avg | Range | Why |
|--------|-----|-------|-----|
| Maroon 5 | 66.3 | 10–100 | Early stuff (Sunday Morning) = 100. Later stuff = 10. |
| The Beatles | 65.7 | 25–95 | I respect them but don't love everything. Pepper = great, White Album = spotty. |
| Ado | 78.0 | 30–100 | Japanese vocalist with range. Some songs blow me away, some are filler. |
| Imagine Dragons | 66.4 | 20–95 | Radio hits vs deep cuts = totally different artist. |
| Eminem | 76.9 | 40–100 | Lyrical genius but some albums are pure filler. |

---

## 3. Genre Map — What I Actually Listen To

The genre labels come from a curated mapping. Here's what the averages *really* tell you:

| Genre | Songs | Avg | Interpretation |
|-------|-------|-----|----------------|
| Soundtrack/Score | 50 | 88.5 | **My #1 genre by preference.** If it's a soundtrack, I probably love it. |
| Classical/Instrumental | 85 | 85.7 | Piano, violin, orchestral. Deep emotional connection. |
| Disco/Funk | 8 | 87.1 | Small sample but high — I love groove. |
| Metal | 31 | 84.2 | Symphonic/progressive only. Not death metal. |
| J-Pop/Anime | 76 | 83.1 | Anime OPs + J-Pop. High energy, great melodies. |
| A Cappella | 11 | 84.9 | Pentatonix, VoicePlay. Vocal craft = chef's kiss. |
| K-Pop | 32 | 80.5 | Production is immaculate. Some groups I follow closely. |
| Pop | 549 | 77.0 | Broad. The best pop (Lawrence, Carly Rae) = 90+. Generic pop = 60. |
| Rock | 263 | 76.4 | Classic + alternative. Pink Floyd, Muse, etc. |
| Electronic/Dance | 111 | 75.6 | Depends on the subgenre. Infected Mushroom = 90, generic EDM = 50. |
| Rap/Hip-Hop | 76 | 44.3 | **This is misleading.** The avg is dragged down by 80+ mumble rap songs at 1–5. Good rap (Eminem, RTJ, Kendrick) scores 75–100. |
| Uncategorized | 3,503 | 70.1 | Most RYM imports aren't genre-tagged yet. |

**Key insight:** My genre preferences are **production-quality dependent**, not genre-dependent. I'll love any genre if the craft is there. I'll hate any genre if it's lazy.

---

## 4. The "Why" Behind the Numbers

### Soundtracks Are My Safe Space
Yu-Peng Chen (97.9), Joe Hisaishi (93.2), HOYO-MiX (85.9), and general Soundtrack/Score (88.5 avg) are my highest-rated category. These are **compositional** artists — every note is intentional, every arrangement serves the emotion. This is the through-line of my taste.

### I'm a "Vocal Instrument" Listener
Within Temptation (91.1), Evanescence (90.0), Taylor Davis (93.3 violin), Lindsey Stirling (84.9 violin), Pentatonix (84.9), Dimash (80 for one song) — I treat vocals and instruments as the same thing. A great voice IS an instrument. I'm drawn to technical ability + emotional delivery.

### I Have a Pop Guilt Pleasure Layer
Lawrence (100.0), Carly Rae Jepsen (82.3), Owl City (85.0), Avril Lavigne (74.5) — I love polished, hooky pop. But it has to be *genuine* pop, not manufactured. Lawrence is a 48-song perfect score because every song feels authentic.

### Anime/Japanese Music Is a Deep Well
Ado (24 songs), YOASOBI, Tuyu, Joe Hisaishi, Genshin/Honkai soundtracks — there's a significant Japanese music pipeline in my taste. The common thread: dramatic, emotionally dynamic, high production value.

### Rap Is My Most Polarizing Genre
I gave Eminem a 76.9 avg, Run the Jewels exists in my recommendations, and I have Kendrick-level taste patterns. But 80+ mumble rap songs at 1–5 tank the genre average. **Any recommender that sees "Rap avg: 44" and avoids suggesting rap is wrong.** The issue is subgenre, not genre.

---

## 5. What the Recommender Currently Gets Wrong

### Blind Spots (Artists I'd Love But Haven't Found)
Based on taste pattern analysis:
1. **Dimash Qudaibergen** — 1 song at 94. Kazakh 6-octave vocalist. Orchestral pop. Should be 20+ songs.
2. **Nightwish** — 3 songs at 87. Symphonic metal godfathers. I love Within Temptation but barely know Nightwish.
3. **Joe Hisaishi** — 24 songs at 93.2 but there are 50+ more Ghibli songs I haven't rated.
4. **Ramin Djawadi** — Game of Thrones/Westworld soundtracks. Orchestral + electronic.
5. **Ólafur Arnalds** — Icelandic piano + strings + electronics. Ambient classical.
6. **Hiroyuki Sawano** — Anime soundtrack composer (Attack on Titan). Orchestral + electronic + vocal.
7. **Pentatonix** — 10 songs at 84 but missing their best covers.

### What Breaks the Algorithm
- **The RYM 70 blob:** 1,423 songs rated exactly 70 create a false "I like everything a little" signal. These should be weighted lower.
- **Mumble rap pollution:** 80+ songs at 1–5 make the recommender think I'm a rap hater. I'm not — I'm a mumble rap hater.
- **Cross-genre bridges:** The recommender probably can't connect Lawrence (indie pop) to Maroon 5's early work, or connect Genshin Impact to other game soundtracks.

---

## 6. Questions I Want GPT to Help Answer

### Taste Analysis Questions
1. **What's my actual "taste fingerprint" beyond genre?** If you strip genre labels, what acoustic/musical properties connect my 90+ songs?
2. **Am I a "era listener"?** Do I rate higher for songs from certain years? (The data has release years cached.)
3. **What's the relationship between song count and rating?** Do I rate higher for artists I've heard a lot of, or do I explore broadly?
4. **Am I becoming more or less generous over time?** The timeline data exists but I haven't analyzed the trend.

### Recommendation Questions
5. **What non-obvious genre bridges exist in my taste?** (e.g., my love of orchestral metal + piano classical might point to neoclassical metal)
6. **Which of my "disliked" genres have subgenres I'd actually like?** (e.g., I hate mumble rap but love lyrical rap)
7. **What's the "next frontier" genre I haven't explored?** Based on my pattern, what would I love that I haven't tried?
8. **Are there any "gateway songs" that could expand my taste?** Songs that sit between what I already love and genres I haven't explored.

### Data Science Questions
9. **Can you cluster my taste into 5-7 "taste modes"?** Not genres — listening moods/states.
10. **What's the statistical signature of my "perfect 100" songs?** What do they have in common that my 80s don't?
11. **Is there a "diminishing returns" pattern?** At what point does hearing more songs from an artist stop correlating with higher ratings?

---

## 7. Data Files Summary (for reference)

| File | Description |
|------|-------------|
| `posts_tails.csv` | Main dataset. 5,068 rows: artist, title, rating (0–100), timestamp, comment |
| `curated_artist_genres.json` | Hand-curated genre labels for ~150 key artists |
| `artist_genre_cache.json` | Auto-fetched genre labels for ~950 artists |
| `release_year_cache.json` | Release year data for ~2,500 artists |
| `posts_tails_additions.csv` | Songs added through the web UI (separate from main CSV) |

---

*This doc was generated by Freebuff's Buffy agent on Sept 19, 2026. The data reflects 5,068 rated songs across ~950 artists spanning 2017–2026.*
