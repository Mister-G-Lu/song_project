/**
 * evolution.js - Taste evolution timeline view
 */

let evolutionChartInstance = null;
let genreEvolutionChartInstance = null;
let cumulativeChartInstance = null;
let releaseYearChartInstance = null;
let evolutionData = null;

async function loadEvolution() {
    showViewLoading('view-evolution', '📈 Loading evolution data...');
    try {
        const res = await fetch('/api/evolution');
        const data = await res.json();
        evolutionData = data;
        hideViewLoading('view-evolution');
        updateEvolutionHeader(data);
        renderEvolutionSummary(data);
        renderEvolutionChart(data);
        renderYearlyTable(data.yearly);
        renderReleaseYearChart(data);
        renderReleaseYearTable(data.release_year_avg);
        populateGenreSelect(data.genre_evolution);
        renderCumulativeChart(data.cumulative);
        loadGeography();
    } catch (err) {
        hideViewLoading('view-evolution');
        console.error('Evolution load error:', err);
        document.getElementById('evolutionSummary').innerHTML = 
            '<div class="view-error"><span class="view-error-icon">⚠️</span><p>Failed to load evolution data</p><button class="btn btn-outline" onclick="loadEvolution()">Retry</button></div>';
    }
}

function updateEvolutionHeader(data) {
    const el = document.getElementById('evolutionSubtitle');
    const years = Object.keys(data.yearly || {});
    if (!el || years.length === 0) return;
    const minY = Math.min(...years.map(Number));
    const maxY = Math.max(...years.map(Number));
    const total = Object.values(data.yearly || {}).reduce((s, i) => s + (i.count || 0), 0);
    el.textContent = `How your music taste has changed across ${years.length} year${years.length === 1 ? '' : 's'} ` +
        `(${minY} → ${maxY}) · ${total.toLocaleString()} songs rated`;
}

function renderEvolutionSummary(data) {
    const container = document.getElementById('evolutionSummary');
    const yearlyEntries = Object.entries(data.yearly || {});

    let bestYear = '';
    let bestAvg = 0;
    for (const [year, info] of yearlyEntries) {
        if (info.avg > bestAvg) { bestAvg = info.avg; bestYear = year; }
    }

    const totalSongs = yearlyEntries.reduce((s, [, i]) => s + (i.count || 0), 0);

    // Meaningful trend: average of the last 6 months vs the 6 before them.
    // Falls back to first-vs-last when there's less history.
    const months = Object.entries(data.monthly_avg || {});
    let trendText = 'N/A';
    if (months.length >= 12) {
        const avg = a => a.reduce((s, v) => s + v, 0) / a.length;
        const diff = avg(months.slice(-6).map(([, v]) => v)) - avg(months.slice(-12, -6).map(([, v]) => v));
        trendText = `${diff >= 0 ? '+' : ''}${diff.toFixed(1)}`;
    } else if (months.length >= 2) {
        const diff = months[months.length - 1][1] - months[0][1];
        trendText = `${diff >= 0 ? '+' : ''}${diff.toFixed(1)}`;
    }

    const thisYear = new Date().getFullYear().toString();
    const thisYearInfo = yearlyEntries.find(([y]) => y === thisYear);
    const thisYearAvg = thisYearInfo ? thisYearInfo[1].avg : 'N/A';

    container.innerHTML = `
        <div class="evo-stat">
            <div class="evo-value">${yearlyEntries.length}</div>
            <div class="evo-label">Years of Reviews</div>
        </div>
        <div class="evo-stat">
            <div class="evo-value">${totalSongs.toLocaleString()}</div>
            <div class="evo-label">Songs Rated</div>
        </div>
        <div class="evo-stat">
            <div class="evo-value">${bestYear}</div>
            <div class="evo-label">Best Year (avg ${bestAvg.toFixed(1)})</div>
        </div>
        <div class="evo-stat">
            <div class="evo-value">${trendText}</div>
            <div class="evo-label">6-Month Rating Trend</div>
        </div>
        <div class="evo-stat">
            <div class="evo-value">${thisYearAvg}</div>
            <div class="evo-label">This Year Avg</div>
        </div>
    `;
}

