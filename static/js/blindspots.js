/**
 * blindspots.js - Genre blind spots explorer
 */

async function loadBlindSpots() {
    showViewLoading('view-blindspots', '🔍 Exploring your blind spots...');
    try {
        const res = await fetch('/api/blind-spots');
        const data = await res.json();
        hideViewLoading('view-blindspots');
        renderTopGenres(data.top_loved_genres);
        renderBlindSpots(data.blind_spots);
        renderYearBlindSpots(data.year_blind_spots);
        loadGeography();
    } catch (err) {
        hideViewLoading('view-blindspots');
        console.error('Blind spots load error:', err);
        renderErrorView(document.getElementById('blindspotsGrid'), 'Failed to load blind spots', loadBlindSpots);
    }
}

function renderTopGenres(genres) {
    const container = document.getElementById('topGenrePills');
    if (!genres || genres.length === 0) {
        container.innerHTML = '<span class="table-placeholder">No genre data available</span>';
        return;
    }

    let html = '';
    genres.forEach(([genre, avg, count]) => {
        html += `<span class="genre-pill">
            ${escapeHtml(genre)}
            <span class="pill-rating">${avg}</span>
            <span style="font-size:11px;color:var(--text-muted)">(${count} songs)</span>
        </span>`;
    });
    container.innerHTML = html;
}

function renderYearBlindSpots(spots) {
    const container = document.getElementById('yearBlindspotsGrid');
    if (!spots || spots.length === 0) {
        container.innerHTML = '<div class="loading-msg">No release-year blind spots found yet — keep rating songs!</div>';
        return;
    }

    const kindMeta = {
        'disliked-era': { label: 'Disliked Era', emoji: '😐', cls: 'badge-low' },
        'under-explored': { label: 'Under-explored', emoji: '🕳️', cls: 'badge-new' },
    };

    let html = '';
    for (const spot of spots) {
        const km = kindMeta[spot.kind] || { label: spot.kind, emoji: '🎯', cls: '' };
        const songs = (spot.suggestion || [])
            .map(c => `${escapeHtml(c.artist)} – “${escapeHtml(c.song)}”`).join(' · ');
        html += `<div class="spot-card">
            <h4>${km.emoji} ${spot.year} <span class="spot-kind ${km.cls}">${km.label}</span></h4>
            <div class="spot-why">${escapeHtml(spot.why || '')}</div>
            ${songs ? `<div class="spot-artists">🎯 Try: ${songs}</div>` : ''}
        </div>`;
    }
    container.innerHTML = html;
}

function renderBlindSpots(spots) {
    const container = document.getElementById('blindspotsGrid');
    if (!spots || Object.keys(spots).length === 0) {
        container.innerHTML = '<div class="loading-msg">No blind spots identified yet.</div>';
        return;
    }

    let html = '';
    for (const [genre, info] of Object.entries(spots)) {
        html += `<div class="spot-card">
            <h4>${escapeHtml(genre)}</h4>
            <div class="spot-why">${escapeHtml(info.why || info.why_you || '')}</div>
            <div class="spot-expect">Expected enjoyment: ${info.expected_rating || '?'}</div>
            <div class="spot-artists">🎯 ${escapeHtml(info.suggestion || '')}</div>
        </div>`;
    }
    container.innerHTML = html;
}

// ---- Geographic Listening Profile ----

const GEO_REGION_COLORS = {
    'North America': '#3b82f6',
    'Europe': '#8b5cf6',
    'Asia': '#f59e0b',
    'South America': '#10b981',
    'Africa': '#ef4444',
    'Oceania': '#06b6d4',
    'Other': '#6b7280',
};

function countryFlag(code) {
    if (!code || code.length !== 2) return '';
    return String.fromCodePoint(0x1F1E6 + code.charCodeAt(0) - 65, 0x1F1E6 + code.charCodeAt(1) - 65);
}

const GEO_REGION_FLAGS = {
    'North America': '🌎', 'South America': '🌎',
    'Europe': '🌍', 'Africa': '🌍',
    'Asia': '🌏', 'Oceania': '🌏', 'Other': '🌐',
};

