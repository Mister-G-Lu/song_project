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
        hideViewLoading('view-fingerprint');
        renderFingerprint(container, fingerprintData);
    } catch (err) {
        hideViewLoading('view-fingerprint');
        container.innerHTML = `<div class="error-message">Failed to load taste fingerprint: ${err.message}</div>`;
    }
}

function renderFingerprint(container, data) {
    const { genre_fingerprint, year_fingerprint, predictability, selectivity, top_influences, taste_summary, positive_song_count, overall_avg } = data;

    container.innerHTML = `
        <div class="fingerprint-grid">
            <!-- Predictability Meter -->
            <div class="chart-card predictability-card">
                <h3>🎯 Taste Predictability <span class="info-tip" data-tip="How concentrated your taste is across genres and decades. 100% = you mostly like one genre/era. 0% = you like everything equally. Calculated using Shannon entropy.">ℹ️</span></h3>
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

                <!-- Selectivity -->
                <div class="selectivity-section">
                    <h4>🎚️ Selectivity <span class="info-tip" data-tip="How picky you are within each genre. High = you love some songs and dislike others in the same genre (e.g., Country 53% = you're selective about which Country you rate highly). Low = you rate everything in that genre similarly.">ℹ️</span></h4>
                    <div class="predictability-meter">
                        <div class="meter-bar selectivity-bar">
                            <div class="meter-fill selectivity-fill" style="width: ${selectivity.overall}%"></div>
                        </div>
                        <div class="meter-labels">
                            <span>Generous</span>
                            <span class="meter-value selectivity-value">${selectivity.overall}%</span>
                            <span>Selective</span>
                        </div>
                    </div>
                    <div id="selectivityBreakdown" class="selectivity-breakdown"></div>
                </div>

                <p class="taste-summary">${taste_summary}</p>
                <div class="fingerprint-stats">
                    <span>${positive_song_count} songs rated ≥75</span>
                    <span>Avg: ${overall_avg}/100</span>
                </div>
            </div>

            <!-- Genre Fingerprint -->
            <div class="chart-card genre-fp-card">
                <h3>🎨 Genre DNA <span class="info-tip" data-tip="Your taste weighted by rating. Pop 27% means 27% of your 'love' (sum of ratings ≥75) goes to Pop. Higher avg rating = you're pickier but love what you pick.">ℹ️</span></h3>
                <div class="genre-bars" id="genreBars"></div>
            </div>

            <!-- Year Fingerprint -->
            <div class="chart-card year-fp-card">
                <h3>📅 Era Preferences <span class="info-tip" data-tip="Which decades your favorite songs come from, weighted by how much you rated them. The 2010s dominate at 57% — most of your beloved music is from that decade.">ℹ️</span></h3>
                <div class="year-bars" id="yearBars"></div>
            </div>

            <!-- Top Influences -->
            <div class="chart-card influences-card full-width">
                <h3>⭐ Top Taste Influences <span class="info-tip" data-tip="Artists ranked by avg rating × log(song count). This rewards both love intensity AND breadth. Use the search to find any specific artist.">ℹ️</span></h3>
                <div class="influences-search">
                    <input type="text" id="influencesSearch" placeholder="🔍 Search artist..." class="influences-search-input" oninput="filterInfluences()" />
                </div>
                <div class="influences-list" id="influencesList"></div>
            </div>

            <!-- Fit Scorer -->
            <div class="chart-card fit-scorer-card full-width">
                <h3>🔬 Taste Fit Scorer <span class="info-tip" data-tip="Scores how well a song matches your taste DNA (0-100). Weights: Genre match 40%, Era match 25%, Artist affinity 35%. Enter any artist/song to test.">ℹ️</span></h3>
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
    renderInfluences(top_influences, '');
    renderSelectivity(selectivity);
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

function renderInfluences(influences, filter) {
    const container = document.getElementById('influencesList');
    if (!container || !influences) return;

    const maxScore = influences.length > 0 ? influences[0].influence_score : 1;
    let filtered = influences;
    if (filter) {
        const q = filter.toLowerCase();
        filtered = influences.filter(inf => inf.artist.toLowerCase().includes(q));
    }

    // Show up to 15, or all if searching
    const limit = filter ? filtered.length : 15;
    container.innerHTML = filtered.slice(0, limit).map((inf) => {
        const pct = (inf.influence_score / maxScore) * 100;
        const rank = influences.indexOf(inf) + 1;
        return `
            <div class="influence-row">
                <div class="influence-rank">#${rank}</div>
                <div class="influence-info">
                    <div class="influence-name">${inf.artist}</div>
                    <div class="influence-genres">${inf.song_count} songs · avg ${inf.avg_rating} · ${inf.genres.join(', ')}</div>
                </div>
                <div class="influence-bar-track">
                    <div class="influence-bar-fill" style="width: ${pct}%"></div>
                </div>
                <div class="influence-score">${inf.influence_score.toFixed(0)}</div>
            </div>
        `;
    }).join('');
    if (!filter && influences.length > 15) {
        container.innerHTML += `<div class="influences-more">... and ${influences.length - 15} more artists</div>`;
    }
    if (filter && filtered.length === 0) {
        container.innerHTML = '<div class="influences-empty">No artists matching "' + filter + '"</div>';
    }
}

function filterInfluences() {
    const q = document.getElementById('influencesSearch')?.value?.trim() || '';
    if (fingerprintData) {
        renderInfluences(fingerprintData.top_influences, q);
    }
}

function renderSelectivity(selectivity) {
    const container = document.getElementById('selectivityBreakdown');
    if (!container || !selectivity || !selectivity.by_genre) return;

    const sorted = Object.entries(selectivity.by_genre)
        .sort((a, b) => b[1].selectivity - a[1].selectivity)
        .slice(0, 8);

    container.innerHTML = sorted.map(([genre, data]) => {
        const pct = data.selectivity;
        const color = pct > 60 ? '#e74c3c' : pct > 40 ? '#f39c12' : '#27ae60';
        return `
            <div class="sel-row">
                <div class="sel-label">${genre}</div>
                <div class="sel-track">
                    <div class="sel-fill" style="width: ${pct}%; background: ${color}"></div>
                </div>
                <div class="sel-value">${pct.toFixed(0)}%</div>
                <div class="sel-meta">std ${data.std_dev} · ${data.rating_range}</div>
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
