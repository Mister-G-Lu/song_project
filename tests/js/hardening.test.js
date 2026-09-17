/**
 * Unit tests for the P1 hardening layer:
 *   - ActionBus event delegation (static/js/delegate.js)
 *   - delegate-handlers.js central registration
 *   - escape-by-default html`` tagged template (utils.js + delegate.js)
 *   - withViewLoading guarantee (utils.js)
 *   - ViewControl abort/staleness (delegate.js)
 */
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { setupDom, click, button } from './setup.js';

describe('escape helpers (utils.js)', () => {
    beforeEach(() => setupDom());

    it('escapeHtml neutralizes script injection', () => {
        const out = window.escapeHtml('<img src=x onerror=alert(1)>&"\'');
        expect(out).toBe("&lt;img src=x onerror=alert(1)&gt;&amp;\"'");
        expect(out).not.toContain('<img');
    });

    it('escapeHtml handles null/undefined', () => {
        expect(window.escapeHtml(null)).toBe('');
        expect(window.escapeHtml(undefined)).toBe('');
    });

    it('escapeJsAttr keeps quotes from terminating inline JS (legacy helper)', () => {
        const out = window.escapeJsAttr(`x'); alert(1); ('`);
        // quotes must arrive escaped (\') so they cannot terminate an attr string
        expect(out).toContain("\\'");
        expect(out).not.toBe(`x'); alert(1); ('`);
    });
});

describe('html tagged template (escape-by-default)', () => {
    beforeEach(() => setupDom());

    // html`` returns a SafeHtml (a String object that remembers it is
    // already-escaped). String() unwraps it for assertions; assigning to
    // innerHTML works directly because it stringifies implicitly.
    it('escapes every interpolation by default', () => {
        const evil = '<script>alert(1)</script>';
        const out = String(window.html`<b>${evil}</b>`);
        expect(out).toBe('<b>&lt;script&gt;alert(1)&lt;/script&gt;</b>');
    });

    it('interpolates safe strings normally', () => {
        expect(String(window.html`<i>${'plain'} ${42}</i>`)).toBe('<i>plain 42</i>');
    });

    it('skips null/undefined as empty', () => {
        expect(String(window.html`a${null}b${undefined}c`)).toBe('abc');
    });

    it('joins arrays of nested templates without double-escaping', () => {
        const items = ['<a>', 'b'];
        const out = window.html`<ul>${items.map(i => window.html`<li>${i}</li>`)}</ul>`;
        expect(String(out)).toBe('<ul><li>&lt;a&gt;</li><li>b</li></ul>');
    });

    it('plain strings are escaped even when another template already built them', () => {
        // A raw string that merely LOOKS like template output is still escaped —
        // only real SafeHtml instances (from html`` or html.raw) pass through.
        const notTemplate = '<li>nope</li>';
        const out = window.html`<ul>${[notTemplate]}</ul>`;
        expect(String(out)).toBe('<ul>&lt;li&gt;nope&lt;/li&gt;</ul>');
    });

    it('html.raw opts out explicitly for trusted markup', () => {
        const trusted = '<em>safe</em>';
        const out = window.html`<p>${window.html.raw(trusted)}</p>`;
        expect(String(out)).toBe('<p><em>safe</em></p>');
    });

    it('assignment to innerHTML renders the escaped markup', () => {
        const div = document.createElement('div');
        div.innerHTML = window.html`<b>${'<img src=x onerror=alert(1)>'}</b>`;
        expect(div.querySelector('img')).toBeNull();
        expect(div.querySelector('b')).not.toBeNull();
    });
});

describe('withViewLoading guarantee (utils.js)', () => {
    beforeEach(() => setupDom());

    function overlayCount(viewId) {
        return document.querySelectorAll(`#${viewId} .view-loading-overlay`).length;
    }

    it('removes the overlay on success', async () => {
        document.body.innerHTML = '<section id="view-x"><div class="content"></div></section>';
        await window.withViewLoading('view-x', 'Loading...', async () => { /* ok */ });
        expect(overlayCount('view-x')).toBe(0);
    });

    it('removes the overlay when fn throws (no handler)', async () => {
        document.body.innerHTML = '<section id="view-x"></section>';
        const errSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
        await window.withViewLoading('view-x', 'Loading...', async () => {
            throw new Error('boom');
        });
        expect(overlayCount('view-x')).toBe(0);
        expect(errSpy).toHaveBeenCalled();
        errSpy.mockRestore();
    });

    it('routes errors to onError AND still clears the overlay', async () => {
        document.body.innerHTML = '<section id="view-x"></section>';
        const onError = vi.fn();
        await window.withViewLoading('view-x', 'L', async () => { throw new Error('x'); }, { onError });
        expect(onError).toHaveBeenCalledTimes(1);
        expect(overlayCount('view-x')).toBe(0);
    });

    it('is a no-op for missing views', async () => {
        await expect(window.withViewLoading('no-such-view', 'L', async () => {}))
            .resolves.toBeUndefined();
    });
});

