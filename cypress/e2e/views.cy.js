// ============================================================
// View Render Tests — Recommender, Blind Spots, Challenge, Weekly
// ============================================================

describe('Specialized Views Render Correctly', () => {
  before(() => {
    cy.visit('/');
    cy.waitForApp();
  });

  describe('Recommender View', () => {
    it('loads and displays recommendations', () => {
      cy.navigateToView('recommender');
      cy.get('#view-recommender').should('have.class', 'active');
      cy.get('#recommendationsContainer', { timeout: 15000 }).should('be.visible');
      cy.get('#recommendationsContainer').should('not.contain.text', 'Generating');
    });

    it('shows recommendation cards with scores', () => {
      cy.get('.rec-card, .recommendation-card', { timeout: 10000 }).should('have.length.at.least', 1);
      cy.get('.rec-card, .recommendation-card').first().should('contain.text', '/100')
        .or('contain.text', '%');
    });

    it('shows the Spotify connection banner', () => {
      cy.get('#spotifyBanner').should('be.visible');
    });
  });

  describe('Blind Spots View', () => {
    it('loads and displays blind spots', () => {
      cy.navigateToView('blindspots');
      cy.get('#view-blindspots').should('have.class', 'active');
      cy.get('#blindspotsGrid', { timeout: 15000 }).should('be.visible');
      cy.get('#blindspotsGrid').should('not.contain.text', 'Mapping');
    });

    it('shows top loved genres as pills', () => {
      cy.get('#topGenrePills', { timeout: 10000 }).should('be.visible');
    });

    it('shows blind spot items', () => {
      cy.get('.blindspot-card, .blind-spot-item', { timeout: 10000 }).should('have.length.at.least', 1);
    });
  });

  describe('Challenge View', () => {
    it('loads and displays challenges', () => {
      cy.navigateToView('challenge');
      cy.get('#view-challenge').should('have.class', 'active');
      cy.get('#challengeContent', { timeout: 15000 }).should('be.visible');
      cy.get('#challengeContent').should('not.contain.text', 'Loading');
    });

    it('shows challenge cards by tier', () => {
      cy.get('.challenge-card, .challenge-item', { timeout: 10000 }).should('have.length.at.least', 1);
    });

    it('shows tier headings (Easy/Medium/Hard)', () => {
      cy.get('#challengeContent').should('contain.text', 'Easy')
        .or('contain.text', 'Medium')
        .or('contain.text', 'Hard')
        .or('contain.text', 'Expert');
    });

    it('shows your listening zones', () => {
      cy.get('#challengeContent').should('contain.text', 'your')
        .or('contain.text', 'zone')
        .or('contain.text', 'Zone');
    });
  });

  describe('Weekly Discovery View', () => {
    it('loads and displays weekly picks', () => {
      cy.navigateToView('weekly');
      cy.get('#view-weekly').should('have.class', 'active');
      cy.get('#weeklyPicks', { timeout: 15000 }).should('be.visible');
      cy.get('#weeklyPicks').should('not.contain.text', 'Curating');
    });

    it('shows weekly stats in the banner', () => {
      cy.get('#weeklyStats', { timeout: 10000 }).should('be.visible');
    });

    it('shows at least one weekly pick', () => {
      cy.get('.weekly-pick, .pick-card', { timeout: 10000 }).should('have.length.at.least', 1);
    });

    it('shows the refresh and export buttons', () => {
      cy.get('.weekly-actions .btn-primary').should('contain.text', 'Refresh');
      cy.get('.weekly-actions .btn-outline').should('contain.text', 'Copy');
    });
  });

  describe('Constellation View', () => {
    it('loads and shows the SVG canvas', () => {
      cy.navigateToView('constellation');
      cy.get('#view-constellation').should('have.class', 'active');
      cy.get('#constellationSvg', { timeout: 15000 }).should('be.visible');
    });

    it('renders SVG circles (artist nodes)', () => {
      cy.get('#constellationSvg circle', { timeout: 10000 }).should('have.length.at.least', 1);
    });

    it('shows the mode toggle buttons', () => {
      cy.get('.mode-btn').should('have.length.at.least', 2);
      cy.get('.mode-btn[data-mode="unsorted"]').should('be.visible');
      cy.get('.mode-btn[data-mode="genre"]').should('be.visible');
    });

    it('switches to genre mode', () => {
      cy.get('.mode-btn[data-mode="genre"]').click();
      cy.get('.mode-btn[data-mode="genre"]').should('have.class', 'active');
      cy.get('.mode-btn[data-mode="unsorted"]').should('not.have.class', 'active');
    });

    it('switches back to unsorted mode', () => {
      cy.get('.mode-btn[data-mode="unsorted"]').click();
      cy.get('.mode-btn[data-mode="unsorted"]').should('have.class', 'active');
    });
  });

  describe('Evolution View', () => {
    it('loads and displays evolution data', () => {
      cy.navigateToView('evolution');
      cy.get('#view-evolution').should('have.class', 'active');
      cy.get('#evolutionSummary', { timeout: 15000 }).should('be.visible');
    });

    it('renders the evolution chart (canvas)', () => {
      cy.get('#evolutionChart', { timeout: 10000 }).should('be.visible');
    });

    it('shows the yearly table', () => {
      cy.get('#yearlyTable', { timeout: 10000 }).should('be.visible');
      cy.get('#yearlyTable').should('not.contain.text', 'Loading');
    });

    it('shows the genre evolution chart', () => {
      cy.get('#genreEvolutionChart', { timeout: 10000 }).should('be.visible');
    });

    it('has a genre selector dropdown', () => {
      cy.get('#genreSelect').should('be.visible');
      cy.get('#genreSelect option').should('have.length.at.least', 2);
    });

    it('shows the cumulative chart', () => {
      cy.get('#cumulativeChart', { timeout: 10000 }).should('be.visible');
    });
  });
});
