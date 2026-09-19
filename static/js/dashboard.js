/**
 * dashboard.js - Dashboard view with stats, charts, and tables
 */

let ratingChartInstance = null;
let genreChartInstance = null;
let _genreDistributionRaw = null;  // full API response for toggle filtering
let _genreFilterMode = 'all';      // 'all' | 'liked'

async function loadDashboard(prefetchedStats, skipBackfill) {
    await withViewLoading('view-dashboard', 'Loading dashboard...', async () => {
        const renderToken = window.ViewControl ? window.ViewControl.beginRender('dashboard') : 0;
        const data = prefetchedStats || await (window.ViewControl
            ? window.ViewControl.fetch('dashboard', '/api/stats')
            : (await fetch('/api/stats')).json());
        if (!window.ViewControl || window.ViewControl.isCurrent('dashboard', renderToken)) {
            renderStats(data);
            renderRatingChart(data.rating_distribution);
            _genreDistributionRaw = data.genre_distribution;
            _initGenreFilterToggle();
            renderGenreChart(data.genre_distribution);
            renderTopArtists(data.top_artists);
            renderRecentReviews(data.recent_reviews);
        }
    });
    // Also load backfill preview alongside dashboard stats (unless caller opts out)
    if (!skipBackfill) {
        try {
            await loadBackfillPreview();
        } catch (err) {
            // Backfill is secondary — don't block dashboard
        }
    }
    // Load ban list (non-blocking)
    try {
        await loadBanList();
    } catch (err) {
        // Ban list is secondary — don't block dashboard
    }
    // Load year conquest (non-blocking)
    try {
        await loadYearConquest();
    } catch (err) {
        // Conquest is secondary — don't block dashboard
    }
    // Load outliers (non-blocking)
    try {
        await loadOutliers();
    } catch (err) {
        // Outliers is secondary — don't block dashboard
    }
}

/**
 * Update just the cheap headline stat cards from a {total_entries,
 * rated_entries, avg_rating} delta (e.g. after an add-song POST). The charts
 * and tables keep their current state — they refresh on the next full load.
 * @param {{total_entries?: number, rated_entries?: number, avg_rating?: number}} delta
 */
function renderStatsTotals(delta) {
    if (!delta) return;
    if (delta.total_entries !== undefined) {
        const el = document.getElementById('statTotal');
        if (el) el.textContent = delta.total_entries.toLocaleString();
    }
    if (delta.rated_entries !== undefined) {
        const el = document.getElementById('statRated');
        if (el) el.textContent = delta.rated_entries.toLocaleString();
    }
    if (delta.avg_rating !== undefined) {
        const el = document.getElementById('statAvg');
        if (el) el.textContent = delta.avg_rating;
    }
}

function renderStats(data) {
    document.getElementById('statTotal').textContent = data.total_entries?.toLocaleString() || '-';
    document.getElementById('statRated').textContent = data.rated_entries?.toLocaleString() || '-';
    document.getElementById('statAvg').textContent = data.avg_rating !== undefined ? data.avg_rating : '-';
    document.getElementById('statMedian').textContent = data.median_rating !== undefined ? data.median_rating : '-';
    document.getElementById('statArtists').textContent = data.unique_artists !== undefined ? data.unique_artists : '-';

    // Genre coverage: compute from genre_distribution
    const genres = data.genre_distribution || {};
    const uncategorized = genres['Uncategorized']?.count || 0;
    const total = data.total_entries || 0;
    const coveragePct = total > 0 ? ((1 - uncategorized / total) * 100).toFixed(1) : '-';
    const coverageEl = document.getElementById('statCoverage');
    if (coverageEl) {
        coverageEl.textContent = coveragePct !== '-' ? `${coveragePct}%` : '-';
        const pct = parseFloat(coveragePct);
        coverageEl.style.color = pct >= 85 ? PALETTE.success : pct >= 70 ? PALETTE.warning : PALETTE.danger;
    }

    if (data.date_range) {
        const start = data.date_range.start || '';
        const end = data.date_range.end || '';
        const startYear = start.slice(0, 4);
        const endYear = end.slice(0, 4);
        const years = parseInt(endYear) - parseInt(startYear);
        document.getElementById('statPeriod').textContent = `${years} years`;
    }

    const perfectCount = Object.entries(data.rating_distribution || {})
        .filter(([k]) => k === '96-100')
        .reduce((sum, [,v]) => sum + v, 0);
    document.getElementById('statPerfect').textContent = perfectCount;
}