describe('ActionBus delegation (delegate.js)', () => {
    beforeEach(() => setupDom());

    it('dispatches a click to the registered handler with dataset context', () => {
        const fn = vi.fn();
        window.ActionBus.register('unitTest', fn);
        const btn = button({ 'data-action': 'unitTest', 'data-artist': 'A&b' });
        click(btn);
        expect(fn).toHaveBeenCalledTimes(1);
        const ctx = fn.mock.calls[0][0];
        expect(ctx.el).toBe(btn);
        expect(ctx.dataset.artist).toBe('A&b');
        expect(ctx.event.type).toBe('click');
    });

    it('dispatches from a child element via closest()', () => {
        const fn = vi.fn();
        window.ActionBus.register('parentAction', fn);
        const btn = button({ 'data-action': 'parentAction' });
        const span = document.createElement('span');
        btn.appendChild(span);
        click(span);
        expect(fn).toHaveBeenCalledTimes(1);
    });

    it('falls back to a same-named window global (migration seam)', () => {
        window.myLegacyHandler = vi.fn();
        const btn = button({ 'data-action': 'myLegacyHandler' });
        click(btn);
        expect(window.myLegacyHandler).toHaveBeenCalledTimes(1);
    });

    it('logs an error for unknown actions and does not throw', () => {
        const errSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
        const btn = button({ 'data-action': 'no_such_action' });
        expect(() => click(btn)).not.toThrow();
        expect(errSpy).toHaveBeenCalled();
        errSpy.mockRestore();
    });

    it('handler exceptions are contained (other clicks keep working)', () => {
        const errSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
        window.ActionBus.register('exploding', () => { throw new Error('kaboom'); });
        const ok = vi.fn();
        window.ActionBus.register('fine', ok);
        click(button({ 'data-action': 'exploding' }));
        click(button({ 'data-action': 'fine' }));
        expect(ok).toHaveBeenCalledTimes(1);
        expect(errSpy).toHaveBeenCalled();
        errSpy.mockRestore();
    });

    it('ignores modified clicks (ctrl/meta/shift/alt, right button)', () => {
        const fn = vi.fn();
        window.ActionBus.register('plain', fn);
        const btn = button({ 'data-action': 'plain' });
        btn.dispatchEvent(new MouseEvent('click', { bubbles: true, ctrlKey: true }));
        btn.dispatchEvent(new MouseEvent('click', { bubbles: true, metaKey: true }));
        btn.dispatchEvent(new MouseEvent('click', { bubbles: true, button: 2 }));
        expect(fn).not.toHaveBeenCalled();
        click(btn); // plain click still works
        expect(fn).toHaveBeenCalledTimes(1);
    });

    it('does not preventDefault when no action is found', () => {
        const link = document.createElement('a');
        link.href = '#';
        document.body.appendChild(link);
        const evt = new MouseEvent('click', { bubbles: true, cancelable: true });
        link.dispatchEvent(evt);
        expect(evt.defaultPrevented).toBe(false);
    });

    it('prevents default when an action runs', () => {
        window.ActionBus.register('pd', () => {});
        const btn = button({ 'data-action': 'pd' });
        const evt = new MouseEvent('click', { bubbles: true, cancelable: true });
        btn.dispatchEvent(evt);
        expect(evt.defaultPrevented).toBe(true);
    });

    it('dispatch(target, event) works as a public API on arbitrary elements', () => {
        const fn = vi.fn();
        window.ActionBus.register('apiAction', fn);
        const btn = button({ 'data-action': 'apiAction' });
        const evt = new MouseEvent('click');
        const ran = window.ActionBus.dispatch(btn, evt);
        expect(ran).toBe(true);
        expect(fn).toHaveBeenCalledTimes(1);
        // Non-action targets report false instead of throwing.
        const plain = document.createElement('div');
        expect(window.ActionBus.dispatch(plain, evt)).toBe(false);
        // null/undefined targets are safe too.
        expect(window.ActionBus.dispatch(null, evt)).toBe(false);
    });

    it('dispatch falls back to window globals and reports missing ones', () => {
        const info = vi.spyOn(console, 'info').mockImplementation(() => {});
        const err = vi.spyOn(console, 'error').mockImplementation(() => {});
        window.legacyGreeting = vi.fn();
        const btn = button({ 'data-action': 'legacyGreeting' });
        expect(window.ActionBus.dispatch(btn, new MouseEvent('click'))).toBe(true);
        expect(window.legacyGreeting).toHaveBeenCalledTimes(1);
        expect(info).toHaveBeenCalled(); // migration notice, once per name
        window.ActionBus.dispatch(btn, new MouseEvent('click'));
        expect(info).toHaveBeenCalledTimes(1); // deduped
        // No global, no registration → dispatch reports failure.
        const ghost = button({ 'data-action': 'neverRegistered' });
        expect(window.ActionBus.dispatch(ghost, new MouseEvent('click'))).toBe(false);
        expect(err).toHaveBeenCalled();
        info.mockRestore();
        err.mockRestore();
    });

    it('_reset clears registrations', () => {
        const fn = vi.fn();
        window.ActionBus.register('temp', fn);
        window.ActionBus._reset();
        const errSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
        click(button({ 'data-action': 'temp' }));
        expect(fn).not.toHaveBeenCalled();
        errSpy.mockRestore();
    });
});

