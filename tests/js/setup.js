/**
 * Shared DOM test environment: loads the real utils.js, delegate.js and
 * delegate-handlers.js scripts into jsdom exactly like the browser does
 * (plain <script> files, no bundler).
 *
 * Scripts run via node:vm so top-level declarations become globals like real
 * <script> tags. The ABSOLUTE filename is passed to runInThisContext so the
 * v8 coverage provider can attribute executed code back to the source files
 * for the 80% threshold gate.
 */
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { vi } from 'vitest';

const root = join(dirname(fileURLToPath(import.meta.url)), '..', '..');

/**
 * Evaluate a real project script in the current jsdom global context.
 * vm.runInThisContext mimics a <script> tag: top-level function/const
 * declarations land on globalThis (unlike new Function, which wraps them
 * in its own function scope).
 */
function loadScript(relPath) {
    const code = readFileSync(join(root, relPath), 'utf8');
    vm.runInThisContext(code, { filename: join(root, relPath) });
}

/**
 * Prepare a fresh DOM + script environment.
 * Top-level const declarations in the scripts cannot be re-evaluated in the
 * same vm context, so the scripts load ONCE; every call resets the mutable
 * state (DOM, bus registrations, view controllers) instead.
 */
let loaded = false;
export function setupDom() {
    document.body.innerHTML = '';
    if (!loaded) {
        vi.stubGlobal('Chart', vi.fn(function Chart() { this.destroy = vi.fn(); }));
        loadScript('static/js/utils.js');
        loadScript('static/js/delegate.js');
        loadScript('static/js/delegate-handlers.js');
        loaded = true;
    } else {
        window.ActionBus._reset();
        window.ViewControl._reset();
    }
    // Re-register central handlers (ActionBus._reset dropped them).
    if (loaded && typeof window.setupDelegatedHandlers === 'function') {
        window.setupDelegatedHandlers();
    }
}

/** Dispatch a real bubbling click from a target element. */
export function click(target) {
    target.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
}

/** Basic button element carrying delegation attributes. */
export function button(attrs, label) {
    const el = document.createElement('button');
    for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, v);
    el.textContent = label || 'click';
    document.body.appendChild(el);
    return el;
}

export { loadScript };