function renderRatingChart(distribution) {
    const canvas = document.getElementById('ratingChart');
    if (!canvas || window.__chartjsFailed) return;
    window.loadLib('chartjs').then(() => {
        _drawRatingChart(distribution);
    }).catch(() => { window.__chartjsFailed = true; });
}

function _drawRatingChart(distribution) {
    const canvas = document.getElementById('ratingChart');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    
    if (ratingChartInstance) { ratingChartInstance.destroy(); ratingChartInstance = null; }

    const labels = Object.keys(distribution);
    const values = Object.values(distribution);
    const colors = PALETTE.chartColors;

    ratingChartInstance = new Chart(ctx, {
        type: 'bar',
        data: {
            labels,
            datasets: [{
                data: values,
                backgroundColor: colors.map(c => c + 'CC'),
                borderColor: colors,
                borderWidth: 1,
                borderRadius: 4,
            }]
        },
        options: {
            ...CHART_THEME,
            scales: {
                y: { beginAtZero: true, ...CHART_THEME.scales.y },
                x: { ...CHART_THEME.scales.x }
            },
            plugins: {
                legend: { display: false },
                tooltip: { ...CHART_THEME.plugins.tooltip, callbacks: {
                    label: (ctx) => `${ctx.parsed.y} songs`
                }}
            }
        }
    });
}

function genreBreakdownModel(genres) {
    const entries = Object.entries(genres || {})
        .filter(([, value]) => Number(value?.count) > 0)
        .map(([key, value]) => ({
            key,
            label: key === 'Uncategorized' ? 'Other' : key,
            count: Number(value.count),
            avgRating: value.avg_rating,
        }))
        .sort((a, b) => b.count - a.count)
        .slice(0, 12);

    // Keep the palette deterministic: the same label always has the same
    // color for this render, while the standalone legend stays inspectable.
    const colors = [
        '#4f8cf7', '#f87171', '#a78bfa', '#34d399', '#fbbf24', '#22d3ee',
        '#fb923c', '#e879f9', '#84cc16', '#f472b6', '#14b8a6', '#c084fc',
    ];
    return {
        entries,
        labels: entries.map(entry => entry.label),
        counts: entries.map(entry => entry.count),
        colors: entries.map((_, index) => colors[index % colors.length]),
        labelToKey: Object.fromEntries(entries.map(entry => [entry.label, entry.key])),
    };
}

function renderGenreLegend(model) {
    const legend = document.getElementById('genreLegend');
    if (!legend) return;

    legend.innerHTML = model.entries.map((entry, index) => {
        const color = model.colors[index];
        const count = entry.count.toLocaleString();
        const rating = entry.avgRating !== undefined && entry.avgRating !== null
            ? ` · avg ${entry.avgRating}`
            : '';
        const key = escapeJsAttr(entry.key);
        return `<button type="button" class="genre-legend-item" role="listitem" data-genre="${escapeHtml(entry.label)}" data-genre-key="${escapeHtml(entry.key)}" style="--genre-color:${color}" aria-label="${escapeHtml(entry.label)}: ${count} songs${rating}" data-action="selectGenreLegend" data-genre-js-key="${key}">
            <span class="genre-legend-swatch" aria-hidden="true"></span>
            <span class="genre-legend-label">${escapeHtml(entry.label)}</span>
            <span class="genre-legend-count">${count}</span>
        </button>`;
    }).join('');
}

function selectGenreLegend(key) {
    if (key === 'Uncategorized') loadUncategorizedBreakdown();
}

function _initGenreFilterToggle() {
    const toggle = document.getElementById('genreFilterToggle');
    if (!toggle || toggle.dataset.bound) return;
    toggle.dataset.bound = '1';
    toggle.addEventListener('click', (e) => {
        const btn = e.target.closest('.genre-toggle-btn');
        if (!btn) return;
        const filter = btn.dataset.filter;
        if (filter === _genreFilterMode) return;
        _genreFilterMode = filter;
        toggle.querySelectorAll('.genre-toggle-btn').forEach(b => {
            b.classList.toggle('active', b.dataset.filter === filter);
            b.setAttribute('aria-checked', b.dataset.filter === filter ? 'true' : 'false');
        });
        if (_genreDistributionRaw) renderGenreChart(_genreDistributionRaw);
    });
}

