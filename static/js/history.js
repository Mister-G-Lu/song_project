/**
 * history.js - Review history search and browse view
 */

let historyOffset = 0;
const HISTORY_LIMIT = 50;
let historyTotal = 0;

async function loadSongs(reset = true) {
    if (reset) {
        historyOffset = 0;
        document.getElementById('historyList').innerHTML = '<div class="loading-msg">Loading...</div>';
    }
    
    showViewLoading('view-history', '📜 Loading review history...');

    const sort = document.getElementById('historySort')?.value || 'rating';
    const order = document.getElementById('historyOrder')?.value || 'desc';
    const minRating = document.getElementById('historyMinRating')?.value || '';

    try {
        const url = `/api/songs?sort=${sort}&order=${order}&limit=${HISTORY_LIMIT}&offset=${historyOffset}&min_rating=${minRating}`;
        const res = await fetch(url);
        const data = await res.json();
        hideViewLoading('view-history');

        historyTotal = data.total;
        
        if (reset) {
            document.getElementById('historyList').innerHTML = '';
        }

        renderHistoryItems(data.songs);
        
        document.getElementById('historyCount').textContent = `Showing ${Math.min(historyOffset + data.songs.length, historyTotal)} of ${historyTotal} songs`;
        
        const loadMoreBtn = document.getElementById('loadMoreBtn');
        loadMoreBtn.style.display = historyOffset + data.songs.length < historyTotal ? 'block' : 'none';
    } catch (err) {
        hideViewLoading('view-history');
        console.error('History load error:', err);
        if (reset) {
            document.getElementById('historyList').innerHTML = 
                '<div class="view-error"><span class="view-error-icon">⚠️</span><p>Failed to load history</p><button class="btn btn-outline" onclick="loadSongs(true)">Retry</button></div>';
        }
    }
}

function renderHistoryItems(songs) {
    const container = document.getElementById('historyList');

    songs.forEach(song => {
        const badgeClass = getRatingClass(song.rating);
        const ratingColor = getRatingColor(song.rating);

        const div = document.createElement('div');
        div.className = 'history-item';
        div.innerHTML = `
            <div class="hi-header">
                <span class="hi-title">${escapeHtml(song.title)}</span>
                <span class="hi-rating" style="color:${ratingColor}">${song.rating}/100</span>
            </div>
            <div class="hi-meta">${song.date} · <span class="rating-badge ${badgeClass}">${song.rating}</span></div>
            <div class="hi-preview">${escapeHtml(song.preview || '')}</div>
        `;
        container.appendChild(div);
    });
}

function loadMoreSongs() {
    historyOffset += HISTORY_LIMIT;
    loadSongs(false);
}

function searchHistory() {
    const query = document.getElementById('historySearch')?.value?.trim();
    const container = document.getElementById('historyList');
    const countContainer = document.getElementById('historyCount');

    if (!query) {
        loadSongs(true);
        return;
    }

    container.innerHTML = '<div class="loading-msg">Searching...</div>';

    // Capture the request ID so stale responses can be discarded
    const captureId = searchRequestId;

    fetch(`/api/search-history?q=${encodeURIComponent(query)}`)
        .then(res => res.json())
        .then(data => {
            // Stale-response guard: discard if a newer search was started
            if (captureId !== searchRequestId) return;
            container.innerHTML = '';
            countContainer.textContent = `Found ${data.total} results for "${query}"`;

            if (data.results.length === 0) {
                container.innerHTML = '<div class="loading-msg">No results found. Try a different search term.</div>';
                document.getElementById('loadMoreBtn').style.display = 'none';
                return;
            }

            data.results.forEach(r => {
                const badgeClass = getRatingClass(r.rating);
                const div = document.createElement('div');
                div.className = 'history-item';
                div.innerHTML = `
                    <div class="hi-header">
                        <span class="hi-title">${escapeHtml(r.title)}</span>
                        <span>${r.rating ? `<span class="rating-badge ${badgeClass}">${r.rating}</span>` : 'Unrated'}</span>
                    </div>
                    <div class="hi-meta">${r.date || ''}</div>
                    <div class="hi-preview">${escapeHtml(r.preview || '')}</div>
                `;
                container.appendChild(div);
            });
            document.getElementById('loadMoreBtn').style.display = 'none';
        })
        .catch(() => {
            container.innerHTML = '<div class="loading-msg">Search error</div>';
        });
}

let searchTimeout = null;
let searchRequestId = 0;
function debounceSearch() {
    if (searchTimeout) clearTimeout(searchTimeout);
    const myId = ++searchRequestId;
    searchTimeout = setTimeout(() => {
        // Stale-response guard: only process if no newer search fired
        if (myId === searchRequestId) {
            searchHistory();
        }
    }, 300);
}
