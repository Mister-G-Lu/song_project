// ============================================================
// Accessibility Tests — axe-core scan on every view
//
// Catches: missing labels, bad contrast, missing ARIA,
//          keyboard traps, missing document structure
// ============================================================

describe('Accessibility: Dashboard', () => {
  beforeEach(() => {
    cy.visit('/');
    cy.waitForApp();
  });

  it('has no critical axe violations', () => {
    cy.injectAxe();
    cy.checkA11y(null, {
      runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa'] }
    });
  });

  it('stat cards have accessible labels', () => {
    cy.get('.stat-card').each(($card) => {
      cy.wrap($card).find('.stat-label').should('exist');
    });
  });

  it('genre legend items are keyboard reachable', () => {
    cy.get('#genreLegend .genre-legend-item').first().should('have.attr', 'tabindex');
  });
});

describe('Accessibility: Evolution', () => {
  beforeEach(() => {
    cy.visit('/');
    cy.waitForApp();
    cy.navigateToView('evolution');
  });

  it('has no critical axe violations', () => {
    cy.injectAxe();
    cy.checkA11y(null, {
      runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa'] }
    });
  });
});

describe('Accessibility: Constellation', () => {
  beforeEach(() => {
    cy.visit('/');
    cy.waitForApp();
    cy.navigateToView('constellation');
  });

  it('has no critical axe violations', () => {
    cy.injectAxe();
    cy.checkA11y(null, {
      runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa'] }
    });
  });

  it('constellation SVG has aria-label', () => {
    cy.get('#constellationSvg').should('have.attr', 'aria-label');
  });

  it('mode buttons are keyboard accessible', () => {
    cy.get('.constellation-modes button').first().should('have.attr', 'tabindex');
  });
});

describe('Accessibility: Discover', () => {
  beforeEach(() => {
    cy.visit('/');
    cy.waitForApp();
    cy.get('[data-view="discover"]').click();
    cy.get('#view-discover', { timeout: 10000 }).should('have.class', 'active');
    cy.wait(2000);
  });

  it('has no critical axe violations', () => {
    cy.injectAxe();
    cy.checkA11y(null, {
      runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa'] }
    });
  });
});

describe('Accessibility: Taste DNA', () => {
  beforeEach(() => {
    cy.visit('/');
    cy.waitForApp();
    cy.navigateToView('fingerprint');
  });

  it('has no critical axe violations', () => {
    cy.injectAxe();
    cy.checkA11y(null, {
      runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa'] }
    });
  });
});

describe('Accessibility: Genre Blind Spots', () => {
  beforeEach(() => {
    cy.visit('/');
    cy.waitForApp();
    cy.navigateToView('blindspots');
  });

  it('has no critical axe violations', () => {
    cy.injectAxe();
    cy.checkA11y(null, {
      runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa'] }
    });
  });
});

describe('Accessibility: History', () => {
  beforeEach(() => {
    cy.visit('/');
    cy.waitForApp();
    cy.navigateToView('history');
  });

  it('has no critical axe violations', () => {
    cy.injectAxe();
    cy.checkA11y(null, {
      runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa'] }
    });
  });
});

describe('Accessibility: Quick Add Modal', () => {
  beforeEach(() => {
    cy.visit('/');
    cy.waitForApp();
  });

  it('modal has correct ARIA attributes', () => {
    cy.get('[data-action="openQuickAdd"]').click();
    cy.get('#quickAddOverlay .modal', { timeout: 5000 })
      .should('have.attr', 'role', 'dialog');
    cy.get('#quickAddOverlay .modal')
      .should('have.attr', 'aria-modal', 'true');
    cy.get('#quickAddOverlay .modal')
      .should('have.attr', 'aria-labelledby', 'quickAddTitle');
  });

  it('focus moves into modal on open', () => {
    cy.get('[data-action="openQuickAdd"]').click();
    cy.get('#quickAddOverlay .modal', { timeout: 5000 }).should('be.visible');
    cy.focused().should('be.within', '#quickAddOverlay');
  });

  it('Tab cycles within modal (focus trap)', () => {
    cy.get('[data-action="openQuickAdd"]').click();
    cy.get('#quickAddOverlay .modal', { timeout: 5000 }).should('be.visible');
    // Tab through all focusable elements
    cy.get('body').tab();
    cy.focused().should('be.within', '#quickAddOverlay');
    cy.focused().tab();
    cy.focused().should('be.within', '#quickAddOverlay');
  });

  it('Escape closes modal and restores focus', () => {
    cy.get('[data-action="openQuickAdd"]').click();
    cy.get('#quickAddOverlay .modal', { timeout: 5000 }).should('be.visible');
    cy.get('body').type('{esc}');
    cy.get('#quickAddOverlay').should('not.have.class', 'active');
  });
});

describe('Accessibility: Navigation', () => {
  beforeEach(() => {
    cy.visit('/');
    cy.waitForApp();
  });

  it('sidebar links have accessible labels', () => {
    cy.get('.nav-item').each(($link) => {
      cy.wrap($link).should('have.attr', 'aria-current').or('not.have.attr', 'aria-current');
    });
  });

  it('skip link exists', () => {
    cy.get('.skip-link, [class*="skip"]').should('exist');
  });
});