function renderEvolutionChart(data) {
    const canvas = document.getElementById('evolutionChart');
    if (!canvas || window.__chartjsFailed) return;
    const ctx = canvas.getContext('2d');
    
    if (evolutionChartInstance) { evolutionChartInstance.destroy(); evolutionChartInstance = null; }

    const monthly = data.monthly_avg || {};
    const labels = Object.keys(monthly);
    const values = Object.values(monthly);

    if (labels.length === 0) {
        ctx.canvas.parentElement.innerHTML = '<div class="table-placeholder">Not enough data yet</div>';
        return;
    }

    // Zoom the y-axis into the data range so month-to-month shifts are visible,
    // but expand it (and keep it honest) when ratings drift outside 60–95.
    const lo = Math.min(...values);
    const hi = Math.max(...values);
    const yMin = Math.max(0, Math.min(60, Math.floor((lo - 5) / 5) * 5));
    const yMax = Math.max(95, Math.ceil((hi + 5) / 5) * 5);

    evolutionChartInstance = new Chart(ctx, {
        type: 'line',
        data: {
            labels,
            datasets: [{
                label: 'Avg Rating',
                data: values,
                borderColor: PALETTE.accent,
                backgroundColor: cssVarRgb('--accent-rgb', 0.1),
                fill: true,
                tension: 0.4,
                pointRadius: 2,
                pointHoverRadius: 5,
                pointBackgroundColor: PALETTE.accent,
                borderWidth: 2,
            }]
        },
        options: {
            ...CHART_THEME,
            scales: {
                y: { min: yMin, max: yMax, ...CHART_THEME.scales.y },
                x: { ...CHART_THEME.scales.x, ticks: { ...CHART_THEME.scales.x.ticks, font: { size: 10 }, maxTicksLimit: 20 } }
            },
            plugins: { legend: { display: false }, tooltip: { ...CHART_THEME.plugins.tooltip } }
        }
    });
}

function renderYearlyTable(yearly) {
    const container = document.getElementById('yearlyTable');
    if (!yearly || Object.keys(yearly).length === 0) {
        container.innerHTML = '<div class="table-placeholder">No yearly data</div>';
        return;
    }

    // Newest year first; trend compares each year against the (newer) year after it.
    const sorted = Object.entries(yearly).sort((a, b) => b[0].localeCompare(a[0]));
    const maxCount = Math.max(...sorted.map(([, i]) => i.count));
    const bestAvg = Math.max(...sorted.map(([, i]) => i.avg));
    let prevYear = null;
    let prevAvg = null;

    let html = '<table class="data-table"><thead><tr><th>Year</th><th>Avg Rating</th><th>Songs Rated</th><th>Highest</th><th>Trend</th></tr></thead><tbody>';

    for (const [year, info] of sorted) {
        const badgeClass = info.avg >= 85 ? 'perfect' : info.avg >= 80 ? 'high' : 'good';
        const isBest = info.avg === bestAvg ? ' class="row-best"' : '';
        const pct = Math.round((info.count / maxCount) * 100);

        let trend = '<span class="muted">—</span>';
        if (prevAvg !== null) {
            const diff = info.avg - prevAvg;
            const cls = diff > 0.05 ? 'trend-up' : diff < -0.05 ? 'trend-down' : 'muted';
            const arrow = diff > 0.05 ? '▲' : diff < -0.05 ? '▼' : '•';
            trend = `<span class="${cls}" title="vs ${prevYear}">${arrow} ${Math.abs(diff).toFixed(1)}</span>`;
        }
        prevYear = year;
        prevAvg = info.avg;

        html += `<tr${isBest}>
            <td><strong>${year}</strong></td>
            <td><span class="rating-badge ${badgeClass}">${info.avg}</span></td>
            <td><div class="count-cell"><span>${info.count}</span><div class="mini-bar"><div class="mini-bar-fill" style="width:${pct}%"></div></div></div></td>
            <td>${info.top_rating}</td>
            <td style="font-size:13px">${trend}</td>
        </tr>`;
    }
    
    html += '</tbody></table>';
    container.innerHTML = html;
}

// Color a bar by rating, using the same palette semantics as rating badges
// but with concrete hex values (Chart.js can't resolve CSS variables).
function _releaseYearColor(avg) {
    if (avg >= 95) return PALETTE.rating100;
    if (avg >= 90) return PALETTE.rating90;
    if (avg >= 80) return PALETTE.rating80;
    if (avg >= 70) return PALETTE.rating70;
    return PALETTE.textMuted;
}

// Which metric the release-year chart shows: 'avg' (mean rating of songs
// released that year) or 'count' (how many songs you rated that year).
let releaseYearChartMode = 'avg';
let releaseYearChartData = null;