describe('delegated change/input/keydown/submit (delegate.js)', () => {
    beforeEach(() => setupDom());

    it('change events dispatch via data-change-action', () => {
        const fn = vi.fn();
        window.ActionBus.register('onChangeFn', fn);
        const sel = document.createElement('select');
        sel.setAttribute('data-change-action', 'onChangeFn');
        document.body.appendChild(sel);
        sel.dispatchEvent(new Event('change', { bubbles: true }));
        expect(fn).toHaveBeenCalledTimes(1);
    });

    it('input events dispatch via data-input-action', () => {
        const fn = vi.fn();
        window.ActionBus.register('onInputFn', fn);
        const input = document.createElement('input');
        input.setAttribute('data-input-action', 'onInputFn');
        document.body.appendChild(input);
        input.dispatchEvent(new Event('input', { bubbles: true }));
        expect(fn).toHaveBeenCalledTimes(1);
    });

    it('keydown events dispatch via data-keydown-action', () => {
        const fn = vi.fn();
        window.ActionBus.register('onKeyFn', fn);
        const input = document.createElement('input');
        input.setAttribute('data-keydown-action', 'onKeyFn');
        document.body.appendChild(input);
        input.dispatchEvent(new KeyboardEvent('keydown', { bubbles: true, key: 'Enter' }));
        expect(fn).toHaveBeenCalledTimes(1);
    });

    it('submit events dispatch via data-submit-action and never POST the page', () => {
        const fn = vi.fn();
        window.ActionBus.register('onSubmitFn', fn);
        const form = document.createElement('form');
        form.setAttribute('data-submit-action', 'onSubmitFn');
        document.body.appendChild(form);
        const evt = new Event('submit', { bubbles: true, cancelable: true });
        form.dispatchEvent(evt);
        expect(fn).toHaveBeenCalledTimes(1);
        expect(evt.defaultPrevented).toBe(true);
    });
});

describe('registered handlers (delegate-handlers.js)', () => {
    beforeEach(() => setupDom());

    it('switchView passes data-view through', () => {
        const spy = vi.fn();
        window.switchView = spy;
        const link = button({ 'data-action': 'switchView', 'data-view': 'history' });
        click(link);
        expect(spy).toHaveBeenCalledWith('history');
    });

    it('quickAddFromConquest passes artist/song data attrs', () => {
        const spy = vi.fn();
        window.quickAddFromConquest = spy;
        click(button({
            'data-action': 'quickAddFromConquest',
            'data-artist': 'Nirvana',
            'data-song': 'Lithium',
        }));
        expect(spy).toHaveBeenCalledWith('Nirvana', 'Lithium');
    });

    it('removeBanItem passes type and value', () => {
        const spy = vi.fn();
        window.removeBanItem = spy;
        click(button({
            'data-action': 'removeBanItem',
            'data-ban-type': 'artists',
            'data-ban-value': 'Nickelback',
        }));
        expect(spy).toHaveBeenCalledWith('artists', 'Nickelback');
    });

    it('quickAddOverlayClick only closes for overlay-self clicks', () => {
        const closeSpy = vi.fn();
        window.closeQuickAdd = closeSpy;
        const overlay = button({ 'data-action': 'quickAddOverlayClick' });
        const inner = document.createElement('div');
        overlay.appendChild(inner);

        click(inner); // bubbled from inside → not a backdrop click
        expect(closeSpy).not.toHaveBeenCalled();

        click(overlay); // direct click on the overlay itself
        expect(closeSpy).toHaveBeenCalledTimes(1);
    });

    it('all static-markup actions resolve to real handlers', () => {
        // The full set of data-action names used by templates/index.html.
        const staticActions = [
            'switchView', 'toggleCollapsed', 'loadYearConquest', 'applyBackfill',
            'refreshBackfillPreview', 'refreshRecommendations', 'toggleReverseMe',
            'setReleaseYearChartMode', 'updateGenreEvolutionChart', 'setDiscoverTab',
            'setDiscoverMode', 'discoverSeedGo', 'refreshDiscover', 'toggleFreshReleases',
            'searchHistory', 'debounceSearch', 'loadSongs', 'loadMoreSongs',
            'quickAddOverlayClick', 'closeQuickAdd', 'openQuickAdd', 'resetQuickAddForm',
            'setConstellationMode', 'addBanItem', 'banValueEnter', 'toggleNextSibling',
            'closeUncategorizedBreakdown', 'updateThreshold',
        ];
        for (const name of staticActions) {
            expect(window.ActionBus.has(name), name).toBe(true);
        }
    });
});

