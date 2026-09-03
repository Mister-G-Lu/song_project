/**
 * fingerprint.js — Taste DNA visualization
 * Shows genre fingerprint, year fingerprint, predictability score,
 * top influences, and a candidate song fit scorer.
 */

let fingerprintData = null;

async function loadFingerprint() {
    const container = document.getElementById('fingerprintContent');
    if (!container) return;

    try {
        const resp = await fetch('/api/taste-fingerprint');
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        fingerprintData = await resp.json();
        renderFingerprint(container, fingerprintData);
    } catch (err) {
        container.innerHTML = `<div class="error-message">Failed to load taste fingerprint: ${err.message}</div>`;
    }
}

function renderFingerprint(container, data) {
    const { genre_fingerprint, year_fingerprint, predictability, top_influences, taste_summary, positive_song_count, overall_avg } = data;

    container.innerHTML = `
        <div class="fingerprint-grid">
            <!-- Predictability Meter -->
            <div class="chart-card predictability-card">
                <h3>🎯 Taste Predictability</h3>
                <div class="predictability-meter">
                    <div class="meter-bar">
                        <div class="meter-fill" style="width: ${predictability.overall}%"></div>
                    </div>
                    <div class="meter-labels">
                        <span>Eclectic</span>
                        <span class="meter-value">${predictability.overall}%</span>
                        <span>Predictable</span>
                    </div>
                </div>
                <div class="predictability-breakdown">
                    <div class="breakdown-item">
                        <span class="breakdown-label">Genre concentration</span>
                        <span class="breakdown-value">${predictability.genre_predictability}%</span>
                    </div>
                    <div class="breakdown-item">
                        <span class="breakdown-label">Era concentration</span>
                        <span class="breakdown-value">${predictability.year_predictability}%</span>
                    </div>
                </div>
                <p class="taste-summary">${taste_summary}</p>
                <div class="fingerprint-stats">
                    <span>${positive_song_count} songs rated ≥75</span>
                    <span>Avg: ${overall_avg}/100</span>
                </div>
            </div>

            <!-- Genre Fingerprint -->
            <div class="chart-card genre-fp-card">
                <h3>🎨 Genre DNA</h3>
                <div class="genre-bars" id="genreBars"></div>
            </div>

            <!-- Year Fingerprint -->
            <div class="chart-card year-fp-card">
                <h3>📅 Era Preferences</h3>
                <div class="year-bars" id="yearBars"></div>
            </div>

            <!-- Top Influences -->
            <div class="chart-card influences-card">
                <h3>⭐ Top Taste Influences</h3>
                <div class="influences-list" id="influencesList"></div>
            </div>

            <!-- Fit Scorer -->
            <div class="chart-card fit-scorer-card full-width">
                <h3>🔬 Taste Fit Scorer</h3>
                <p class="card-subtitle">How well does a song match your taste DNA?</p>
                <div class="fit-form">
                    <input type="text" id="fitArtist" placeholder="Artist name" class="fit-input" />
                    <input type="text" id="fitSong" placeholder="Song name" class="fit-input" />
                    <input type="text" id="fitGenre" placeholder="Genre (optional)" class="fit-input fit-input-sm" />
                    <input type="number" id="fitYear" placeholder="Year (optional)" class="fit-input fit-input-sm" min="1900" max="2030" />
                    <button class="btn btn-primary" onclick="scoreFit()">Score It</button>
                </div>
                <div id="fitResult" class="fit-result" style="display:none"></div>
            </div>
        </div>
    `;

    renderGenreBars(genre_fingerprint);
    renderYearBars(year_fingerprint);
    renderInfluences(top_influences);
}

function renderGenreBars(genreFp) {
    const container = document.getElementById('genreBars');
    if (!container || !genreFp) return;

    const sorted = Object.entries(genreFp).sort((a, b) => b[1].weight - a[1].weight);
    const maxWeight = sorted.length > 0 ? sorted[0][1].weight : 1;

    container.innerHTML = sorted.map(([genre, data]) => {
        const pct = (data.weight / maxWeight) * 100;
        const barColor = getGenreColor(genre);
        return `
            <div class="bar-row">
                <div class="bar-label">${genre}</div>
                <div class="bar-track">
                    <div class="bar-fill" style="width: ${pct}%; background: ${barColor}"></div>
                </div>
                <div class="bar-value">${(data.weight * 100).toFixed(1)}%</div>
                <div class="bar-meta">${data.song_count} songs · avg ${data.avg_rating}</div>
            </div>
        `;
    }).join('');
}

function renderYearBars(yearFp) {
    const container = document.getElementById('yearBars');
    if (!container || !yearFp) return;

    const sorted = Object.entries(yearFp).sort((a, b) => parseInt(a[0]) - parseInt(b[0]));
    const maxWeight = sorted.length > 0 ? Math.max(...sorted.map(([, d]) => d.weight)) : 1;

    container.innerHTML = sorted.map(([decade, data]) => {
        const pct = (data.weight / maxWeight) * 100;
        const hue = mapDecadeToHue(parseInt(decade));
        return `
            <div class="bar-row">
                <div class="bar-label">${decade}</div>
                <div class="bar-track">
                    <div class="bar-fill" style="width: ${pct}%; background: hsl(${hue}, 70%, 50%)"></div>
                </div>
                <div class="bar-value">${(data.weight * 100).toFixed(1)}%</div>
                <div class="bar-meta">${data.song_count} songs · avg ${data.avg_rating}</div>
            </div>
        `;
    }).join('');
}