function setReleaseYearChartMode(mode) {
    if (mode === releaseYearChartMode && releaseYearChartInstance) return;
    releaseYearChartMode = mode;
    document.querySelectorAll('#releaseYearChartToggle .sort-btn').forEach(b => {
        b.classList.toggle('active', b.dataset.ryMode === mode);
    });
    if (releaseYearChartData) renderReleaseYearChart(releaseYearChartData);
}

function renderReleaseYearChart(data) {
    const coverage = data.release_year_coverage || null;
    const coverageEl = document.getElementById('releaseYearCoverage');
    if (coverageEl && coverage) {
        const bySrc = Object.entries(coverage.by_source || {})
            .map(([k, v]) => `${k}: ${v}`).join(' · ');
        coverageEl.textContent = `✓ ${coverage.matched.toLocaleString()} / ${coverage.total.toLocaleString()} songs matched`;
        coverageEl.title = `Release years resolved from — ${bySrc}`;
    }

    const canvas = document.getElementById('releaseYearChart');
    if (!canvas || window.__chartjsFailed) return;
    const ctx = canvas.getContext('2d');

    if (releaseYearChartInstance) { releaseYearChartInstance.destroy(); releaseYearChartInstance = null; }

    releaseYearChartData = data;
    const years = data.release_year_avg || {};
    const labels = Object.keys(years);
    const values = Object.values(years);

    if (labels.length === 0) {
        ctx.canvas.parentElement.innerHTML = '<div class="table-placeholder">No release years detected in song titles</div>';
        return;
    }

    const showCount = releaseYearChartMode === 'count';
    const maxCount = Math.max(...values.map(v => v.count), 1);
    const countColor = (c) => `hsl(${200 - Math.round((c / maxCount) * 120)}, 60%, 50%)`; // blue → teal by volume

    // Swap the card title + subtitle (scoped to THIS card, not the first
    // .full-width on the page) so the view's metric is unambiguous.
    const ryCard = canvas.closest('.chart-card');
    if (ryCard) {
        const titleEl = ryCard.querySelector('.card-header h3');
        if (titleEl) titleEl.textContent = showCount ? 'Songs Rated by Song Release Year' : 'Avg Rating by Song Release Year';
        const subEl = ryCard.querySelector('.subtitle');
        if (subEl) subEl.textContent = showCount
            ? 'How many songs you rated were released each year — a volume view of where you explore'
            : 'Which eras of music you actually enjoyed most — release year resolved from the official song database, the enrichment cache, or the year in the title';
    }

    releaseYearChartInstance = new Chart(ctx, {
        type: 'bar',
        data: {
            labels,
            datasets: [{
                label: showCount ? 'Songs Rated' : 'Avg Rating',
                data: showCount ? values.map(v => v.count) : values.map(v => v.avg),
                backgroundColor: showCount
                    ? values.map(v => countColor(v.count))
                    : values.map(v => _releaseYearColor(v.avg)),
                borderColor: showCount
                    ? values.map(v => countColor(v.count))
                    : values.map(v => _releaseYearColor(v.avg)),
                borderWidth: 1,
                borderRadius: 4,
            }]
        },
        options: {
            ...CHART_THEME,
            scales: {
                y: showCount
                    ? { min: 0, suggestedMax: maxCount, ...CHART_THEME.scales.y }
                    : { min: 40, max: 100, ...CHART_THEME.scales.y },
                x: { ...CHART_THEME.scales.x, ticks: { ...CHART_THEME.scales.x.ticks, font: { size: 10 }, maxTicksLimit: 25 } }
            },
            plugins: {
                legend: { display: false },
                tooltip: {
                    ...CHART_THEME.plugins.tooltip,
                    callbacks: {
                        title: (ctx) => `Released ${labels[ctx[0].dataIndex]}`,
                        label: (ctx) => {
                            const d = values[ctx.dataIndex];
                            return showCount
                                ? `Songs rated: ${d.count}`
                                : `Avg: ${d.avg}/100 (${d.count} songs, best ${d.top_rating})`;
                        }
                    }
                }
            }
        }
    });
}

// Sort state for the Release Year table. key is one of 'year' | 'avg' | 'count';
// dir is 1 (ascending) or -1 (descending). Defaults to avg-desc, matching the
// original "years you enjoyed most first" ordering.
let releaseYearSort = { key: 'avg', dir: -1 };

