/**
 * evolution.js - Taste evolution timeline view
 */

let evolutionChartInstance = null;
let genreEvolutionChartInstance = null;
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
        renderReleaseYearChart(data);
        renderReleaseYearTable(data.release_year_avg);
        populateGenreSelect(data.genre_evolution);
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
