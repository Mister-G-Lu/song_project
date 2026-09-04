/**
 * discover.js — Live discovery view
 *
 * Fresh tracks from artists adjacent to the ones you love, pulled live from
 * Deezer's public related-artists graph (no API key). Three comfort levels:
 *   easy   — nearest neighbours' best-known tracks
 *   medium — mid-list neighbours, deeper cuts, only artists you haven't rated
 *   hard   — far neighbours, low-fan artists, deep cuts ("challenge me")
 *
 * 30-second previews are fetched straight from Deezer in the browser via
 * JSONP, so they work both in the live app and the static GitHub Pages build.
 */

let discoverMode = 'easy';
let discoverData = null;
let discoverSeed = '';
let discoverTab = 'live';   // 'live' (Deezer neighbours) | 'challenge' (curated out-of-zone)

/** Switch between the two Discover panes. Each loads lazily on first show. */
function setDiscoverTab(tab) {
    if (tab !== 'live' && tab !== 'challenge') return;
    discoverTab = tab;
    document.querySelectorAll('#discoverTabs .discover-tab').forEach(b => {
        const on = b.dataset.tab === tab;
        b.classList.toggle('active', on);
        b.setAttribute('aria-selected', on ? 'true' : 'false');
    });
    document.getElementById('discoverLive').hidden = tab !== 'live';
    document.getElementById('discoverChallenge').hidden = tab !== 'challenge';
    if (tab === 'challenge') {
        if (!document.querySelector('#challengeContent .challenge-tier, #challengeContent .challenge-empty')) loadChallenges();
    } else if (!document.querySelector('#discoverGrid .discover-card')) {
        loadDiscover();
    }
    stopPreview();
}

const DISCOVER_MODE_META = {
    easy:   { label: 'Easy',   emoji: '☕', hint: 'Close neighbours of your favourites — should feel familiar.' },
    medium: { label: 'Medium', emoji: '🧭', hint: 'One step further out: artists you have never rated, deeper cuts.' },
    hard:   { label: 'Hard',   emoji: '🧗', hint: 'Far neighbours, small artists, deep album tracks. Challenge yourself.' },
};

async function loadDiscover(force) {
    const grid = document.getElementById('discoverGrid');
    if (!grid) return;
    showViewLoading('view-discover', `${DISCOVER_MODE_META[discoverMode].emoji} Finding ${discoverMode} picks...`);
    try {
        const params = new URLSearchParams({ mode: discoverMode, limit: '24' });
        if (discoverSeed) params.set('seed', discoverSeed);
        if (force) params.set('_', Date.now());
        const data = await apiFetch(`/api/discover?${params}`);
        discoverData = data;
        hideViewLoading('view-discover');
        renderDiscover(data);
    } catch (err) {
        hideViewLoading('view-discover');
        console.error('Discover load error:', err);
        renderErrorView(grid, 'Failed to load discoveries', () => loadDiscover());
    }
}

function setDiscoverMode(mode) {
    if (!DISCOVER_MODE_META[mode]) return;
    discoverMode = mode;
    document.querySelectorAll('#discoverModes .mode-btn').forEach(b => {
        b.classList.toggle('active', b.dataset.mode === mode);
    });
    const hint = document.getElementById('discoverModeHint');
    if (hint) hint.textContent = DISCOVER_MODE_META[mode].hint;
    loadDiscover();
}

function exploreFromArtist(name) {
    discoverSeed = (name || '').trim();
    const input = document.getElementById('discoverSeedInput');
    if (input) input.value = discoverSeed;
    if (discoverSeed && window.STATIC_MODE) {
        showToast('📄 Static snapshot — artist explore needs the local app; showing the pre-built batch');
    }
    loadDiscover();
}

function clearDiscoverSeed() {
    exploreFromArtist('');
}

function onDiscoverSeedKey(e) {
    if (e.key === 'Enter') {
        e.preventDefault();
        exploreFromArtist(e.target.value);
    }
}

function renderDiscover(data) {
    const grid = document.getElementById('discoverGrid');
    const meta = document.getElementById('discoverMeta');
    const picks = (data && data.picks) || [];

    // Header line: what fed this batch + how discovery has performed for you.
    if (meta) {
        const seedsUsed = data.seeds_used || [];
        const stats = (data.stats && data.stats.total) || {};
        let parts = [];
        if (data.seed) {
            parts.push(`Exploring outward from <strong>${escapeHtml(data.seed)}</strong> <button class="link-btn" onclick="clearDiscoverSeed()">✕ back to all favourites</button>`);
        } else if (seedsUsed.length) {
            const shown = seedsUsed.slice(0, 5).map(escapeHtml).join(', ');
            parts.push(`Seeded by ${seedsUsed.length} of your top artists (${shown}${seedsUsed.length > 5 ? ', …' : ''})`);
        }
        if (data.candidates) parts.push(`${data.candidates} candidate artists considered`);
        if (stats.rated) {
            parts.push(`<span title="Share of surfaced picks you later saved with 80+, out of the ones you rated">Hit rate so far: <strong>${stats.hit_rate}%</strong> (${stats.hits}/${stats.rated} rated)</span>`);
        }
        meta.innerHTML = parts.join(' · ');
    }

    if (!picks.length) {
        const offline = data && data.network_error;
        grid.innerHTML = `<div class="discover-empty">
            <div class="discover-empty-icon">${offline ? '📡' : '🕳️'}</div>
            <p>${offline
                ? 'Could not reach Deezer right now — live discovery needs an internet connection. Cached results (if any) are still used automatically.'
                : 'Nothing new found in this window. Try another mode, or explore from a specific artist.'}</p>
            <button class="btn btn-outline" onclick="loadDiscover(true)">Try again</button>
            <button class="btn btn-outline" onclick="setDiscoverTab('challenge')">Browse curated challenges instead</button>
        </div>`;
        return;
    }

    let html = '';
    for (const p of picks) {
        const viaChips = (p.via || []).slice(0, 3).map(v =>
            `<button class="via-chip" onclick="exploreFromArtist('${escapeJsAttr(v)}')" title="Explore outward from ${escapeHtml(v)}">${escapeHtml(v)}</button>`
        ).join('');
        const extra = `
            ${viaChips ? `<div class="via-row"><span class="via-label">via</span>${viaChips}</div>` : ''}
            <button class="link-btn explore-btn" onclick="exploreFromArtist('${escapeJsAttr(p.artist)}')" title="Use this artist as the seed">↳ explore from ${escapeHtml(p.artist)}</button>
        `;
        html += songCard({
            artist: p.artist,
            song: p.song,
            year: p.year || null,
            genre: p.known_artist ? 'deeper cut' : '',
            reason: p.reason,
            listened: p.listened,
            source: 'discover',
            cardClass: 'discover-card',
            cover: p.cover,
            deezerId: p.deezer_id,
            extraHtml: extra,
        });
    }
    grid.innerHTML = html;
}