describe('ViewControl abort/staleness (delegate.js)', () => {
    beforeEach(() => setupDom());

    function jsonOk(data) {
        return new Response(JSON.stringify(data), { status: 200 });
    }

    it('resolves parsed JSON on success', async () => {
        vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonOk({ hello: 1 })));
        await expect(window.ViewControl.fetch('v1', '/api/x')).resolves.toEqual({ hello: 1 });
        vi.unstubAllGlobals();
    });

    it('throws on non-OK responses', async () => {
        vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
            new Response('{"error":"nope"}', { status: 500 })));
        await expect(window.ViewControl.fetch('v2', '/api/x')).rejects.toThrow('HTTP 500');
        vi.unstubAllGlobals();
    });

    it('a newer fetch aborts the previous one for the same view', async () => {
        // Mock that honors the AbortSignal the way real fetch does.
        const fetchMock = vi.fn()
            .mockImplementationOnce((_url, init) => new Promise((_res, rej) => {
                init.signal.addEventListener('abort', () =>
                    rej(new DOMException('Aborted', 'AbortError')));
            }))
            .mockImplementationOnce(() => Promise.resolve(jsonOk({ newer: true })));
        vi.stubGlobal('fetch', fetchMock);

        const p1 = window.ViewControl.fetch('v3', '/api/slow');
        const p2 = window.ViewControl.fetch('v3', '/api/fast');
        await expect(p2).resolves.toEqual({ newer: true });
        await expect(p1).rejects.toMatchObject({ name: 'AbortError' });
        vi.unstubAllGlobals();
    });

    it('beginRender/isCurrent token marks superseded renders stale', () => {
        const t1 = window.ViewControl.beginRender('v4');
        expect(window.ViewControl.isCurrent('v4', t1)).toBe(true);
        const t2 = window.ViewControl.beginRender('v4');
        expect(window.ViewControl.isCurrent('v4', t1)).toBe(false);
        expect(window.ViewControl.isCurrent('v4', t2)).toBe(true);
    });

    it('_reset aborts in-flight controllers and clears tokens', async () => {
        vi.stubGlobal('fetch', vi.fn().mockImplementation((_u, init) => new Promise((_res, rej) => {
            init.signal.addEventListener('abort', () =>
                rej(new DOMException('Aborted', 'AbortError')));
        })));
        const p = window.ViewControl.fetch('v4r', '/api/x');
        window.ViewControl._reset();
        await expect(p).rejects.toMatchObject({ name: 'AbortError' });
        expect(window.ViewControl.isCurrent('v4r', 1)).toBe(false);
        vi.unstubAllGlobals();
    });

    it('times out slow requests', async () => {
        const fetchMock = vi.fn().mockImplementation((_url, init) => new Promise((res, rej) => {
            const t = setTimeout(() => res(jsonOk({})), 5000);
            init.signal.addEventListener('abort', () => {
                clearTimeout(t);
                rej(new DOMException('Aborted', 'AbortError'));
            });
        }));
        vi.stubGlobal('fetch', fetchMock);
        const p = window.ViewControl.fetch('v5', '/api/slow', { timeoutMs: 50 });
        await expect(p).rejects.toMatchObject({ name: 'AbortError' });
        vi.unstubAllGlobals();
    });
});
