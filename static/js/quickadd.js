/**
 * quickadd.js - Quick-add songs you discover
 * FAB button + modal form + keyboard shortcut
 * Uses separate Artist + Song Name fields for better duplicate detection.
 */

let quickAddSongCount = 0;
let _artistList = [];  // cached artist list for autocomplete
let _suggestionIndex = -1;
let _addSource = null;  // tracks where the add was triggered from (e.g. 'conquest')

function openQuickAdd(prefillArtist, prefillSong) {
    if (window.STATIC_MODE) {
        showToast('📄 Read-only snapshot — add songs from your local app');
        return;
    }
    resetQuickAddForm();
    document.getElementById('quickAddForm').style.display = '';
    document.getElementById('qaSuccess').style.display = 'none';

    const overlay = document.getElementById('quickAddOverlay');
    overlay.classList.add('active');

    if (prefillArtist) {
        document.getElementById('qaArtist').value = prefillArtist;
    }
    if (prefillSong) {
        document.getElementById('qaSong').value = prefillSong;
    }

    document.getElementById(prefillArtist ? 'qaSong' : 'qaArtist').focus();
    document.body.style.overflow = 'hidden';

    // Load artist list for autocomplete (non-blocking)
    _loadArtistList();
}

function closeQuickAdd() {
    _addSource = null;
    const overlay = document.getElementById('quickAddOverlay');
    overlay.classList.remove('active');
    document.body.style.overflow = '';
    _hideSuggestions();

    setTimeout(() => {
        document.getElementById('quickAddForm').style.display = '';
        document.getElementById('qaSuccess').style.display = 'none';
    }, 300);
}

function resetQuickAddForm() {
    document.getElementById('quickAddForm').reset();
    document.getElementById('qaTitle').value = '';
    document.getElementById('quickAddForm').style.display = '';
    document.getElementById('qaSuccess').style.display = 'none';
    document.getElementById('qaDuplicateHint').style.display = 'none';
    resetQuickAddButton();
    _hideSuggestions();
    document.getElementById('qaArtist').focus();
}

function resetQuickAddButton() {
    document.getElementById('qaSubmitBtn').disabled = false;
    document.getElementById('qaSubmitBtn').textContent = 'Add Song';
}

/** Load the artist list from the API for autocomplete suggestions. */
async function _loadArtistList() {
    if (_artistList.length > 0) return;  // already cached
    try {
        const resp = await fetch('/api/stats');
        const data = await resp.json();
        if (data.top_artists) {
            _artistList = data.top_artists.map(a => ({
                name: a.name,
                count: a.song_count || a.count || 0
            }));
        }
    } catch (e) {
        // Non-critical — autocomplete just won't work
    }
}

/** Show artist autocomplete suggestions filtered by input. */
function _showSuggestions(query) {
    const container = document.getElementById('qaArtistSuggestions');
    if (!query || query.length < 1) {
        _hideSuggestions();
        return;
    }

    const q = query.toLowerCase();
    const matches = _artistList
        .filter(a => a.name.toLowerCase().includes(q))
        .slice(0, 8);

    if (matches.length === 0) {
        _hideSuggestions();
        return;
    }

    container.innerHTML = matches.map((a, i) =>
        `<div class="suggestion-item" data-index="${i}" data-name="${a.name.replace(/"/g, '&quot;')}" onclick="_selectArtist('${a.name.replace(/'/g, "\\'")}')">${a.name}<span class="suggestion-count">${a.count} songs</span></div>`
    ).join('');
    container.style.display = 'block';
    _suggestionIndex = -1;
}

function _hideSuggestions() {
    const el = document.getElementById('qaArtistSuggestions');
    if (el) el.style.display = 'none';
    _suggestionIndex = -1;
}

function _selectArtist(name) {
    document.getElementById('qaArtist').value = name;
    _hideSuggestions();
    document.getElementById('qaSong').focus();
}

/** Handle keyboard navigation in the suggestions dropdown. */
function _handleSuggestionKeys(e) {
    const container = document.getElementById('qaArtistSuggestions');
    if (!container || container.style.display === 'none') return false;

    const items = container.querySelectorAll('.suggestion-item');
    if (items.length === 0) return false;

    if (e.key === 'ArrowDown') {
        e.preventDefault();
        _suggestionIndex = Math.min(_suggestionIndex + 1, items.length - 1);
        _highlightSuggestion(items);
        return true;
    } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        _suggestionIndex = Math.max(_suggestionIndex - 1, 0);
        _highlightSuggestion(items);
        return true;
    } else if (e.key === 'Enter' && _suggestionIndex >= 0) {
        e.preventDefault();
        _selectArtist(items[_suggestionIndex].dataset.name);
        return true;
    } else if (e.key === 'Escape') {
        _hideSuggestions();
        return true;
    }
    return false;
}

function _highlightSuggestion(items) {
    items.forEach((item, i) => {
        item.classList.toggle('active', i === _suggestionIndex);
    });
}

/** Live duplicate check as the user fills in artist + song. */
let _dupCheckTimeout = null;
async function _liveDuplicateCheck() {
    clearTimeout(_dupCheckTimeout);
    const artist = document.getElementById('qaArtist').value.trim();
    const song = document.getElementById('qaSong').value.trim();
    const hint = document.getElementById('qaDuplicateHint');

    if (!song || song.length < 2) {
        hint.style.display = 'none';
        return;
    }

    _dupCheckTimeout = setTimeout(async () => {
        try {
            const resp = await fetch('/api/check-song', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ artist, song })
            });
            const data = await resp.json();
            if (data.exists) {
                hint.textContent = `⚠️ Looks like "${data.match || 'similar'}" match already in your collection`;
                hint.style.display = 'block';
            } else {
                hint.style.display = 'none';
            }
        } catch (e) {
            hint.style.display = 'none';
        }
    }, 400);
}