async function loadGeography() {
    const regionsEl = document.getElementById('geoRegions');
    const countriesEl = document.getElementById('geoCountries');
    const blindSpotsEl = document.getElementById('geoBlindSpots');
    const coverageEl = document.getElementById('geoCoverage');
    if (!regionsEl) return;

    try {
        const res = await fetch('/api/geography');
        const data = await res.json();
        renderGeography(data, regionsEl, countriesEl, blindSpotsEl, coverageEl);
    } catch (err) {
        console.error('Geography load error:', err);
        regionsEl.innerHTML = '<div class="table-placeholder">Failed to load geographic data</div>';
    }
}

function renderGeography(data, regionsEl, countriesEl, blindSpotsEl, coverageEl) {
    const regions = data.regions || [];
    const countries = data.countries || {};
    const blindSpots = data.blind_spots || [];
    const coverage = data.coverage || {};

    // Coverage badge
    if (coverageEl && coverage.songs_with_country != null) {
        coverageEl.textContent = `✓ ${coverage.songs_with_country.toLocaleString()} / ${coverage.total_songs.toLocaleString()} songs mapped`;
        coverageEl.title = `${coverage.unique_artists_with_country} / ${coverage.unique_artists_total} unique artists mapped to ${coverage.unique_countries} countries`;
    }

    // Region bar chart
    if (regions.length > 0) {
        const totalCount = regions.reduce((s, r) => s + r.count, 0);
        let html = '<div class="geo-region-bars">';
        for (const region of regions) {
            const pct = Math.round((region.count / totalCount) * 100);
            const color = GEO_REGION_COLORS[region.name] || '#6b7280';
            html += `<div class="geo-region-row">
                <div class="geo-region-label">
                    <span class="geo-region-dot" style="background:${color}"></span>
                    <span class="geo-region-name">${GEO_REGION_FLAGS[region.name] || '🌐'} ${escapeHtml(region.name)}</span>
                    <span class="geo-region-countries">${region.country_count} countries</span>
                </div>
                <div class="geo-region-bar-wrap">
                    <div class="geo-region-bar" style="width:${pct}%;background:${color}" title="${region.count} songs"></div>
                </div>
                <div class="geo-region-stats">
                    <span class="geo-region-count">${region.count.toLocaleString()}</span>
                    <span class="geo-region-avg">avg ${region.avg_rating}</span>
                </div>
            </div>`;
        }
        html += '</div>';
        regionsEl.innerHTML = html;
    }

    // Country table
    const countryEntries = Array.isArray(countries) ? countries.sort((a, b) => b.count - a.count) : Object.entries(countries).map(([code, info]) => ({ code, ...info })).sort((a, b) => b.count - a.count);

    if (countryEntries.length > 0) {
        let html = '<div class="geo-countries"><h4>Countries</h4><table class="data-table"><thead><tr>';
        html += '<th>Country</th><th>Songs</th><th>Avg Rating</th><th>Top Rating</th><th>Share</th>';
        html += '</tr></thead><tbody>';

        const maxCountryCount = Math.max(...countryEntries.map(c => c.count));
        for (const c of countryEntries) {
            const pct = Math.round((c.count / maxCountryCount) * 100);
            const badgeClass = c.avg_rating >= 85 ? 'perfect' : c.avg_rating >= 80 ? 'high' : 'good';
            html += `<tr>
                <td style="white-space:nowrap">${countryFlag(c.code)} <strong>${escapeHtml(c.name)}</strong></td>
                <td>${c.count.toLocaleString()}</td>
                <td><span class="rating-badge ${badgeClass}">${c.avg_rating}</span></td>
                <td>${c.top_rating != null ? c.top_rating : '—'}</td>
                <td><div class="mini-bar"><div class="mini-bar-fill" style="width:${pct}%"></div></div></td>
            </tr>`;
        }
        html += '</tbody></table></div>';
        countriesEl.innerHTML = html;
    }

    // Blind spots
    if (blindSpots.length > 0) {
        blindSpotsEl.innerHTML = `<div class="geo-blind-spots">
            <h4>📍 Blind Spots</h4>
            <p>You haven't rated any songs from: <strong>${blindSpots.map(r => escapeHtml(r)).join(', ')}</strong></p>
            <p class="muted">Try exploring music from these regions in the <a href="#" onclick="showView('challenges'); return false;">Challenges</a> section.</p>
        </div>`;
    } else {
        blindSpotsEl.innerHTML = '';
    }
}
