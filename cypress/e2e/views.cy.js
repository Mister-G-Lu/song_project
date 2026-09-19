// ============================================================
// View Render Tests — Recommender, Blind Spots, Discover (live + challenges)
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

  describe('Discover › Out of your zone (challenges)', () => {
    it('loads and displays challenges in the second Discover tab', () => {
      cy.navigateToView('discover');
      cy.get('#discoverTabs .discover-tab[data-tab="challenge"]').click();
      cy.get('#discoverChallenge').should('be.visible');
      cy.get('#discoverLive').should('not.be.visible');
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

    // --- Obscure Gems Slider ---

    it('switches to Obscure Gems mode and shows the slider', () => {
      cy.navigateToView('discover');
      cy.get('#discoverTabs .discover-tab[data-tab="challenge"]').click();
      cy.get('#challengeContent', { timeout: 15000 }).should('be.visible');
      cy.get('[data-mode="obscure"]').click();
      cy.get('#obscureThreshold', { timeout: 10000 }).should('be.visible');
      cy.get('#thresholdValue').should('be.visible');
    });

    it('slider has correct min/max/step attributes', () => {
      cy.get('#obscureThreshold').should('have.attr', 'min', '30');
      cy.get('#obscureThreshold').should('have.attr', 'max', '100');
      cy.get('#obscureThreshold').should('have.attr', 'step', '5');
    });

    it('slider updates threshold display when moved', () => {
      cy.get('#obscureThreshold').should('be.visible');
      // Set slider to 50 via Cypress
      cy.get('#obscureThreshold').invoke('val', 50).trigger('input');
      cy.get('#thresholdValue').should('contain.text', '50');
    });

    it('slider re-fetches challenges after debounce', () => {
      cy.intercept('GET', '/api/challenges*').as('challengesReq');
      cy.get('#obscureThreshold').should('be.visible');
      cy.get('#obscureThreshold').invoke('val', 40).trigger('input');
      // Wait for debounced reload (300ms debounce + network)
      cy.wait('@challengesReq', { timeout: 5000 });
    });

    it('slider value persists across mode switches', () => {
      // Set to obscure, change slider
      cy.get('[data-mode="obscure"]').click();
      cy.get('#obscureThreshold', { timeout: 10000 }).should('be.visible');
      cy.get('#obscureThreshold').invoke('val', 45).trigger('input');
      cy.get('#thresholdValue').should('contain.text', '45');
      // Switch away and back
      cy.get('[data-mode="outside_zone"]').click();
      cy.get('#obscureThreshold').should('not.exist');
      cy.get('[data-mode="obscure"]').click();
      cy.get('#obscureThreshold', { timeout: 10000 }).should('be.visible');
      cy.get('#obscureThreshold').should('have.value', '45');
    });
  });

  describe('Discover › Near you (live)', () => {
    it('loads and shows the mode dial, seed box and grid', () => {
      cy.navigateToView('discover');
      cy.get('#view-discover').should('have.class', 'active');
      cy.get('#discoverTabs .discover-tab').should('have.length', 2);
      cy.get('#discoverTabs .discover-tab[data-tab="live"]').click();
      cy.get('#discoverLive').should('be.visible');
      cy.get('#discoverModes .mode-btn').should('have.length', 3);
      cy.get('#discoverModes .mode-btn[data-mode="easy"]').should('have.class', 'active');
      cy.get('#discoverSeedInput').should('be.visible');
      cy.get('#discoverGrid', { timeout: 20000 }).should('be.visible')
        .and('not.contain.text', 'Finding fresh picks');
    });

    it('renders picks or a graceful offline message', () => {
      cy.get('#discoverGrid .discover-card, #discoverGrid .discover-empty', { timeout: 20000 })
        .should('have.length.at.least', 1);
    });

    it('switching mode updates the active button and hint', () => {
      cy.get('#discoverModes .mode-btn[data-mode="hard"]').click();
      cy.get('#discoverModes .mode-btn[data-mode="hard"]').should('have.class', 'active');
      cy.get('#discoverModes .mode-btn[data-mode="easy"]').should('not.have.class', 'active');
      cy.get('#discoverModeHint').should('contain.text', 'Far neighbours');
      cy.get('#discoverGrid .discover-card, #discoverGrid .discover-empty', { timeout: 20000 })
        .should('have.length.at.least', 1);
    });

    it('fresh releases panel is collapsed by default and expands', () => {
      cy.get('#freshPanel').should('have.class', 'collapsed');
      cy.get('#freshPanel .collapsible-header').click();
      cy.get('#freshPanel').should('not.have.class', 'collapsed');
      cy.get('#freshReleases', { timeout: 20000 }).should('be.visible');
    });

    it('legacy switchView("challenge") lands on the Out-of-zone tab', () => {
      cy.window().then((win) => win.switchView('challenge'));
      cy.get('#view-discover').should('have.class', 'active');
      cy.get('#discoverTabs .discover-tab[data-tab="challenge"]').should('have.class', 'active');
      cy.get('#discoverChallenge').should('be.visible');
    });
  });

  describe('Constellation View', () => {
    it('loads and shows the SVG canvas', () => {
      cy.navigateToView('constellation');
      cy.get('#view-constellation').should('have.class', 'active');
      cy.get('#constellationSvg', { timeout: 15000 }).should('be.visible');
    });

    it('renders SVG circles (artist nodes)', () => {
      cy.get('#constellationSvg circle', { timeout: 10000 }).should('have.length.at.least', 10);
    });

    it('shows the legend', () => {
      cy.get('#constellationLegend').should('be.visible');
      cy.get('#constellationLegend').should('not.be.empty');
    });

    it('shows 2 mode toggle buttons', () => {
      cy.get('#view-constellation .mode-btn').should('have.length', 2);
      cy.get('.mode-btn[data-mode="genre"]').should('be.visible').and('contain.text', 'Genre & Taste');
      cy.get('.mode-btn[data-mode="connections"]').should('be.visible').and('contain.text', 'Artist Connections');
    });

    it('Genre & Taste is the default active mode', () => {
      cy.get('.mode-btn[data-mode="genre"]').should('have.class', 'active');
      cy.get('.mode-btn[data-mode="connections"]').should('not.have.class', 'active');
    });

    it('shows mode description for genre clusters', () => {
      cy.get('#constellationModeDesc', { timeout: 10000 }).should('contain.text', 'favorites');
      cy.get('#constellationModeDesc').should('contain.text', 'genre');
    });

    it('shows rating labels on nodes', () => {
      cy.get('#constellationSvg g.node text', { timeout: 10000 }).should('have.length.at.least', 1);
    });

    it('legend shows sentiment tiers', () => {
      cy.get('#constellationLegend', { timeout: 15000 }).should('contain.text', 'Loved');
      cy.get('#constellationLegend', { timeout: 15000 }).should('contain.text', 'Disliked');
    });

    it('switches to Artist Connections mode and re-renders', () => {
      cy.get('.mode-btn[data-mode="connections"]').click();
      cy.get('.mode-btn[data-mode="connections"]').should('have.class', 'active');
      cy.get('.mode-btn[data-mode="genre"]').should('not.have.class', 'active');
      cy.get('#constellationModeDesc', { timeout: 10000 }).should('contain.text', 'collaborations');
      cy.get('#constellationSvg circle', { timeout: 15000 }).should('have.length.at.least', 10);
    });

    it('Artist Connections legend shows community clusters', () => {
      cy.get('#constellationLegend', { timeout: 15000 }).should('not.be.empty');
    });

    it('switches back to Genre & Taste without errors', () => {
      cy.get('.mode-btn[data-mode="genre"]').click();
      cy.get('.mode-btn[data-mode="genre"]').should('have.class', 'active');
      cy.get('#constellationSvg circle', { timeout: 15000 }).should('have.length.at.least', 10);
    });

    it('cycles through both modes consecutively', () => {
      cy.get('.mode-btn[data-mode="connections"]').click();
      cy.get('.mode-btn[data-mode="connections"]').should('have.class', 'active');
      cy.get('#constellationSvg circle', { timeout: 15000 }).should('have.length.at.least', 10);

      cy.get('.mode-btn[data-mode="genre"]').click();
      cy.get('.mode-btn[data-mode="genre"]').should('have.class', 'active');
      cy.get('#constellationSvg circle', { timeout: 15000 }).should('have.length.at.least', 10);
    });

    // Regression guard: within each genre cluster, higher-rated artists must
    // sit ABOVE lower-rated ones ("favorites float to top, disliked sink")
    // in the Genre & Taste mode.
    it('Genre & Taste floats higher-rated artists above lower-rated ones', () => {
      cy.get('#constellationSvg circle', { timeout: 15000 }).should('have.length.at.least', 10);
      cy.window().then((win) => {
        const nodes = win.d3.select('#constellationSvg').selectAll('g.node').data();
        expect(nodes.length, 'nodes rendered').to.be.at.least(10);
        const byGenre = {};
        nodes.forEach((n) => {
          const g = n.genre || 'Uncategorized';
          (byGenre[g] = byGenre[g] || []).push(n);
        });
        const mean = (a) => a.reduce((s, v) => s + v, 0) / a.length;
        let checked = 0;
        for (const [g, arr] of Object.entries(byGenre)) {
          const hi = arr.filter((n) => n.avg_rating >= 80).map((n) => n.y);
          const lo = arr.filter((n) => n.avg_rating < 70).map((n) => n.y);
          if (hi.length >= 3 && lo.length >= 2) {
            checked += 1;
            expect(mean(hi), `high-rated y in ${g}`).to.be.lessThan(mean(lo));
          }
        }
        expect(checked, 'genres with both tiers').to.be.at.least(2);
      });
    });

    // Regression guard: the Followers chart must keep the same intent —
    // within a genre row, higher-rated points sit above lower-rated ones.
    it('Followers chart sorts rating vertically within genre rows', () => {
      cy.get('.mode-btn[data-mode="followers"]').click();
      cy.get('#constellationSvg circle', { timeout: 15000 }).should('have.length.at.least', 10);
      cy.window().then((win) => {
        const nodes = win.d3.select('#constellationSvg').selectAll('g.node').data();
        const byGenre = {};
        nodes.forEach((n) => {
          const g = n.genre || 'Uncategorized';
          (byGenre[g] = byGenre[g] || []).push(n);
        });
        const mean = (a) => a.reduce((s, v) => s + v, 0) / a.length;
        let checked = 0;
        for (const [g, arr] of Object.entries(byGenre)) {
          const hi = arr.filter((n) => n.avg_rating >= 80).map((n) => n.y);
          const lo = arr.filter((n) => n.avg_rating < 70).map((n) => n.y);
          if (hi.length >= 3 && lo.length >= 2) {
            checked += 1;
            expect(mean(hi), `high-rated y in ${g}`).to.be.lessThan(mean(lo));
          }
        }
        expect(checked, 'genres with both tiers').to.be.at.least(2);
      });
    });

    it('shows 3 mode toggle buttons', () => {
      cy.get('#view-constellation .mode-btn').should('have.length', 3);
      cy.get('.mode-btn[data-mode="followers"]').should('be.visible').and('contain.text', 'Followers');
    });

    it('switches to Followers mode and renders the scatter chart', () => {
      cy.get('.mode-btn[data-mode="followers"]').click();
      cy.get('.mode-btn[data-mode="followers"]').should('have.class', 'active');
      cy.get('.mode-btn[data-mode="genre"]').should('not.have.class', 'active');
      cy.get('#constellationModeDesc', { timeout: 10000 }).should('not.be.visible');
      cy.get('#constellationFollowersDesc', { timeout: 10000 }).should('be.visible')
        .and('contain.text', 'follower');
      cy.get('#constellationSvg circle', { timeout: 15000 }).should('have.length.at.least', 10);
    });

    it('Followers chart shows a labeled log-scale X axis', () => {
      cy.get('#constellationSvg .pop-axis', { timeout: 10000 }).should('exist');
      cy.get('#constellationSvg .pop-axis .tick', { timeout: 10000 }).should('have.length.at.least', 4);
      cy.get('#constellationSvg .pop-axis-title', { timeout: 10000 })
        .should('contain.text', 'Follower count');
    });

    it('Followers chart shows genre row labels', () => {
      cy.get('#constellationSvg text', { timeout: 10000 })
        .filter((i, el) => /^(Rock|Pop|Metal)/.test(el.textContent))
        .should('have.length.at.least', 1);
    });

    it('Followers legend shows the axis hint', () => {
      cy.get('#constellationLegend', { timeout: 15000 }).should('contain.text', 'follower');
    });

    it('switches back from Followers without errors', () => {
      cy.get('.mode-btn[data-mode="genre"]').click();
      cy.get('.mode-btn[data-mode="genre"]').should('have.class', 'active');
      cy.get('#constellationModeDesc', { timeout: 10000 }).should('be.visible');
      cy.get('#constellationFollowersDesc').should('not.be.visible');
      cy.get('#constellationSvg circle', { timeout: 15000 }).should('have.length.at.least', 10);
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