function _filterGenreDistribution(genres) {
    if (_genreFilterMode === 'all') return genres;
    const filtered = {};
    for (const [genre, info] of Object.entries(genres)) {
        const liked = info.liked_count ?? info.count;
        if (liked > 0) {
            filtered[genre] = { ...info, count: liked };
        }
    }
    return filtered;
}

function renderGenreChart(genres) {
    const canvas = document.getElementById('genreChart');
    if (!canvas || window.__chartjsFailed) return;
    const filtered = _filterGenreDistribution(genres);
    window.loadLib('chartjs').then(() => {
        _drawGenreChart(filtered);
    }).catch(() => { window.__chartjsFailed = true; });
}

function _drawGenreChart(genres) {
    const canvas = document.getElementById('genreChart');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    
    if (genreChartInstance) { genreChartInstance.destroy(); genreChartInstance = null; }

    const model = genreBreakdownModel(genres);
    const { labels, counts, colors, labelToKey } = model;
    renderGenreLegend(model);
    window.__genreBreakdownModel = model;

    // The legend is deliberately HTML rather than Chart.js's canvas legend:
    // it remains readable, wraps naturally, and gives every color a real DOM
    // label that keyboard users and tests can inspect.
    const genreCountLabels = {
        id: 'genreCountLabels',
        afterDraw(chart) {
            const { ctx, chartArea } = chart;
            const meta = chart.getDatasetMeta(0);
            if (!meta || !meta.data) return;
            const data = chart.data.datasets[0].data;
            const total = data.reduce((sum, value) => sum + Number(value), 0) || 1;
            const radius = Math.min(chartArea.right - chartArea.left, chartArea.bottom - chartArea.top) * 0.31;
            ctx.save();
            ctx.textAlign = 'center';
            ctx.textBaseline = 'middle';
            ctx.font = '600 10px Inter, -apple-system, BlinkMacSystemFont, sans-serif';
            meta.data.forEach((arc, index) => {
                if (!arc || data[index] / total < 0.035) return;
                const midpoint = (arc.startAngle + arc.endAngle) / 2;
                const x = arc.x + Math.cos(midpoint) * radius;
                const y = arc.y + Math.sin(midpoint) * radius;
                ctx.shadowColor = 'rgba(0,0,0,0.55)';
                ctx.shadowBlur = 3;
                ctx.fillStyle = '#fff';
                ctx.fillText(String(data[index]), x, y);
            });
            ctx.restore();
        }
    };
    try { Chart.register(genreCountLabels); } catch (e) { /* already registered */ }

    genreChartInstance = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels,
            datasets: [{
                data: counts,
                backgroundColor: colors,
                borderColor: PALETTE.bgPrimary,
                borderWidth: 2,
            }]
        },
        options: {
            // Do not spread CHART_THEME here: its Cartesian x/y scales would
            // reserve invisible axis space and move the doughnut off-center.
            responsive: true,
            maintainAspectRatio: false,
            layout: { autoPadding: false, padding: 0 },
            cutout: '62%',
            onClick: (e, elements) => {
                if (elements.length > 0 && labels[elements[0].index] === 'Other') {
                    loadUncategorizedBreakdown();
                }
            },
            plugins: {
                legend: { display: false },
                tooltip: { ...CHART_THEME.plugins.tooltip, callbacks: {
                    label: (ctx) => {
                        const genre = ctx.label;
                        const lookupKey = labelToKey[genre] || genre;
                        const info = genres[lookupKey] || {};
                        return [
                            `${ctx.parsed} songs`,
                            `Avg rating: ${info.avg_rating || 'N/A'}`
                        ];
                    }
                }},
                genreCountLabels: true
            }
        }
    });
    window.__genreChart = genreChartInstance;
    
    const uncatHint = document.getElementById('uncategorizedHint');
    if (uncatHint && genres['Uncategorized']?.count > 0) {
        uncatHint.style.display = 'block';
    }
}


/**
 * Load and render the uncategorized breakdown panel.
 */
async function loadUncategorizedBreakdown() {
    const panel = document.getElementById('uncategorizedBreakdown');
    if (!panel) return;
    
    panel.style.display = 'block';
    panel.innerHTML = '<div class="loading-msg">Analyzing uncategorized songs...</div>';
    
    try {
        const resp = await fetch('/api/uncategorized-breakdown');
        const data = await resp.json();
        renderUncategorizedBreakdown(data);
    } catch (err) {
        panel.innerHTML = `<div class="error-msg">Failed to load breakdown: ${escapeHtml(err.message)}</div>`;
        console.error('Uncategorized breakdown error:', err);
    }
}

