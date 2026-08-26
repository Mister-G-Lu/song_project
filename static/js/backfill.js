/**
 * backfill.js — Backfill Missing Ratings panel
 * Extracted from dashboard.js for modularity.
 * Handles letter-grade extraction and tone-inference preview + apply flow.
 */

async function loadBackfillPreview() {
    const container = document.getElementById('backfillPreviewStats');
    try {
        const res = await fetch('/api/backfill-preview?method=all');
        const data = await res.json();
        renderBackfillPreview(data);
    } catch (err) {
        container.innerHTML = '<div class="backfill-error">⚠️ Failed to load preview. Is the server running?</div>';
    }
}

function renderBackfillPreview(data) {
    const container = document.getElementById('backfillPreviewStats');
    const btn = document.getElementById('backfillBtn');

    if (data.total_changes === 0) {
        container.innerHTML = '<div class="backfill-none">✅ No unrated entries found — all songs already have ratings!</div>';
        btn.disabled = true;
        return;
    }

    const src = data.changes_by_source || {};
    const pct = ((data.after.rated / data.after.total) * 100).toFixed(0);

    let detailHtml = '';
    if (data.changes && data.changes.length > 0) {
        detailHtml = '<div class="backfill-sample"><h4>Sample entries to be backfilled:</h4>';
        detailHtml += '<table class="data-table"><thead><tr><th>Title</th><th>Source</th><th>New Rating</th><th>Preview</th></tr></thead><tbody>';
        data.changes.slice(0, 10).forEach(c => {
            const sourceLabel = c.source === 'letter' ? `📝 ${c.grade_str}` : `🎯 ${c.source.replace('tone:', '')}`;
            detailHtml += `<tr>
                <td><strong>${escapeHtml(c.title)}</strong></td>
                <td><span class="backfill-source">${sourceLabel}</span></td>
                <td><span class="rating-badge ${getRatingClass(c.new_rating)}">${c.new_rating}</span></td>
                <td style="font-size:12px;color:var(--text-muted);max-width:200px;overflow:hidden;text-overflow:ellipsis">${escapeHtml(c.preview).slice(0,100)}</td>
            </tr>`;
        });
        detailHtml += '</tbody></table></div>';
    }

    container.innerHTML = `
        <div class="backfill-grid">
            <div class="backfill-stat">
                <div class="bf-value">+${data.total_changes}</div>
                <div class="bf-label">Ratings to Recover</div>
            </div>
            <div class="backfill-stat">
                <div class="bf-value">${src.letter_grades}</div>
                <div class="bf-label">From Letter Grades</div>
            </div>
            <div class="backfill-stat">
                <div class="bf-value">${src.tone_inference}</div>
                <div class="bf-label">From Tone Inference</div>
            </div>
            <div class="backfill-stat">
                <div class="bf-value">${pct}%</div>
                <div class="bf-label">Coverage After</div>
            </div>
        </div>
        <div class="backfill-compare">
            <span class="bf-before">Before: ${data.before.rated} rated (avg ${data.before.avg_rating})</span>
            <span class="bf-arrow">→</span>
            <span class="bf-after">After: <strong>${data.after.rated}</strong> rated (avg <strong>${data.after.avg_rating}</strong>)</span>
        </div>
    `;

    document.getElementById('backfillDetail').innerHTML = detailHtml;
    btn.disabled = false;
}

async function refreshBackfillPreview() {
    const btn = document.getElementById('backfillBtn');
    btn.disabled = true;
    btn.textContent = '⟳ Loading...';
    await loadBackfillPreview();
    btn.textContent = '⚡ Apply Backfill';
    btn.disabled = false;
}

async function applyBackfill() {
    if (window.STATIC_MODE) {
        showToast('📄 Read-only snapshot — backfill writes to the CSV and needs the local app');
        return;
    }
    const btn = document.getElementById('backfillBtn');
    if (btn.disabled) return;

    if (!confirm('This will write recovered ratings to your CSV file. The original data will be preserved but ratings will be added to unrated entries. Continue?')) {
        return;
    }

    btn.disabled = true;
    btn.textContent = '⟳ Applying...';

    try {
        const res = await fetch('/api/backfill-ratings', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ method: 'all' })
        });
        const data = await res.json();

        if (data.error) {
            showToast(`⚠️ ${data.error}`);
            btn.disabled = false;
            btn.textContent = '⚡ Apply Backfill';
            return;
        }

        showToast(`✅ Backfilled ${data.total_changes} ratings! ${data.after.rated} songs now rated (avg ${data.after.avg_rating})`);
        renderBackfillPreview(data);

        // Reload dashboard stats (skip backfill preview — POST already has the data)
        loadDashboard(null, true);
    } catch (err) {
        showToast(`⚠️ Error applying backfill: ${err.message}`);
        btn.disabled = false;
        btn.textContent = '⚡ Apply Backfill';
    }
}