async function refreshDiscover() {
    if (window.STATIC_MODE) {
        showToast('📄 Read-only snapshot — picks are rebuilt every Monday');
        return;
    }
    await loadDiscover(true);
    showToast('✨ New batch ready');
}

// ---------------------------------------------------------------------------
// Fresh releases — new to the world, from artists in your orbit
// ---------------------------------------------------------------------------

let freshLoaded = false;

async function loadFreshReleases() {
    const el = document.getElementById('freshReleases');
    if (!el || freshLoaded) return;
    el.innerHTML = '<div class="loading-msg">Checking for new releases...</div>';
    try {
        const data = await apiFetch('/api/fresh-releases?days=90&limit=24');
        freshLoaded = true;
        const rel = data.releases || [];
        const sub = document.getElementById('freshSubtitle');
        if (sub) sub.textContent = `Albums, EPs and singles from the last ${data.days} days by ${data.artists_checked} artists you rate well`;
        if (!rel.length) {
            el.innerHTML = `<div class="loading-msg">${data.network_error ? 'Could not reach Deezer.' : 'Nothing new from your artists in this window.'}</div>`;
            return;
        }
        el.innerHTML = rel.map(r => `
            <a class="release-card" href="${escapeHtml(r.link || '#')}" target="_blank" rel="noopener" title="Open on Deezer">
                ${r.cover ? `<img class="release-cover" src="${escapeHtml(r.cover)}" alt="" loading="lazy">` : '<div class="release-cover release-cover-empty">♪</div>'}
                <div class="release-body">
                    <div class="release-artist">${escapeHtml(r.artist)}</div>
                    <div class="release-title">${escapeHtml(r.title)}</div>
                    <div class="release-meta">${escapeHtml(r.record_type || 'release')} · ${escapeHtml(r.release_date)} · you rate them ${r.your_avg}</div>
                </div>
            </a>`).join('');
    } catch (err) {
        console.error('Fresh releases error:', err);
        el.innerHTML = '<div class="loading-msg">Failed to load releases</div>';
    }
}

function toggleFreshReleases(header) {
    const panel = header.closest('.fresh-panel');
    panel.classList.toggle('collapsed');
    if (!panel.classList.contains('collapsed')) loadFreshReleases();
}

// ---------------------------------------------------------------------------
// 30-second previews straight from Deezer (JSONP → works on static hosting)
// ---------------------------------------------------------------------------

let _dzCallbackSeq = 0;
let _activePreview = null;  // { audio, btn }

function deezerJsonp(path) {
    return new Promise((resolve, reject) => {
        const cb = `__dz_cb_${Date.now()}_${_dzCallbackSeq++}`;
        const script = document.createElement('script');
        const timer = setTimeout(() => { cleanup(); reject(new Error('Deezer timeout')); }, 8000);
        function cleanup() {
            clearTimeout(timer);
            delete window[cb];
            script.remove();
        }
        window[cb] = (data) => { cleanup(); resolve(data); };
        script.onerror = () => { cleanup(); reject(new Error('Deezer JSONP failed')); };
        script.src = `https://api.deezer.com${path}${path.includes('?') ? '&' : '?'}output=jsonp&callback=${cb}`;
        document.head.appendChild(script);
    });
}

function stopPreview() {
    if (_activePreview) {
        _activePreview.audio.pause();
        _activePreview.btn.classList.remove('is-playing');
        _activePreview.btn.innerHTML = '&#9654; Preview';
        _activePreview = null;
    }
}

async function togglePreview(btn, trackId) {
    if (_activePreview && _activePreview.btn === btn) { stopPreview(); return; }
    stopPreview();
    btn.classList.add('is-busy');
    try {
        const track = await deezerJsonp(`/track/${trackId}`);
        if (!track || !track.preview) throw new Error('No preview');
        const audio = new Audio(track.preview);
        audio.volume = 0.8;
        audio.onended = stopPreview;
        await audio.play();
        _activePreview = { audio, btn };
        btn.classList.add('is-playing');
        btn.innerHTML = '&#9632; Stop';
    } catch (err) {
        console.warn('Preview failed:', err);
        showToast('No preview available for this track');
    } finally {
        btn.classList.remove('is-busy');
    }
}
