// ============================================================
// Visual Regression Tests — Screenshot every view and key UI states
//
// First run:  npx cypress run --spec cypress/e2e/visual-regression.cy.js --env updateSnapshots=true
// Compare:    npx cypress run --spec cypress/e2e/visual-regression.cy.js
// Update one: npx cypress run --spec cypress/e2e/visual-regression.cy.js --env updateSnapshots=true
// ============================================================

describe('Visual Regression: Dashboard', () => {
  beforeEach(() => {
    cy.visit('/');
    cy.waitForApp();
  });

  it('dashboard — full page', () => {
    cy.matchImageSnapshot('dashboard-full');
  });

  it('dashboard — genre breakdown 90+ filter', () => {
    cy.get('#genreFilterToggle [data-filter="liked90"]').click();
    cy.wait(500); // let chart re-render
    cy.get('#genreChart').should('be.visible');
    cy.matchImageSnapshot('dashboard-genre-90plus');
  });

  it('dashboard — stat cards', () => {
    cy.get('.stat-card').first().should('be.visible');
    cy.get('.stat-card').first().matchImageSnapshot('dashboard-stat-cards');
  });
});

describe('Visual Regression: Evolution', () => {
  beforeEach(() => {
    cy.visit('/');
    cy.waitForApp();
    cy.navigateToView('evolution');
  });

  it('evolution — full page', () => {
    cy.matchImageSnapshot('evolution-full');
  });

  it('evolution — release year chart', () => {
    cy.get('#releaseYearChart', { timeout: 10000 }).should('be.visible');
    cy.get('#releaseYearChart').closest('.chart-card').matchImageSnapshot('evolution-release-year');
  });

  it('evolution — yearly table', () => {
    cy.get('#yearlyTable', { timeout: 10000 }).should('be.visible');
    cy.get('#yearlyTable').closest('.chart-card').matchImageSnapshot('evolution-yearly-table');
  });
});

describe('Visual Regression: Constellation', () => {
  beforeEach(() => {
    cy.visit('/');
    cy.waitForApp();
    cy.navigateToView('constellation');
  });

  it('constellation — genre mode', () => {
    cy.get('#constellationSvg', { timeout: 15000 }).should('be.visible');
    cy.matchImageSnapshot('constellation-genre');
  });

  it('constellation — followers mode', () => {
    cy.get('[data-mode="followers"]', { timeout: 10000 }).click();
    cy.wait(1000); // let D3 re-render
    cy.matchImageSnapshot('constellation-followers');
  });
});

describe('Visual Regression: Discover', () => {
  beforeEach(() => {
    cy.visit('/');
    cy.waitForApp();
    cy.get('[data-view="discover"]').click();
    cy.get('#view-discover', { timeout: 10000 }).should('have.class', 'active');
    cy.wait(3000); // let discover content load
  });

  it('discover — live tab', () => {
    cy.get('#view-discover').should('have.class', 'active');
    cy.wait(3000); // let live content load
    cy.matchImageSnapshot('discover-live');
  });

  it('discover — challenge tab', () => {
    cy.get('#discoverTabs .discover-tab[data-tab="challenge"]').click();
    cy.get('#challengeContent', { timeout: 15000 }).should('be.visible');
    cy.matchImageSnapshot('discover-challenges');
  });

  it('discover — obscure gems with slider', () => {
    cy.get('#discoverTabs .discover-tab[data-tab="challenge"]').click();
    cy.get('#challengeContent', { timeout: 15000 }).should('be.visible');
    cy.get('[data-mode="obscure"]').click();
    cy.get('#obscureThreshold', { timeout: 10000 }).should('be.visible');
    cy.matchImageSnapshot('discover-obscure-gems');
  });
});

describe('Visual Regression: Taste DNA', () => {
  beforeEach(() => {
    cy.visit('/');
    cy.waitForApp();
    cy.navigateToView('fingerprint');
  });

  it('fingerprint — full page', () => {
    cy.matchImageSnapshot('fingerprint-full');
  });
});

describe('Visual Regression: Genre Blind Spots', () => {
  beforeEach(() => {
    cy.visit('/');
    cy.waitForApp();
    cy.navigateToView('blindspots');
  });

  it('blindspots — full page', () => {
    cy.matchImageSnapshot('blindspots-full');
  });
});

describe('Visual Regression: History', () => {
  beforeEach(() => {
    cy.visit('/');
    cy.waitForApp();
    cy.navigateToView('history');
  });

  it('history — full page', () => {
    cy.matchImageSnapshot('history-full');
  });
});

describe('Visual Regression: Navigation', () => {
  beforeEach(() => {
    cy.visit('/');
    cy.waitForApp();
  });

  it('sidebar — default state', () => {
    cy.get('nav').first().matchImageSnapshot('nav-sidebar');
  });

  it('sidebar — mobile viewport', () => {
    cy.viewport(375, 812);
    cy.wait(300);
    cy.matchImageSnapshot('nav-sidebar-mobile');
  });
});

describe('Visual Regression: Quick Add Modal', () => {
  beforeEach(() => {
    cy.visit('/');
    cy.waitForApp();
  });

  it('quick-add — modal open', () => {
    cy.get('[data-action="openQuickAdd"]').click();
    cy.get('#quickAddOverlay', { timeout: 5000 }).should('be.visible');
    cy.matchImageSnapshot('quickadd-modal');
  });
});