// Cache the raw payload object so a header click re-sorts in place without
// re-fetching (and without re-wrapping an already-converted array).
let releaseYearData = null;

// Long-tail release years (1–2 songs each) are noisy, so show the busiest few
// by default and let the user expand to the full list.
const RELEASE_YEARS_VISIBLE = 25;
let releaseYearShowAll = false;

function toggleReleaseYearShowAll() {
    releaseYearShowAll = !releaseYearShowAll;
    renderReleaseYearTable(releaseYearData);
}

function _releaseYearSortArrow(key) {
    if (releaseYearSort.key !== key) return '⇅';
    return releaseYearSort.dir === 1 ? '▲' : '▼';
}

function sortReleaseYearBy(key) {
    // Clicking the currently-sorted column toggles direction; clicking another
    // column selects it with a sensible default (desc for numeric, asc for year).
    if (releaseYearSort.key === key) {
        releaseYearSort.dir *= -1;
    } else {
        releaseYearSort.key = key;
        releaseYearSort.dir = key === 'year' ? 1 : -1;
    }
    renderReleaseYearTable(releaseYearData);
}

function renderReleaseYearTable(releaseYearAvg) {
    const container = document.getElementById('releaseYearTable');
    if (!releaseYearAvg || Object.keys(releaseYearAvg).length === 0) {
        releaseYearData = null;
        container.innerHTML = '<div class="table-placeholder">No release years detected</div>';
        return;
    }

    releaseYearData = releaseYearAvg;
    const rows = Object.entries(releaseYearAvg);

    let sorted = [...rows];
    const { key, dir } = releaseYearSort;
    sorted.sort((a, b) => {
        let va, vb;
        if (key === 'year') { va = parseInt(a[0], 10); vb = parseInt(b[0], 10); }
        else if (key === 'count') { va = a[1].count; vb = b[1].count; }
        else { va = a[1].avg; vb = b[1].avg; }
        return (va - vb) * dir;
    });

    const visible = releaseYearShowAll ? sorted : sorted.slice(0, RELEASE_YEARS_VISIBLE);
    const maxCount = Math.max(...rows.map(([, d]) => d.count));

    // Keep the expand/collapse control next to the card title, above the scroll area.
    const toggleEl = document.getElementById('releaseYearToggle');
    if (toggleEl) {
        const totalYears = rows.length;
        toggleEl.innerHTML = totalYears > RELEASE_YEARS_VISIBLE
            ? `<button class="btn btn-outline btn-sm" onclick="toggleReleaseYearShowAll()">` +
              `${releaseYearShowAll ? `Show top ${RELEASE_YEARS_VISIBLE}` : `All ${totalYears} years`}</button>`
            : '';
    }

    const th = (label, k) =>
        `<button class="sort-btn ${releaseYearSort.key === k ? 'active' : ''}" ` +
        `onclick="sortReleaseYearBy('${k}')" title="Sort by ${label}">` +
        `${label} <span class="sort-arrow">${_releaseYearSortArrow(k)}</span></button>`;

    let html = '<table class="data-table"><thead><tr>' +
        `<th>${th('Release Year', 'year')}</th>` +
        `<th>${th('Avg Rating', 'avg')}</th>` +
        `<th>${th('Songs Rated', 'count')}</th>` +
        '<th>Highest</th><th>Share of Ratings</th>' +
        '</tr></thead><tbody>';

    for (const [year, info] of visible) {
        const badgeClass = info.avg >= 85 ? 'perfect' : info.avg >= 80 ? 'high' : 'good';
        const pct = Math.round((info.count / maxCount) * 100);
        html += `<tr>
            <td><strong>${year}</strong></td>
            <td><span class="rating-badge ${badgeClass}">${info.avg}</span></td>
            <td>${info.count}</td>
            <td>${info.top_rating}</td>
            <td><div class="mini-bar" title="${info.count} of ${maxCount} songs in the busiest year"><div class="mini-bar-fill" style="width:${pct}%"></div></div></td>
        </tr>`;
    }

    html += '</tbody></table>';
    container.innerHTML = html;
}