function renderInfluences(influences) {
    const container = document.getElementById('influencesList');
    if (!container || !influences) return;

    const maxScore = influences.length > 0 ? influences[0].influence_score : 1;

    container.innerHTML = influences.slice(0, 15).map((inf, i) => {
        const pct = (inf.influence_score / maxScore) * 100;
        const rank = i + 1;
        return `
            <div class="influence-row">
                <div class="influence-rank">#${rank}</div>
                <div class="influence-info">
                    <div class="influence-name">${inf.artist}</div>
                    <div class="influence-genres">${inf.genres.join(', ')}</div>
                </div>
                <div class="influence-bar-track">
                    <div class="influence-bar-fill" style="width: ${pct}%"></div>
                </div>
                <div class="influence-score">${inf.influence_score.toFixed(0)}</div>
            </div>
        `;
    }).join('');
}

async function scoreFit() {
    const artist = document.getElementById('fitArtist')?.value?.trim() || '';
    const song = document.getElementById('fitSong')?.value?.trim() || '';
    const genre = document.getElementById('fitGenre')?.value?.trim() || '';
    const year = document.getElementById('fitYear')?.value?.trim() || '';

    if (!artist && !song) {
        alert('Enter at least an artist or song name');
        return;
    }

    const resultDiv = document.getElementById('fitResult');
    if (!resultDiv) return;

    resultDiv.style.display = 'block';
    resultDiv.innerHTML = '<div class="fit-loading">Scoring...</div>';

    try {
        const params = new URLSearchParams();
        if (artist) params.set('artist', artist);
        if (song) params.set('song', song);
        if (genre) params.set('genre', genre);
        if (year) params.set('year', year);

        const resp = await fetch(`/api/taste-fit?${params}`);
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const result = await resp.json();

        const scoreColor = getScoreColor(result.fit_score);
        resultDiv.innerHTML = `
            <div class="fit-score-display">
                <div class="fit-score-circle" style="border-color: ${scoreColor}; color: ${scoreColor}">
                    ${result.fit_score}
                </div>
                <div class="fit-score-label">${result.label}</div>
            </div>
            <div class="fit-breakdown">
                <div class="fit-bar-row">
                    <span>Genre match</span>
                    <div class="fit-bar-track"><div class="fit-bar-fill" style="width: ${result.genre_match}%; background: ${scoreColor}"></div></div>
                    <span>${result.genre_match.toFixed(0)}</span>
                </div>
                <div class="fit-bar-row">
                    <span>Era match</span>
                    <div class="fit-bar-track"><div class="fit-bar-fill" style="width: ${result.year_match}%; background: ${scoreColor}"></div></div>
                    <span>${result.year_match.toFixed(0)}</span>
                </div>
                <div class="fit-bar-row">
                    <span>Artist affinity</span>
                    <div class="fit-bar-track"><div class="fit-bar-fill" style="width: ${result.artist_match}%; background: ${scoreColor}"></div></div>
                    <span>${result.artist_match.toFixed(0)}</span>
                </div>
            </div>
            <p class="fit-explanation">${result.explanation}</p>
        `;
    } catch (err) {
        resultDiv.innerHTML = `<div class="fit-error">Error: ${err.message}</div>`;
    }
}

/* ---- Helpers ---- */

function getGenreColor(genre) {
    const colors = {
        'Pop': '#ff6b9d',
        'Rock': '#e74c3c',
        'Electronic/Dance': '#9b59b6',
        'Hip-Hop/Rap': '#3498db',
        'R&B/Soul': '#e67e22',
        'Country': '#27ae60',
        'Classical': '#1abc9c',
        'Jazz': '#f39c12',
        'Metal': '#7f8c8d',
        'Folk': '#8d6e63',
        'Punk': '#c0392b',
        'Reggae/Dub': '#2ecc71',
        'Blues': '#2c3e50',
        'Latin': '#e74c3c',
        'World': '#16a085',
        'J-Pop/Anime': '#ff69b4',
        'Indie': '#95a5a6',
        'R&B': '#e67e22',
        'Disco/Funk': '#f1c40f',
        'Alternative': '#34495e',
        'Eurovision': '#9b59b6',
    };
    return colors[genre] || '#7f8c8d';
}

function mapDecadeToHue(decade) {
    // Map decades to a color spectrum: 1950s=red, 1980s=blue, 2020s=purple
    const t = Math.max(0, Math.min(1, (decade - 1950) / 70));
    return Math.round(200 - t * 120); // 200 (blue-ish) → 80 (green-ish)
}

function getScoreColor(score) {
    if (score >= 80) return '#27ae60';
    if (score >= 60) return '#2ecc71';
    if (score >= 40) return '#f39c12';
    if (score >= 20) return '#e67e22';
    return '#e74c3c';
}
