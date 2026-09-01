/**
 * dashboard.js - Dashboard view with stats, charts, and tables
 */

let ratingChartInstance = null;
let genreChartInstance = null;

async function loadDashboard(prefetchedStats, skipBackfill) {
    try {
        const data = prefetchedStats || await (await fetch('/api/stats')).json();
        hideViewLoading('view-dashboard');
        renderStats(data);
        renderRatingChart(data.rating_distribution);
        renderGenreChart(data.genre_distribution);
        renderTopArtists(data.top_artists);
        renderRecentReviews(data.recent_reviews);
    } catch (err) {
        hideViewLoading('view-dashboard');
        console.error('Dashboard load error:', err);
    }
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

function renderGenreChart(genres) {
    const canvas = document.getElementById('genreChart');
    if (!canvas || window.__chartjsFailed) return;
    const ctx = canvas.getContext('2d');
    
    if (genreChartInstance) { genreChartInstance.destroy(); genreChartInstance = null; }

    const entries = Object.entries(genres || {}).filter(([,v]) => v.count > 0);
    // Rename 'Uncategorized' to 'Other' for better UX
    const renamed = entries.map(([k, v]) => [k === 'Uncategorized' ? 'Other' : k, v]);
    const sorted = renamed.sort((a, b) => b[1].count - a[1].count).slice(0, 12);
    // Map renamed labels back to original keys for tooltip lookup
    const labelToKey = { 'Other': 'Uncategorized' };
    
    const labels = sorted.map(([k]) => k);
    const counts = sorted.map(([,v]) => v.count);
    const avgRatings = sorted.map(([,v]) => v.avg_rating);
    
    const colors = labels.map((_, i) => {
        const hue = (i * 27) % 360;
        return `hsla(${hue}, 70%, 55%, 0.8)`;
    });

    // Store reference for click handling
    window.__genreChart = genreChartInstance;

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
            ...CHART_THEME,
            onClick: (e, elements) => {
                if (elements.length > 0) {
                    const idx = elements[0].index;
                    const label = labels[idx];
                    if (label === 'Other') {
                        loadUncategorizedBreakdown();
                    }
                }
            },
            plugins: {
                legend: {
                    position: 'right',
                    labels: {
                        color: PALETTE.textSecondary,
                        font: { size: 11 },
                        padding: 8,
                        usePointStyle: true,
                    }
                },
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
                }}
            }
        }
    });
    
    // Add a subtle "click Other for details" hint
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
        html += '<h5 onclick="this.nextElementSibling.classList.toggle(\'collapsed\')" class="section-toggle">📀 Known Artists (extraction missed them) ▼</h5>';
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
        html += '<h5 onclick="this.nextElementSibling.classList.toggle(\'collapsed\')" class="section-toggle">🎤 Unknown Artists (need classification) ▼</h5>';
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
        html += '<h5 onclick="this.nextElementSibling.classList.toggle(\'collapsed\')" class="section-toggle">❓ No Artist Detected ▼</h5>';
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
        html += '<h5 onclick="this.nextElementSibling.classList.toggle(\'collapsed\')" class="section-toggle">📋 Meta / System Entries ▼</h5>';
        html += '<div class="section-body">';
        html += `<p class="subtitle">${meta.length} system entries (Announcements, roundups, etc.)</p>`;
        html += '</div></div>';
    }
    
    // Close button
    html += '<div class="breakdown-actions">';
    html += '<button class="btn btn-outline" onclick="closeUncategorizedBreakdown()">Close</button>';
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
        html += `<span class="ban-tag">${escapeHtml(g)} <button class="ban-remove" onclick="removeBanItem('genres','${escapeJsAttr(g)}')" title="Unban">&times;</button></span>`;
    }
    html += '</div></div>';

    html += '<div class="ban-list-section"><h5>Artists</h5><div class="ban-list-tags">';
    if (artists.length === 0) html += '<span class="table-placeholder">None blocked</span>';
    for (const a of artists) {
        html += `<span class="ban-tag">${escapeHtml(a)} <button class="ban-remove" onclick="removeBanItem('artists','${escapeJsAttr(a)}')" title="Unban">&times;</button></span>`;
    }
    html += '</div></div>';

    html += '<div class="ban-list-section"><h5>Songs</h5><div class="ban-list-tags">';
    if (songs.length === 0) html += '<span class="table-placeholder">None blocked</span>';
    for (const s of songs) {
        html += `<span class="ban-tag">${escapeHtml(s)} <button class="ban-remove" onclick="removeBanItem('songs','${escapeJsAttr(s)}')" title="Unban">&times;</button></span>`;
    }
    html += '</div></div>';

    // Add form
    html += `<div class="ban-list-add">
        <select id="banTypeSelect">
            <option value="genres">Genre</option>
            <option value="artists">Artist</option>
            <option value="songs">Song</option>
        </select>
        <input type="text" id="banValueInput" placeholder="e.g. Eurovision" onkeydown="if(event.key==='Enter')addBanItem()" />
        <button class="btn btn-primary btn-sm" onclick="addBanItem()">Block</button>
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