function renderUncategorizedBreakdown(data) {
    const panel = document.getElementById('uncategorizedBreakdown');
    if (!panel) return;
    
    const summary = data.summary || {};
    const total = summary.total_uncategorized || data.total || 0;
    
    let html = '<div class="breakdown-header">';
    html += `<h4>🔍 Uncategorized Song Breakdown (${total} songs)</h4>`;
    html += '<p class="subtitle">Click labels to see which songs fall through the cracks</p>';
    html += '</div>';
    
    // Summary cards
    html += '<div class="breakdown-summary">';
    html += `<div class="breakdown-stat"><span class="stat-num">${summary.by_known_artists || 0}</span><span class="stat-desc">Known artists</span></div>`;
    html += `<div class="breakdown-stat"><span class="stat-num">${summary.by_unknown_artists || 0}</span><span class="stat-desc">Unknown artists</span></div>`;
    html += `<div class="breakdown-stat"><span class="stat-num">${summary.no_artist_count || 0}</span><span class="stat-desc">No artist found</span></div>`;
    html += `<div class="breakdown-stat"><span class="stat-num">${summary.meta_count || 0}</span><span class="stat-desc">Meta entries</span></div>`;
    html += '</div>';
    
    // Known artists section
    const knownArtists = data.known_artists || {};
    const knownKeys = Object.keys(knownArtists);
    if (knownKeys.length > 0) {
        html += '<div class="breakdown-section">';
        html += '<h5 data-action="toggleNextSibling" class="section-toggle">📀 Known Artists (extraction missed them) ▼</h5>';
        html += '<div class="section-body">';
        html += '<table class="data-table compact"><thead><tr><th>Artist</th><th>Songs</th><th>Suggested Genre</th><th>Sample</th></tr></thead><tbody>';
        for (const [artist, info] of Object.entries(knownArtists)) {
            const genre = info.suggested_genre || '?';
            html += `<tr>
                <td><strong>${escapeHtml(artist)}</strong></td>
                <td>${info.count}</td>
                <td><span class="badge-genre">${escapeHtml(genre)}</span></td>
                <td class="sample-cell">${escapeHtml((info.sample_songs || [''])[0] || '')}</td>
            </tr>`;
        }
        html += '</tbody></table>';
        html += '</div></div>';
    }
    
    // Unknown artists section
    const unknownArtists = data.unknown_artists || {};
    const unknownKeys = Object.keys(unknownArtists);
    if (unknownKeys.length > 0) {
        html += '<div class="breakdown-section">';
        html += '<h5 data-action="toggleNextSibling" class="section-toggle">🎤 Unknown Artists (need classification) ▼</h5>';
        html += '<div class="section-body">';
        html += '<table class="data-table compact"><thead><tr><th>Artist</th><th>Songs</th><th>Sample</th></tr></thead><tbody>';
        for (const [artist, info] of Object.entries(unknownArtists).slice(0, 30)) {
            html += `<tr>
                <td><strong>${escapeHtml(artist)}</strong></td>
                <td>${info.count}</td>
                <td class="sample-cell">${escapeHtml((info.sample_songs || [''])[0] || '')}</td>
            </tr>`;
        }
        html += '</tbody></table>';
        html += '</div></div>';
    }
    
    // No-artist section
    const noArtist = data.no_artist || [];
    if (noArtist.length > 0) {
        html += '<div class="breakdown-section">';
        html += '<h5 data-action="toggleNextSibling" class="section-toggle">❓ No Artist Detected ▼</h5>';
        html += '<div class="section-body">';
        html += '<table class="data-table compact"><thead><tr><th>Title</th><th>Rating</th><th>Preview</th></tr></thead><tbody>';
        for (const entry of noArtist.slice(0, 20)) {
            html += `<tr>
                <td>${escapeHtml(entry.title || '')}</td>
                <td>${entry.rating || '—'}</td>
                <td class="sample-cell">${escapeHtml(entry.preview || '')}</td>
            </tr>`;
        }
        if (noArtist.length > 20) {
            html += `<tr><td colspan="3" class="more-cell">+ ${noArtist.length - 20} more entries</td></tr>`;
        }
        html += '</tbody></table>';
        html += '</div></div>';
    }
    
    // Meta entries
    const meta = data.meta_entries || [];
    if (meta.length > 0) {
        html += '<div class="breakdown-section">';
        html += '<h5 data-action="toggleNextSibling" class="section-toggle">📋 Meta / System Entries ▼</h5>';
        html += '<div class="section-body">';
        html += `<p class="subtitle">${meta.length} system entries (Announcements, roundups, etc.)</p>`;
        html += '</div></div>';
    }
    
    // Close button
    html += '<div class="breakdown-actions">';
    html += '<button class="btn btn-outline" data-action="closeUncategorizedBreakdown">Close</button>';
    html += '</div>';
    
    panel.innerHTML = html;
}

