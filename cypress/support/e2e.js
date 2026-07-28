// ============================================================
// Custom Cypress commands for the Music Taste Analyzer
// ============================================================

/**
 * Wait for a specific view to finish loading.
 * Checks view is active then waits for any loading spinner to clear.
 * Handles views that may not show a loading message at all.
 */
Cypress.Commands.add('waitForView', (viewId) => {
  cy.get(`#${viewId}`, { timeout: 15000 }).should('have.class', 'active');
  // Some views may not have a loading message — check existence first
  cy.get('body').then(($body) => {
    if ($body.find(`#${viewId} .loading-msg`).length > 0) {
      cy.get(`#${viewId} .loading-msg`, { timeout: 8000 }).should('not.exist');
    }
  });
});

/**
 * Navigate to a view by clicking the sidebar link.
 */
Cypress.Commands.add('navigateToView', (viewName) => {
  cy.get(`[data-view="${viewName}"]`).click();
  cy.waitForView(`view-${viewName}`);
});

/**
 * Assert no console errors were logged during the test.
 * Run in afterEach to catch stray errors.
 */
Cypress.Commands.add('assertNoConsoleErrors', () => {
  cy.window().then((win) => {
    // Read errors captured by the global error handler
    const errors = win.__cypressCapturedErrors || [];
    if (errors.length > 0) {
      const msg = errors.join('; ');
      errors.length = 0; // reset
      throw new Error(`Console error(s) detected: ${msg}`);
    }
  });
});

/**
 * Install console.error/warn capture to detect JS errors.
 * Called once per spec file in beforeEach.
 */
Cypress.Commands.add('captureConsoleErrors', () => {
  cy.window().then((win) => {
    if (!win.__cypressCapturedErrors) {
      win.__cypressCapturedErrors = [];
      const origError = win.console.error;
      win.console.error = (...args) => {
        const msg = args.join(' ');
        // Filter benign Chart.js ResizeObserver noise
        if (msg.includes('ResizeObserver')) return;
        win.__cypressCapturedErrors.push(msg);
        origError.apply(win.console, args);
      };
    }
  });
});

/**
 * Wait for the app to fully initialize (loading screen hidden, dashboard visible).
 */
Cypress.Commands.add('waitForApp', () => {
  cy.get('#loadingScreen', { timeout: 20000 }).should('have.class', 'hidden');
  cy.get('#view-dashboard').should('have.class', 'active');
});

// ============================================================
// Global hooks
// ============================================================

beforeEach(() => {
  // Capture console errors
  cy.captureConsoleErrors();

  // Ignore benign Chart.js ResizeObserver errors
  cy.on('uncaught:exception', (err) => {
    if (err.message && (
      err.message.includes('ResizeObserver') ||
      err.message.includes('chart') ||
      err.message.includes('ResizeObserver loop')
    )) {
      return false;
    }
    return true;
  });
});

afterEach(() => {
  // Check for console errors after each test
  cy.assertNoConsoleErrors();
});