function populateGenreSelect(genreEvolution) {
    const select = document.getElementById('genreSelect');
    const entries = Object.entries(genreEvolution || {});
    const genres = entries.map(([g]) => g).sort();
    
    select.innerHTML = genres.map(g => `<option value="${escapeHtml(g)}">${escapeHtml(g)}</option>`).join('');
    
    if (genres.length > 0) {
        // Default to the genre with the most history, not the alphabetically first.
        let richest = entries[0];
        for (const e of entries) if (e[1].length > richest[1].length) richest = e;
        select.value = richest[0];
        updateGenreEvolutionChart();
    }
}

function updateGenreEvolutionChart() {
    if (!evolutionData) return;
    
    const genre = document.getElementById('genreSelect').value;
    const genreData = (evolutionData.genre_evolution || {})[genre] || [];

    const container = document.getElementById('genreChartContainer');
    const canvas = document.getElementById('genreEvolutionChart');
    if (!canvas || window.__chartjsFailed) return;

    // Sparse genres can't form a trend — show a helpful placeholder instead of
    // silently leaving a stale or blank chart.
    if (genreData.length < 2) {
        if (genreEvolutionChartInstance) { genreEvolutionChartInstance.destroy(); genreEvolutionChartInstance = null; }
        canvas.style.display = 'none';
        let ph = container.querySelector('.genre-placeholder');
        if (!ph) {
            ph = document.createElement('div');
            ph.className = 'table-placeholder genre-placeholder';
            container.appendChild(ph);
        }
        ph.innerHTML = `Not enough ${escapeHtml(genre)} ratings yet — rate more of them to see a trend`;
        return;
    }

    canvas.style.display = '';
    const ph = container.querySelector('.genre-placeholder');
    if (ph) ph.remove();

    const ctx = canvas.getContext('2d');
    
    if (genreEvolutionChartInstance) { genreEvolutionChartInstance.destroy(); genreEvolutionChartInstance = null; }

    genreEvolutionChartInstance = new Chart(ctx, {
        type: 'line',
        data: {
            labels: genreData.map(d => d.month),
            datasets: [{
                label: `${genre} Rating`,
                data: genreData.map(d => d.avg),
                borderColor: PALETTE.success,
                backgroundColor: cssVarRgb('--success-rgb', 0.1),
                fill: true,
                tension: 0.4,
                pointRadius: 3,
                pointBackgroundColor: PALETTE.success,
                borderWidth: 2,
            }]
        },
        options: {
            ...CHART_THEME,
            scales: {
                y: { min: 50, max: 100, ...CHART_THEME.scales.y },
                x: { ...CHART_THEME.scales.x, ticks: { ...CHART_THEME.scales.x.ticks, font: { size: 10 } } }
            },
            plugins: {
                legend: { display: false },
                tooltip: { ...CHART_THEME.plugins.tooltip, callbacks: {
                    label: (ctx) => {
                        const d = genreData[ctx.dataIndex];
                        return `Avg: ${d.avg}/100 (${d.count} songs)`;
                    }
                }}
            }
        }
    });
}

function renderCumulativeChart(data) {
    const canvas = document.getElementById('cumulativeChart');
    if (!canvas || window.__chartjsFailed) return;
    const ctx = canvas.getContext('2d');
    
    if (cumulativeChartInstance) { cumulativeChartInstance.destroy(); cumulativeChartInstance = null; }

    if (!data || data.length === 0) {
        ctx.canvas.parentElement.innerHTML = '<div class="table-placeholder">Not enough data</div>';
        return;
    }

    cumulativeChartInstance = new Chart(ctx, {
        type: 'line',
        data: {
            labels: data.map(d => d.date),
            datasets: [{
                label: 'Total Songs',
                data: data.map(d => d.total_songs),
                borderColor: PALETTE.warning,
                backgroundColor: cssVarRgb('--warning-rgb', 0.08),
                fill: true,
                tension: 0.4,
                pointRadius: 1,
                pointHoverRadius: 4,
                borderWidth: 2,
            }]
        },
        options: {
            ...CHART_THEME,
            scales: {
                y: { beginAtZero: true, ...CHART_THEME.scales.y },
                x: { ...CHART_THEME.scales.x, ticks: { ...CHART_THEME.scales.x.ticks, font: { size: 10 }, maxTicksLimit: 15 } }
            },
            plugins: {
                legend: { display: false },
                tooltip: { ...CHART_THEME.plugins.tooltip, callbacks: {
                    label: (ctx) => `Total: ${ctx.parsed.y.toLocaleString()} songs`
                }}
            }
        }
    });
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

// Convert ISO 2-letter country code to flag emoji
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

    // Country table — API returns a list, not a dict
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
