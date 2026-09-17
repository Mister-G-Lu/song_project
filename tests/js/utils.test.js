/**
 * Tests for utils.js helpers beyond the hardening layer: the escape
 * helpers' siblings (rating classes, toasts, cards) and the static-site
 * compatibility shim (staticApiFile / staticSongsResponse /
 * staticSearchResponse — client-side replicas of the Flask endpoints).
 */
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { setupDom, click, button } from './setup.js';

function jsonResponse(data, ok = true, status = 200) {
    return {
        ok,
        status,
        json: async () => data,
    };
}

describe('rating helpers (utils.js)', () => {
    beforeEach(() => setupDom());

    it('getRatingClass maps rating bands to css classes', () => {
        expect(window.getRatingClass(95)).toBe('perfect');
        expect(window.getRatingClass(85)).toBe('high');
        expect(window.getRatingClass(75)).toBe('good');
        expect(window.getRatingClass(65)).toBe('ok');
        expect(window.getRatingClass(5)).toBe('low');
        expect(window.getRatingClass(null)).toBe('');
    });

    it('getRatingColor returns a css color string', () => {
        const c = window.getRatingColor(80);
        expect(typeof c).toBe('string');
        expect(c.length).toBeGreaterThan(0);
    });
});

describe('showToast (utils.js)', () => {
    beforeEach(() => setupDom());

    it('creates, styles, and auto-hides the shared toast element', () => {
        vi.useFakeTimers();
        document.body.innerHTML = '<div id="toast"></div>';
        window.showToast('hello world');
        const toast = document.getElementById('toast');
        expect(toast.textContent).toBe('hello world');
        expect(toast.classList.contains('show')).toBe(true);
        vi.advanceTimersByTime(3100);
        expect(toast.classList.contains('show')).toBe(false);
        vi.useRealTimers();
    });
});

describe('song card builders (utils.js)', () => {
    beforeEach(() => setupDom());

    it('songCard escapes artist/title and uses delegated actions', () => {
        const html = window.songCard({
            artist: 'K Claudia & <b>Bold</b>',
            song: '"Quoted" Song',
            rating: 84,
            source: 'recommender',
            listened: false,
        });
        expect(html).toContain('data-action="searchSpotifyTrack"');
        expect(html).toContain('data-action="quickAddFromRecommender"');
        expect(html).toContain('data-action="toggleListened"');
        expect(html).toContain('data-action="ignoreSong"');
        expect(html).not.toContain('<b>Bold</b>');
        expect(html).toContain('&lt;b&gt;Bold&lt;/b&gt;');
        // No inline JS anywhere in the card.
        expect(html).not.toContain('onclick');
    });

    it('listenedButtonHtml reflects state via data attributes', () => {
        const on = window.listenedButtonHtml('A', 'S', true);
        expect(on).toContain('data-listened="true"');
        expect(on).toContain('is-listened');
        const off = window.listenedButtonHtml('A', 'S', false);
        expect(off).toContain('data-listened="false"');
    });

    it('ignoreButtonHtml carries artist/song data attributes', () => {
        const html = window.ignoreButtonHtml('A&B', 'S');
        expect(html).toContain('data-action="ignoreSong"');
        expect(html).toContain('data-artist="A&amp;B"');
    });
});