// ============================================================
// Ban List — manage blocked genres, artists, and songs
// ============================================================

async function loadBanList() {
    const container = document.getElementById('banListContent');
    if (!container) return;
    try {
        const resp = await fetch('/api/ban-list');
        const data = await resp.json();
        renderBanList(data, container);
    } catch (err) {
        container.innerHTML = '<div class="error-msg">Failed to load ban list</div>';
    }
}

function renderBanList(data, container) {
    const genres = data.genres || [];
    const artists = data.artists || [];
    const songs = data.songs || [];
    const total = genres.length + artists.length + songs.length;

    let html = `<div class="ban-list-stats">${total} item${total !== 1 ? 's' : ''} blocked</div>`;
    html += '<div class="ban-list-section"><h5>Genres</h5><div class="ban-list-tags">';
    if (genres.length === 0) html += '<span class="table-placeholder">None blocked</span>';
    for (const g of genres) {
        html += `<span class="ban-tag">${escapeHtml(g)} <button class="ban-remove" data-action="removeBanItem" data-ban-type="genres" data-ban-value="${escapeHtml(g)}" title="Unban">&times;</button></span>`;
    }
    html += '</div></div>';

    html += '<div class="ban-list-section"><h5>Artists</h5><div class="ban-list-tags">';
    if (artists.length === 0) html += '<span class="table-placeholder">None blocked</span>';
    for (const a of artists) {
        html += `<span class="ban-tag">${escapeHtml(a)} <button class="ban-remove" data-action="removeBanItem" data-ban-type="artists" data-ban-value="${escapeHtml(a)}" title="Unban">&times;</button></span>`;
    }
    html += '</div></div>';

    html += '<div class="ban-list-section"><h5>Songs</h5><div class="ban-list-tags">';
    if (songs.length === 0) html += '<span class="table-placeholder">None blocked</span>';
    for (const s of songs) {
        html += `<span class="ban-tag">${escapeHtml(s)} <button class="ban-remove" data-action="removeBanItem" data-ban-type="songs" data-ban-value="${escapeHtml(s)}" title="Unban">&times;</button></span>`;
    }
    html += '</div></div>';

    // Rating-derived auto-suppressions — the converged ban layer. These come
    // from low ratings (avg < 40 over 3+ songs), not the Ignore button, but
    // they hide the same way in Recommender/Weekly. Shown so you can see what
    // the engine is hiding and why, and lock any of them into a manual ban.
    const auto = data.auto_suppressed || {};
    const autoArtists = Object.entries(auto.artists || {});
    const autoGenres = Object.entries(auto.genres || {});
    if (autoArtists.length || autoGenres.length) {
        html += '<div class="ban-list-section ban-list-auto"><h5>🚫 Auto-suppressed from your ratings</h5>';
        html += '<p class="ban-list-auto-note">Your low ratings already hide these from Recommender &amp; Weekly, just like a manual Ignore. Rate higher to lift them, or lock one into a manual ban.</p>';
        if (autoArtists.length) {
            html += '<h6>Artists</h6><div class="ban-list-tags">';
            for (const [a, info] of autoArtists) {
                html += `<span class="ban-tag ban-tag-auto">${escapeHtml(a)} <span class="ban-auto-reason" title="${escapeHtml(info.reason)}">${escapeHtml(info.reason)}</span> <button class="ban-lock" data-action="lockAutoSuppression" data-ban-type="artists" data-ban-value="${escapeHtml(a)}" title="Also add to the manual ban list">Ban</button></span>`;
            }
            html += '</div>';
        }
        if (autoGenres.length) {
            html += '<h6>Genres</h6><div class="ban-list-tags">';
            for (const [g, info] of autoGenres) {
                html += `<span class="ban-tag ban-tag-auto">${escapeHtml(g)} <span class="ban-auto-reason" title="${escapeHtml(info.reason)}">${escapeHtml(info.reason)}</span> <button class="ban-lock" data-action="lockAutoSuppression" data-ban-type="genres" data-ban-value="${escapeHtml(g)}" title="Also add to the manual ban list">Ban</button></span>`;
            }
            html += '</div>';
        }
        html += '</div>';
    }

    // Add form
    html += `<div class="ban-list-add">
        <select id="banTypeSelect">
            <option value="genres">Genre</option>
            <option value="artists">Artist</option>
            <option value="songs">Song</option>
        </select>
        <input type="text" id="banValueInput" placeholder="e.g. Eurovision" data-keydown-action="banValueEnter" />
        <button class="btn btn-primary btn-sm" data-action="addBanItem">Block</button>
    </div>`;

    container.innerHTML = html;
}