async function submitQuickAdd(event) {
    event.preventDefault();

    const artist = document.getElementById('qaArtist').value.trim();
    const song = document.getElementById('qaSong').value.trim();
    const rating = document.getElementById('qaRating').value.trim();
    const notes = document.getElementById('qaNotes').value.trim();
    const source = document.getElementById('qaSource').value;

    if (!artist && !song) {
        showToast('Please enter at least an artist or song name');
        return;
    }

    // Build the combined title for the CSV (backend expects a single title)
    const title = artist && song ? `${song} (${artist})` : artist || song;

    const submitBtn = document.getElementById('qaSubmitBtn');
    submitBtn.disabled = true;
    submitBtn.textContent = 'Checking for duplicates...';

    // Final duplicate check before saving
    try {
        const checkResp = await fetch('/api/check-song', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ artist, song })
        });
        const checkData = await checkResp.json();
        if (checkData.exists) {
            const confirmed = confirm(
                `This song appears to already be in your collection!\n\n` +
                `Artist: "${artist}"\nSong: "${song}"\n` +
                `Match: ${checkData.match || 'similar title'}\n\n` +
                `Do you still want to add it?`
            );
            if (!confirmed) {
                submitBtn.disabled = false;
                submitBtn.textContent = 'Add Song';
                return;
            }
        }
    } catch (e) {
        // Duplicate check is nice-to-have; proceed even if it fails
        console.warn('Duplicate check failed:', e);
    }

    // Build the notes with source info
    let fullNotes = notes;
    if (source && !fullNotes.includes(source)) {
        fullNotes = fullNotes ? `${fullNotes} [Found via: ${source}]` : `[Found via: ${source}]`;
    }

    try {
        const resp = await fetch('/api/add-song', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ title, rating: rating || '', notes: fullNotes })
        });

        const data = await resp.json();

        if (data.success) {
            quickAddSongCount++;
            document.getElementById('quickAddForm').style.display = 'none';
            document.getElementById('qaSuccess').style.display = 'block';
            resetQuickAddButton();

            // Refresh dashboard stats (including Top Artists)
            const statTotal = document.getElementById('statTotal');
            if (statTotal && statTotal.textContent !== '-') {
                const current = parseInt(statTotal.textContent.replace(/,/g, '')) || 0;
                statTotal.textContent = (current + 1).toLocaleString();
            }

            // Refresh recent reviews if visible
            const recentContainer = document.getElementById('recentReviews');
            if (recentContainer && recentContainer.querySelector('.review-item')) {
                fetch('/api/stats')
                    .then(r => r.json())
                    .then(d => {
                        if (d.recent_reviews && window.renderRecentReviews) {
                            renderRecentReviews(d.recent_reviews);
                        }
                    })
                    .catch(() => {});
            }

            // Refresh views — targeted if we know the source
            if (_addSource === 'conquest' && typeof loadYearConquest === 'function') {
                loadYearConquest();  // only refresh conquest section
            } else {
                refreshActiveViews();
            }
            _addSource = null;

            showToast(`Added "${song}" by ${artist} to your collection!`);
        } else {
            showToast(data.error || 'Failed to add song');
            submitBtn.disabled = false;
            submitBtn.textContent = 'Add Song';
        }
    } catch (err) {
        showToast('Connection error. Check that the server is running.');
        submitBtn.disabled = false;
        submitBtn.textContent = 'Add Song';
    }
}

// Export for use from recommender cards
function quickAddFromRecommender(artist, song, source) {
    document.getElementById('qaSource').value = source || 'recommender';
    openQuickAdd(artist, song);
}

// Keyboard shortcut: press 'A' to open quick-add; Escape to close
document.addEventListener('keydown', function(e) {
    const overlay = document.getElementById('quickAddOverlay');
    if (e.key === 'Escape' && overlay.classList.contains('active')) {
        closeQuickAdd();
        return;
    }
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' || e.target.tagName === 'SELECT') {
        // Handle suggestion navigation when artist field is focused
        if (e.target.id === 'qaArtist' && _handleSuggestionKeys(e)) return;
        return;
    }
    if (e.key === 'a' || e.key === 'A') {
        if (!overlay.classList.contains('active')) {
            openQuickAdd();
            e.preventDefault();
        }
    }
});

// Live duplicate check on artist/song input (debounced)
document.addEventListener('DOMContentLoaded', function() {
    const artistInput = document.getElementById('qaArtist');
    const songInput = document.getElementById('qaSong');

    if (artistInput) {
        artistInput.addEventListener('input', function() {
            _showSuggestions(this.value);
            _liveDuplicateCheck();
        });
        artistInput.addEventListener('blur', function() {
            // Delay hiding so click on suggestion registers
            setTimeout(_hideSuggestions, 200);
        });
        artistInput.addEventListener('focus', function() {
            if (this.value) _showSuggestions(this.value);
        });
    }
    if (songInput) {
        songInput.addEventListener('input', _liveDuplicateCheck);
    }
});
