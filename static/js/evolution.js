/**
 * evolution.js - Taste evolution timeline view
 */

let evolutionChartInstance = null;
let genreEvolutionChartInstance = null;
let cumulativeChartInstance = null;
let evolutionData = null;

async function loadEvolution() {
    showViewLoading('view-evolution', '📈 Loading evolution data...');
    try {
        const res = await fetch('/api/evolution');
        const data = await res.json();
        evolutionData = data;
        hideViewLoading('view-evolution');
        renderEvolutionSummary(data);
        renderEvolutionChart(data);
        renderYearlyTable(data.yearly);
        populateGenreSelect(data.genre_evolution);
        renderCumulativeChart(data.cumulative);
    } catch (err) {
        hideViewLoading('view-evolution');
        console.error('Evolution load error:', err);
        document.getElementById('evolutionSummary').innerHTML = 
            '<div class="view-error"><span class="view-error-icon">⚠️</span><p>Failed to load evolution data</p><button class="btn btn-outline" onclick="loadEvolution()">Retry</button></div>';
    }
}

function renderEvolutionSummary(data) {
    const container = document.getElementById('evolutionSummary');
    const yearlyEntries = Object.entries(data.yearly || {});

    let currentYearAvg = 'N/A';
    let bestYear = '';
    let bestAvg = 0;
    let totalYears = yearlyEntries.length;

    for (const [year, info] of yearlyEntries) {
        if (info.avg > bestAvg) {
            bestAvg = info.avg;
            bestYear = year;
        }
        if (year === new Date().getFullYear().toString()) {
            currentYearAvg = info.avg;
        }
    }

    const allMonths = Object.values(data.monthly_avg || {});
    const trend = allMonths.length >= 2 ? 
        (allMonths[allMonths.length - 1] - allMonths[0]).toFixed(1) : 'N/A';
    const trendText = trend !== 'N/A' ? (trend >= 0 ? `+${trend}` : trend) : 'N/A';

    container.innerHTML = `
        <div class="evo-stat">
            <div class="evo-value">${totalYears}</div>
            <div class="evo-label">Years of Reviews</div>
        </div>
        <div class="evo-stat">
            <div class="evo-value">${bestYear}</div>
            <div class="evo-label">Best Year (avg ${bestAvg.toFixed(1)})</div>
        </div>
        <div class="evo-stat">
            <div class="evo-value">${trendText}</div>
            <div class="evo-label">Rating Trend</div>
        </div>
        <div class="evo-stat">
            <div class="evo-value">${currentYearAvg}</div>
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

    evolutionChartInstance = new Chart(ctx, {
        type: 'line',
        data: {
            labels,
            datasets: [{
                label: 'Avg Rating',
                data: values,
                borderColor: '#7c5cfc',
                backgroundColor: 'rgba(124, 92, 252, 0.1)',
                fill: true,
                tension: 0.4,
                pointRadius: 2,
                pointHoverRadius: 5,
                pointBackgroundColor: '#7c5cfc',
                borderWidth: 2,
            }]
        },
        options: {
            ...CHART_THEME,
            scales: {
                y: { min: 60, max: 95, ...CHART_THEME.scales.y },
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

    let html = '<table class="data-table"><thead><tr><th>Year</th><th>Avg Rating</th><th>Songs Rated</th><th>Highest</th><th>Trend</th></tr></thead><tbody>';
    
    const sorted = Object.entries(yearly).sort((a, b) => b[0].localeCompare(a[0]));
    let prevAvg = null;

    for (const [year, info] of sorted) {
        const badgeClass = info.avg >= 85 ? 'perfect' : info.avg >= 80 ? 'high' : 'good';
        let trend = '—';
        if (prevAvg !== null) {
            const diff = (info.avg - prevAvg).toFixed(1);
            trend = diff >= 0 ? `📈 +${diff}` : `📉 ${diff}`;
        }
        prevAvg = info.avg;

        html += `<tr>
            <td><strong>${year}</strong></td>
            <td><span class="rating-badge ${badgeClass}">${info.avg}</span></td>
            <td>${info.count}</td>
            <td>${info.top_rating}</td>
            <td style="font-size:13px">${trend}</td>
        </tr>`;
    }
    
    html += '</tbody></table>';
    container.innerHTML = html;
}

function populateGenreSelect(genreEvolution) {
    const select = document.getElementById('genreSelect');
    const genres = Object.keys(genreEvolution || {}).sort();
    
    select.innerHTML = genres.map(g => `<option value="${escapeHtml(g)}">${escapeHtml(g)}</option>`).join('');
    
    if (genres.length > 0) {
        select.value = genres[0];
        updateGenreEvolutionChart();
    }
}

function updateGenreEvolutionChart() {
    if (!evolutionData) return;
    
    const genre = document.getElementById('genreSelect').value;
    const genreData = (evolutionData.genre_evolution || {})[genre];
    
    if (!genreData || genreData.length < 2) return;

    const canvas = document.getElementById('genreEvolutionChart');
    if (!canvas || window.__chartjsFailed) return;
    const ctx = canvas.getContext('2d');
    
    if (genreEvolutionChartInstance) { genreEvolutionChartInstance.destroy(); genreEvolutionChartInstance = null; }

    genreEvolutionChartInstance = new Chart(ctx, {
        type: 'line',
        data: {
            labels: genreData.map(d => d.month),
            datasets: [{
                label: `${genre} Rating`,
                data: genreData.map(d => d.avg),
                borderColor: '#34d399',
                backgroundColor: 'rgba(52, 211, 153, 0.1)',
                fill: true,
                tension: 0.4,
                pointRadius: 3,
                pointBackgroundColor: '#34d399',
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
                borderColor: '#fbbf24',
                backgroundColor: 'rgba(251, 191, 36, 0.08)',
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
            plugins: { legend: { display: false }, tooltip: { ...CHART_THEME.plugins.tooltip } }
        }
    });
}