async function addBanItem() {
    if (window.STATIC_MODE) {
        showToast('📄 Read-only snapshot — update the ban list from your local app');
        return;
    }
    const banType = document.getElementById('banTypeSelect').value;
    const value = document.getElementById('banValueInput').value.trim();
    if (!value) { showToast('Enter a value to block'); return; }
    try {
        const resp = await fetch('/api/ban-list/add', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ type: banType, value })
        });
        if (resp.ok) {
            document.getElementById('banValueInput').value = '';
            loadBanList();
            showToast(`Blocked "${value}"`);
        }
    } catch (err) {
        showToast('Failed to add ban item');
    }
}

async function lockAutoSuppression(banType, value) {
    // Promote a rating-derived suppression to a persistent manual ban so it
    // stays hidden even if the underlying ratings change.
    if (window.STATIC_MODE) {
        showToast('📄 Read-only snapshot — update the ban list from your local app');
        return;
    }
    try {
        const resp = await fetch('/api/ban-list/add', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ type: banType, value })
        });
        if (resp.ok) {
            loadBanList();
            showToast(`🔒 Banned "${value}"`);
        }
    } catch (err) {
        showToast('Failed to ban item');
    }
}

async function removeBanItem(banType, value) {
    if (window.STATIC_MODE) {
        showToast('📄 Read-only snapshot — update the ban list from your local app');
        return;
    }
    try {
        const resp = await fetch('/api/ban-list/remove', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ type: banType, value })
        });
        if (resp.ok) {
            loadBanList();
            showToast(`Unblocked "${value}"`);
        }
    } catch (err) {
        showToast('Failed to remove ban item');
    }
}

function closeUncategorizedBreakdown() {
    const panel = document.getElementById('uncategorizedBreakdown');
    if (panel) {
        panel.style.display = 'none';
        panel.innerHTML = '';
    }
}

function renderTopArtists(artists) {
    const container = document.getElementById('topArtistsTable');
    if (!artists || artists.length === 0) {
        container.innerHTML = '<div class="table-placeholder">No artist data available</div>';
        return;
    }

    let html = '<table class="data-table"><thead><tr><th>#</th><th>Artist</th><th>Avg Rating</th><th>Songs</th><th>Top Songs</th></tr></thead><tbody>';
    
    artists.forEach((artist, i) => {
        const rankClass = i < 3 ? 'top3' : '';
        const badgeClass = getRatingClass(artist.avg_rating);
        const topSongs = (artist.top_songs || []).map(s => s.title.split('(')[0].trim()).join(', ').slice(0, 60);
        
        html += `<tr>
            <td><span class="artist-rank ${rankClass}">${i + 1}</span></td>
            <td><strong>${artist.name}</strong></td>
            <td><span class="rating-badge ${badgeClass}">${artist.avg_rating}</span></td>
            <td>${artist.song_count}</td>
            <td style="font-size:12px;color:var(--text-muted)">${topSongs || '—'}</td>
        </tr>`;
    });
    
    html += '</tbody></table>';
    container.innerHTML = html;
}

function renderRecentReviews(reviews) {
    const container = document.getElementById('recentReviews');
    if (!reviews || reviews.length === 0) {
        container.innerHTML = '<div class="table-placeholder">No reviews yet</div>';
        return;
    }

    let html = '';
    reviews.forEach(r => {
        const badgeClass = getRatingClass(r.rating);
        html += `<div class="review-item">
            <div class="review-header">
                <span class="review-title">${escapeHtml(r.title)}</span>
                <span><span class="rating-badge ${badgeClass}">${r.rating || '?'}</span> <span class="review-date">${r.date}</span></span>
            </div>
            <div class="review-preview">${escapeHtml(r.preview || '')}</div>
        </div>`;
    });
    
    container.innerHTML = html;
}

