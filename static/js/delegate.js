/**
 * delegate.js - Event delegation, escape-by-default HTML, and view request control.
 *
 * Replaces the inline `onclick="fn('${escapeJsAttr(x)}')"` pattern:
 *   - ActionBus: ONE document-level click listener dispatches to handlers
 *     registered by name. Buttons declare `data-action="name"` plus
 *     `data-*` attributes; no string-built JS args, no double-escaping trap,
 *     and inline handlers are gone (CSP-friendly).
 *   - html: tagged template that escapes every interpolation by default.
 *     Opt out ONLY for trusted markup with html.raw(...).
 *   - Views: per-view AbortController (new load cancels the previous fetch)
 *     and a version token so stale responses never paint.
 *
 * Load order: after utils.js (fetch shim), before the view scripts.
 */
(function () {
    'use strict';

    // ============================================================
    // ActionBus — delegated click handling
    // ============================================================

    const handlers = Object.create(null);
    /** Retries registered by renderErrorView, keyed by function name. */
    const retryHandlers = Object.create(null);
    const warnedMissing = new Set();

    const ActionBus = {
        /**
         * Register a handler for data-action="name".
         * @param {string} name
         * @param {(ctx: {el: Element, dataset: DOMStringMap, event: MouseEvent}) => void} fn
         */
        register(name, fn) {
            if (typeof name !== 'string' || typeof fn !== 'function') {
                throw new TypeError(`ActionBus.register(${name}): handler must be a function`);
            }
            handlers[name] = fn;
        },

        /** Register an error-view retry callback by function name. */
        registerRetry(name, fn) {
            retryHandlers[name] = fn;
        },

        has(name) {
            return Object.prototype.hasOwnProperty.call(handlers, name);
        },

        /**
         * Dispatch the action declared on the element (or its closest ancestor).
         * Falls back to a global function of the same name taking (ctx) —
         * used by tests and by handlers not yet explicitly registered.
         * @param {Element} target
         * @param {MouseEvent} event
         * @returns {boolean} true if an action ran
         */
        dispatch(target, event) {
            const el = target && target.closest ? target.closest('[data-action]') : null;
            if (!el) return false;
            const name = el.dataset.action;
            let fn = handlers[name];
            if (!fn) {
                const globalFn = window[name];
                if (typeof globalFn === 'function') {
                    fn = globalFn;
                    if (!warnedMissing.has(name)) {
                        warnedMissing.add(name);
                        console.info(`[ActionBus] "${name}" resolved via window global — register it explicitly for CSP/testability.`);
                    }
                }
            }
            if (!fn) {
                if (!warnedMissing.has(name)) {
                    warnedMissing.add(name);
                    console.error(`[ActionBus] no handler registered for data-action="${name}"`);
                }
                return false;
            }
            try {
                fn({ el, dataset: el.dataset, event, target });
            } catch (err) {
                console.error(`[ActionBus] handler "${name}" failed:`, err);
            }
            return true;
        },

        /** Testing seam: drop all registrations. */
        _reset() {
            for (const k of Object.keys(handlers)) delete handlers[k];
            for (const k of Object.keys(retryHandlers)) delete retryHandlers[k];
            warnedMissing.clear();
        },
    };

    // One listener per delegated event type for the whole app. Each maps to
    // its own data attribute: click → data-action, change →
    // data-change-action, input → data-input-action, keydown →
    // data-keydown-action, submit → data-submit-action.
    const DELEGATED = [
        ['click', 'action'],
        ['change', 'change-action'],
        ['input', 'input-action'],
        ['keydown', 'keydown-action'],
        ['submit', 'submit-action'],
    ];
    for (const [type, attr] of DELEGATED) {
        document.addEventListener(type, (event) => {
            // Ignore modified clicks — users expect "open in new tab" to work.
            if (type === 'click' &&
                (event.defaultPrevented || event.button !== 0 ||
                 event.metaKey || event.ctrlKey || event.altKey || event.shiftKey)) {
                return;
            }
            const attrName = 'data-' + attr;
            const el = event.target && event.target.closest
                ? event.target.closest(`[${attrName}]`)
                : null;
            if (!el) return;
            const ctx = { el, dataset: el.dataset, event, target: event.target };
            const name = el.getAttribute(attrName);
            let fn = handlers[name];
            if (!fn) {
                const globalFn = window[name];
                if (typeof globalFn === 'function') {
                    fn = globalFn;
                    if (!warnedMissing.has(name)) {
                        warnedMissing.add(name);
                        console.info(`[ActionBus] "${name}" resolved via window global — register it explicitly for CSP/testability.`);
                    }
                }
            }
            if (!fn) {
                if (!warnedMissing.has(name)) {
                    warnedMissing.add(name);
                    console.error(`[ActionBus] no handler registered for ${attrName}="${name}"`);
                }
                return;
            }
            try {
                fn(ctx);
            } catch (err) {
                console.error(`[ActionBus] handler "${name}" failed:`, err);
            }
            // An action that ran owns the event: nav links must not navigate
            // (href="#") and delegated form submits must not POST the page.
            // EXCEPTION — plain submit buttons: preventDefault on the click of
            // a type=submit button cancels its default action, which IS the
            // form submission. When such a button carries no data-action of
            // its own and the click matched an ancestor (e.g. a modal overlay),
            // canceling the click silently kills the delegated form submit.
            // Preserve the native activation so the submit event fires (the
            // delegated submit handler prevents the page POST itself).
            if (type === 'submit') {
                event.preventDefault();
            } else {
                const target = event.target;
                const submitBtn = target && target.closest
                    ? target.closest('button[type="submit"], input[type="submit"]')
                    : null;
                const btnOwnsClick = submitBtn && submitBtn.hasAttribute('data-action');
                if (!submitBtn || btnOwnsClick) event.preventDefault();
            }
        });
    }

    window.ActionBus = ActionBus;

    // ============================================================
    // html — escape-by-default tagged template
    // ============================================================

    /**
     * A string whose HTML is already safe (escaped at creation time, or
     * explicitly trusted via html.raw). Subclassing String keeps every string
     * method working while letting nested templates interpolate without
     * double-escaping.
     */
    class SafeHtml extends String {}

    /**
     * Tagged template: escapes every interpolation by default.
     *   html`<b>${userTitle}</b>`            — safe, escaped
     *   html`<b>${html.raw(trusted)}</b>`    — explicit opt-out
     * Nested html`` results (and arrays of them) interpolate as-is — they
     * were already escaped when built. Plain strings are ALWAYS escaped.
     * @param {TemplateStringsArray} strings
     * @param {...any} values
     * @returns {SafeHtml} a String — usable as innerHTML or plain text
     */
    function html(strings, ...values) {
        let out = '';
        for (let i = 0; i < strings.length; i++) {
            out += strings[i];
            if (i >= values.length) break;
            const v = values[i];
            if (v == null) continue;
            if (v instanceof SafeHtml) { out += v; continue; }
            if (Array.isArray(v)) {
                out += v.map(item =>
                    item instanceof SafeHtml ? item : escapeHtml(item == null ? '' : String(item))
                ).join('');
                continue;
            }
            out += escapeHtml(String(v));
        }
        return new SafeHtml(out);
    }

    /** Mark a string as trusted HTML (does NOT escape — use sparingly). */
    html.raw = function raw(value) { return new SafeHtml(String(value)); };

    window.html = html;

    // ============================================================
    // View request control — abort + staleness guard
    // ============================================================

    const viewControllers = Object.create(null);
    const viewVersions = Object.create(null);

    const ViewControl = {
        /**
         * Abort any in-flight request for a view and fetch a new one.
         * Each call supersedes the previous: the old fetch rejects with
         * an AbortError the moment the new one starts.
         * @param {string} viewId
         * @param {string} url
         * @param {{init?: RequestInit, timeoutMs?: number}} [opts]
         * @returns {Promise<any>} parsed JSON, or rejects on failure
         */
        async fetch(viewId, url, opts) {
            const { init = {}, timeoutMs = 30000 } = opts || {};
            const prev = viewControllers[viewId];
            if (prev) prev.abort();

            const controller = new AbortController();
            viewControllers[viewId] = controller;
            const timer = setTimeout(() => controller.abort(), timeoutMs);

            try {
                const res = await fetch(url, { ...init, signal: controller.signal });
                if (!res.ok) throw new Error(`HTTP ${res.status}`);
                return await res.json();
            } finally {
                clearTimeout(timer);
                if (viewControllers[viewId] === controller) delete viewControllers[viewId];
            }
        },

        /**
         * Like fetch() but returns the raw Response (for callers that do
         * their own res.ok checks or parse non-JSON bodies).
         * @param {string} viewId
         * @param {string} url
         * @param {{init?: RequestInit, timeoutMs?: number}} [opts]
         * @returns {Promise<Response>}
         */
        async fetchRaw(viewId, url, opts) {
            const { init = {}, timeoutMs = 30000 } = opts || {};
            const prev = viewControllers[viewId];
            if (prev) prev.abort();

            const controller = new AbortController();
            viewControllers[viewId] = controller;
            const timer = setTimeout(() => controller.abort(), timeoutMs);

            try {
                return await fetch(url, { ...init, signal: controller.signal });
            } finally {
                clearTimeout(timer);
                if (viewControllers[viewId] === controller) delete viewControllers[viewId];
            }
        },

        /**
         * Take a render token for a view; compare with isCurrent() after
         * awaiting anything before painting the DOM.
         * @param {string} viewId
         * @returns {number} token to check later
         */
        beginRender(viewId) {
            const n = (viewVersions[viewId] || 0) + 1;
            viewVersions[viewId] = n;
            return n;
        },

        /** True iff `token` is still the latest render token for the view. */
        isCurrent(viewId, token) {
            return viewVersions[viewId] === token;
        },

        /** Testing seam. */
        _reset() {
            for (const k of Object.keys(viewControllers)) {
                try { viewControllers[k].abort(); } catch (e) { /* noop */ }
                delete viewControllers[k];
            }
            for (const k of Object.keys(viewVersions)) delete viewVersions[k];
        },
    };

    window.ViewControl = ViewControl;
})();
