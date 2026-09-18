/**
 * Coverage for utils.js helpers not exercised elsewhere: cssVar palette
 * helpers, listened-toggle and ignore-song fetch flows, Spotify-track search
 * fallback branches, and the static-mode fetch shim's search/sort/paging.
 */
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { setupDom } from './setup.js';

/** Read the last JSON POST body captured by a fetch mock. */
function lastBody(fetchMock) {
    const call = fetchMock.mock.calls[fetchMock.mock.calls.length - 1];
    return JSON.parse(call[1].body);
}

describe('cssVar helpers (utils.js)', () => {
    beforeEach(() => setupDom());

    it('reads a defined custom property', () => {
        document.documentElement.style.setProperty('--test-var', '#123456');
        expect(window.cssVar('--test-var', 'fallback')).toBe('#123456');
    });

    it('returns the fallback for an undefined property', () => {
        expect(window.cssVar('--definitely-not-set-xyz', 'fb')).toBe('fb');
    });

    it('cssVarRgb wraps the value in rgba()', () => {
        document.documentElement.style.setProperty('--test-rgb', '12, 34, 56');
        expect(window.cssVarRgb('--test-rgb', 0.25)).toBe('rgba(12, 34, 56, 0.25)');
    });

    it('cssVarRgb falls back to black for unknown vars', () => {
        expect(window.cssVarRgb('--definitely-not-set-xyz', 0.5)).toBe('rgba(0, 0, 0, 0.5)');
    });
});

describe('toggleListenedButton fetch flow (utils.js)', () => {
    beforeEach(() => setupDom());

    function button(listened) {
        document.body.innerHTML = `
            <div id="toast"></div>
            <button id="btn" class="rec-btn rec-btn-listened">Mark Listened</button>`;
        return document.getElementById('btn');
    }

    it('POSTs the listened state and toasts success', async () => {
        const fetchMock = vi.fn().mockResolvedValue({ ok: true });
        vi.stubGlobal('fetch', fetchMock);
        const btn = button(false);

        await window.toggleListenedButton(btn, 'Artist', 'Song', false);

        expect(lastBody(fetchMock)).toEqual({
            artist: 'Artist', song: 'Song', listened: true,
        });
        expect(btn.classList.contains('is-listened')).toBe(true);
        expect(document.getElementById('toast').textContent).toContain('Marked');
        vi.unstubAllGlobals();
    });

    it('reverts the button and toasts on failure', async () => {
        vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 500 }));
        const btn = button(false);

        await window.toggleListenedButton(btn, 'Artist', 'Song', false);

        expect(document.getElementById('toast').textContent).toContain('Failed');
        expect(btn.classList.contains('is-busy')).toBe(false);
        vi.unstubAllGlobals();
    });
});

describe('ignoreSong fetch flow (utils.js)', () => {
    beforeEach(() => setupDom());

    it('adds to the ban list and removes the card', async () => {
        const fetchMock = vi.fn().mockResolvedValue({ ok: true });
        vi.stubGlobal('fetch', fetchMock);
        document.body.innerHTML = `
            <div id="toast"></div>
            <div class="song-card"><button id="btn" class="rec-btn rec-btn-ignore">✕ Ignore</button></div>`;
        const btn = document.getElementById('btn');

        await window.ignoreSong(btn, 'Artist', 'Song');

        expect(fetchMock.mock.calls[0][0]).toBe('/api/ban-list/add');
        expect(lastBody(fetchMock)).toEqual({ type: 'songs', value: 'Artist – Song' });
        expect(document.querySelector('.song-card')).toBeNull();
        expect(document.getElementById('toast').textContent).toContain("ignored");
        vi.unstubAllGlobals();
    });

    it('keeps the card and toasts on failure', async () => {
        vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 500 }));
        document.body.innerHTML = `
            <div id="toast"></div>
            <div class="song-card"><button id="btn">✕ Ignore</button></div>`;
        const btn = document.getElementById('btn');

        await window.ignoreSong(btn, 'Artist', 'Song');

        expect(document.querySelector('.song-card')).not.toBeNull();
        expect(document.getElementById('toast').textContent).toContain('Failed');
        vi.unstubAllGlobals();
    });
});

describe('searchSpotifyTrack fallback branches (utils.js)', () => {
    beforeEach(() => setupDom());

    it('falls back to a combined search when the exact lookup misses', async () => {
        const fetchMock = vi.fn()
            .mockResolvedValueOnce({ json: async () => ({}) })            // exact miss
            .mockResolvedValueOnce({ json: async () => ({ external_url: 'https://x/2' }) });
        vi.stubGlobal('fetch', fetchMock);
        vi.stubGlobal('open', vi.fn());
        document.body.innerHTML = '<div id="toast"></div>';

        await window.searchSpotifyTrack('Artist', 'Song');

        expect(fetchMock).toHaveBeenCalledTimes(2);
        expect(fetchMock.mock.calls[1][0]).toContain('Song%20Artist');
        expect(window.open).toHaveBeenCalledWith('https://x/2', '_blank', 'noopener,noreferrer');
        vi.unstubAllGlobals();
    });

    it('toasts a helpful message when both lookups miss', async () => {
        const fetchMock = vi.fn()
            .mockResolvedValue({ json: async () => ({}) });
        vi.stubGlobal('fetch', fetchMock);
        vi.stubGlobal('open', vi.fn());
        document.body.innerHTML = '<div id="toast"></div>';

        await window.searchSpotifyTrack('Artist', 'Song');

        expect(window.open).not.toHaveBeenCalled();
        expect(document.getElementById('toast').textContent).toContain("Couldn't find");
        vi.unstubAllGlobals();
    });

    it('blocks javascript: URLs returned by the API', async () => {
        const fetchMock = vi.fn()
            .mockResolvedValue({ json: async () => ({ external_url: 'javascript:alert(1)' }) });
        vi.stubGlobal('fetch', fetchMock);
        vi.stubGlobal('open', vi.fn());
        document.body.innerHTML = '<div id="toast"></div>';

        await window.searchSpotifyTrack('Artist', 'Song');

        expect(window.open).not.toHaveBeenCalled();
        expect(document.getElementById('toast').textContent).toContain('non-https');
        vi.unstubAllGlobals();
    });

    it('_openExternal allows https and passes noopener', () => {
        vi.stubGlobal('open', vi.fn());
        document.body.innerHTML = '<div id="toast"></div>';

        window._openExternal('https://open.spotify.com/track/1', 'x');
        expect(window.open).toHaveBeenCalledWith(
            'https://open.spotify.com/track/1', '_blank', 'noopener,noreferrer');
        vi.unstubAllGlobals();
    });
});

describe('listened/ignore button HTML builders (utils.js)', () => {
    beforeEach(() => setupDom());

    it('listenedButtonHtml reflects state in class, label and attrs', () => {
        const on = window.listenedButtonHtml('A', 'S', true);
        expect(on).toContain('is-listened');
        expect(on).toContain('✓ Listened');
        expect(on).toContain('data-listened="true"');
        const off = window.listenedButtonHtml('A', 'S', false);
        expect(off).toContain('Mark Listened');
        expect(off).toContain('data-listened="false"');
    });

    it('ignoreButtonHtml carries the action attributes', () => {
        const html = window.ignoreButtonHtml('A', 'S');
        expect(html).toContain('data-action="ignoreSong"');
        expect(html).toContain('data-artist="A"');
        expect(html).toContain('data-song="S"');
    });
});