describe('static-site shim (utils.js)', () => {
    beforeEach(() => setupDom());

    it('staticApiFile maps api paths to snapshot files', () => {
        expect(window.staticApiFile('/api/stats')).toBe('data/api/stats.json');
        expect(window.staticApiFile('/api/songs')).toBe('data/api/songs.json');
        expect(window.staticApiFile('/api/challenges')).toBe('data/api/challenges.json');
        const params = new URLSearchParams('mode=opposite_taste');
        expect(window.staticApiFile('/api/challenges', params))
            .toBe('data/api/challenges-opposite.json');
    });

    it('staticSongsResponse filters, sorts, and paginates like the Flask endpoint', async () => {
        const dump = {
            songs: [
                { title: 'Song A', rating: 90, date: '2024-01-01' },
                { title: 'Song B', rating: 70, date: '2024-02-01' },
                { title: 'Love Song', rating: 85, date: '2024-03-01' },
                { title: 'Unrated', rating: null, date: '2024-04-01' },
                { title: 'song c', rating: 60, date: '2024-05-01' },
            ],
        };
        vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(dump)));

        // search + sort desc
        const params = new URLSearchParams('search=song&sort=rating&order=desc&limit=2&offset=0');
        const body = await (await window.staticSongsResponse(params)).json();
        expect(body.total).toBe(4); // everything with "song" in the title
        expect(body.songs.map(s => s.rating)).toEqual([90, 85]); // top 2 by rating

        // asc + pagination: sorted [60, 70, 85, 90] → skip 2, take 2
        const params2 = new URLSearchParams('sort=rating&order=asc&limit=2&offset=2');
        const body2 = await (await window.staticSongsResponse(params2)).json();
        expect(body2.songs.map(s => s.rating)).toEqual([85, 90]);

        // min_rating filter
        const params3 = new URLSearchParams('min_rating=80');
        const body3 = await (await window.staticSongsResponse(params3)).json();
        expect(body3.total).toBe(2);
        expect(body3.songs.every(s => s.rating >= 80)).toBe(true);

        // Unrated songs are excluded from the listing entirely, mirroring the
        // live endpoint (which only lists rated entries).
        const params4 = new URLSearchParams('search=unrated');
        const body4 = await (await window.staticSongsResponse(params4)).json();
        expect(body4.total).toBe(0);

        vi.unstubAllGlobals();
    });

    it('staticSearchResponse matches title/preview and caps at 30', async () => {
        // staticSongsData caches the dump after its first load; reset the cache
        // so this test's dump (not a previous test's) is what the shim reads.
        window.__resetStaticSongsCacheForTest();
        vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
            jsonResponse({ songs: Array.from({ length: 35 }, (_, i) => ({
                title: `Match ${i}`, rating: i, date: '2024-01-01', preview: 'x'.repeat(400),
            })) })));
        const res = await window.staticSearchResponse(new URLSearchParams('q=match'));
        const body = await res.json();
        expect(body.total).toBe(35);
        expect(body.results).toHaveLength(30); // capped
        expect(body.results[0].preview.length).toBeLessThanOrEqual(300);
        expect(body.results[0].title.length).toBeLessThanOrEqual(80);

        const miss = await window.staticSearchResponse(new URLSearchParams('q=zzz'));
        expect((await miss.json()).total).toBe(0);

        vi.unstubAllGlobals();
    });

    it('staticSongsData caches the dump after first fetch', async () => {
        window.__resetStaticSongsCacheForTest();
        const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ songs: [{ title: 'x' }] }));
        vi.stubGlobal('fetch', fetchMock);
        await window.staticSongsData();
        await window.staticSongsData();
        expect(fetchMock).toHaveBeenCalledTimes(1);
        vi.unstubAllGlobals();
    });

    it('fetch shim passes /api/ calls to real fetch when not in static mode', async () => {
        const realFetch = vi.fn().mockResolvedValue(jsonResponse({ ok: 1 }));
        vi.stubGlobal('fetch', realFetch);
        // staticModePromise resolved false (data/config.json fetch failed in jsdom),
        // so the shim must delegate straight through.
        const res = await window.fetch('/api/stats');
        expect(res.json()).resolves.toEqual({ ok: 1 });
        expect(realFetch).toHaveBeenCalledWith('/api/stats');
        vi.unstubAllGlobals();
    });
});

describe('apiFetch (utils.js)', () => {
    beforeEach(() => setupDom());

    it('resolves with parsed json on ok', async () => {
        vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse({ a: 1 })));
        await expect(window.apiFetch('/api/x')).resolves.toEqual({ a: 1 });
        vi.unstubAllGlobals();
    });

    it('throws on non-ok and logs', async () => {
        const errSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
        vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse({}, false, 500)));
        await expect(window.apiFetch('/api/x')).rejects.toThrow('HTTP 500');
        expect(errSpy).toHaveBeenCalled();
        errSpy.mockRestore();
        vi.unstubAllGlobals();
    });
});

describe('listened / ignore actions (utils.js)', () => {
    beforeEach(() => setupDom());

    it('toggleListenedButton posts and repaints the button', async () => {
        vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse({ listened: true })));
        document.body.innerHTML = '<div id="toast"></div>';
        const btn = button({
            'data-action': 'toggleListened',
            'data-artist': 'A',
            'data-song': 'S',
            'data-listened': 'false',
        });
        await window.toggleListenedButton(btn, 'A', 'S', false);
        expect(btn.classList.contains('is-listened')).toBe(true);
        expect(btn.textContent).toBe('✓ Listened');
        vi.unstubAllGlobals();
    });

    it('ignoreSong posts and removes the card', async () => {
        vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse({ ok: true })));
        document.body.innerHTML = '<div id="toast"></div>';
        const card = document.createElement('div');
        card.className = 'song-card';
        const btn = button({ 'data-action': 'ignoreSong', 'data-artist': 'A', 'data-song': 'S' });
        card.appendChild(btn);
        document.body.appendChild(card);
        await window.ignoreSong(btn, 'A', 'S');
        expect(document.querySelector('.song-card')).toBeNull();
        vi.unstubAllGlobals();
    });
});

describe('ViewControl.fetchRaw (delegate.js)', () => {
    beforeEach(() => setupDom());

    it('returns the raw Response for custom handling', async () => {
        const raw = { ok: true, status: 200, json: async () => ({ x: 1 }) };
        vi.stubGlobal('fetch', vi.fn().mockResolvedValue(raw));
        const res = await window.ViewControl.fetchRaw('fpraw', '/api/y');
        expect(res.ok).toBe(true);
        expect(await res.json()).toEqual({ x: 1 });
        vi.unstubAllGlobals();
    });

    it('supersedes a previous in-flight fetchRaw for the same view', async () => {
        const fetchMock = vi.fn()
            .mockImplementationOnce((_u, init) => new Promise((_res, rej) => {
                init.signal.addEventListener('abort', () =>
                    rej(new DOMException('Aborted', 'AbortError')));
            }))
            .mockImplementationOnce(() => Promise.resolve({ ok: true, json: async () => ({}) }));
        vi.stubGlobal('fetch', fetchMock);
        const p1 = window.ViewControl.fetchRaw('fp2', '/api/a');
        const p2 = window.ViewControl.fetchRaw('fp2', '/api/b');
        await expect(p2).resolves.toMatchObject({ ok: true });
        await expect(p1).rejects.toMatchObject({ name: 'AbortError' });
        vi.unstubAllGlobals();
    });
});
