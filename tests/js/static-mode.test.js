/**
 * Static-snapshot mode tests. The static GitHub-Pages build flips utils.js
 * into read-only mode via data/config.json ({mode:'static'}). Here we stub
 * fetch BEFORE the scripts load so the shim's static branches actually run:
 * the 501 write guard, client-side /api/songs routing, the read-only banner,
 * and the static-mode Spotify shortcut.
 */
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { loadScript } from './setup.js';

const calls = [];

function staticFetchStub(url, init) {
    calls.push({ url: String(url), init });
    const body = (data) => new Response(JSON.stringify(data), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
    });
    if (url === 'data/config.json') return Promise.resolve(body({ mode: 'static' }));
    if (url === 'data/api/songs.json') {
        return Promise.resolve(body({
            songs: [
                { title: 'Static A', rating: 90, date: '2024-01-01', preview: '' },
                { title: 'Static B', rating: 70, date: '2024-02-01', preview: '' },
            ],
        }));
    }
    if (url === 'data/api/stats.json') return Promise.resolve(body({ rated_entries: 2 }));
    return Promise.resolve(body({ passthrough: url }));
}

let loaded = false;
function loadStaticApp() {
    if (loaded) return;
    vi.stubGlobal('fetch', vi.fn(staticFetchStub));
    loadScript('static/js/utils.js');
    loadScript('static/js/delegate.js');
    loadScript('static/js/delegate-handlers.js');
    loaded = true;
}

describe('static snapshot mode (utils.js shim)', () => {
    beforeEach(() => {
        loadStaticApp();
        document.body.innerHTML = '';
        calls.length = 0;
    });

    it('flags STATIC_MODE and installs the read-only banner', async () => {
        // staticModePromise resolves on the next microtask after load
        await new Promise((r) => setTimeout(r, 0));
        expect(window.STATIC_MODE).toBe(true);
        const banner = document.querySelector('.static-banner');
        expect(banner).not.toBeNull();
        expect(banner.textContent).toContain('Read-only snapshot');
    });

    it('write requests are rejected with 501 in static mode', async () => {
        const res = await window.fetch('/api/add-song', { method: 'POST' });
        expect(res.status).toBe(501);
        const data = await res.json();
        expect(data.error).toContain('Read-only');
    });

    it('GET /api/songs is served client-side from the snapshot dump', async () => {
        const res = await window.fetch('/api/songs?search=static&sort=rating&order=desc');
        expect(res.status).toBe(200);
        const data = await res.json();
        expect(data.total).toBe(2);
        expect(data.songs[0].rating).toBe(90);
    });

    it('GET /api/search-history is served client-side', async () => {
        const res = await window.fetch('/api/search-history?q=static');
        const data = await res.json();
        expect(data.total).toBe(2);
        expect(data.results[0].title).toContain('Static');
    });

    it('other GET /api/ paths map to snapshot files', async () => {
        const res = await window.fetch('/api/stats?limit=5');
        expect(res.status).toBe(200);
        const data = await res.json();
        expect(data.rated_entries).toBe(2);
        // the shim rewrote /api/stats → data/api/stats.json
        expect(calls.some(c => c.url === 'data/api/stats.json')).toBe(true);
    });

    it('non-/api requests pass straight through', async () => {
        const res = await window.fetch('https://example.com/other');
        const data = await res.json();
        expect(data.passthrough).toBe('https://example.com/other');
    });

    it('searchSpotifyTrack opens a Spotify search URL directly (no API)', async () => {
        const open = vi.fn();
        vi.stubGlobal('open', open);
        await window.searchSpotifyTrack('Nirvana', 'Lithium');
        expect(open).toHaveBeenCalledTimes(1);
        const url = open.mock.calls[0][0];
        expect(url).toContain('open.spotify.com/search/');
        expect(url).toContain(encodeURIComponent('Nirvana Lithium'));
        vi.unstubAllGlobals();
    });

    it('toggleListenedButton is blocked with a read-only toast', async () => {
        document.body.innerHTML = '<div id="toast"></div>';
        const btn = document.createElement('button');
        await window.toggleListenedButton(btn, 'A', 'S', false);
        expect(document.getElementById('toast').textContent).toContain('Read-only');
        expect(btn.classList.contains('is-listened')).toBe(false);
    });

    it('ignoreSong is blocked with a read-only toast', async () => {
        document.body.innerHTML = '<div id="toast"></div>';
        const btn = document.createElement('button');
        await window.ignoreSong(btn, 'A', 'S');
        expect(document.getElementById('toast').textContent).toContain('Read-only');
    });
});
