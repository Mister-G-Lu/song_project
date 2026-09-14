// ============================================================
// Dashboard Tests — Stats grid, charts, top artists, reviews
// ============================================================

describe('Dashboard: Stats and Charts', () => {
  beforeEach(() => {
    // Visit fresh each test: Cypress 12+ testIsolation clears the DOM between
    // tests, so a visit in `before` only applied to the first test.
    cy.visit('/');
    cy.waitForApp();
  });

  it('renders all 8 stat cards with values', () => {
    const statIds = ['statTotal', 'statRated', 'statAvg', 'statMedian', 'statArtists', 'statPeriod', 'statPerfect'];
    statIds.forEach((id) => {
      cy.get(`#${id}`, { timeout: 10000 }).should('be.visible');
      cy.get(`#${id}`).invoke('text').should('match', /[\d\-–]/);
    });
  });

  it('shows total entries as a positive number', () => {
    cy.get('#statTotal').invoke('text').then(parseFloat).should('be.gt', 0);
  });

  it('shows rated songs as a positive number', () => {
    cy.get('#statRated').invoke('text').then(parseFloat).should('be.gt', 0);
  });

  it('shows average rating between 0 and 100', () => {
    cy.get('#statAvg').invoke('text').then((t) => {
      if (t !== '-') {
        const val = parseFloat(t);
        expect(val).to.be.within(0, 100);
      }
    });
  });

  it('shows unique artists as a positive number', () => {
    cy.get('#statArtists').invoke('text').then(parseFloat).should('be.gt', 0);
  });

  it('shows the time span in years', () => {
    cy.get('#statPeriod').invoke('text').should('match', /\d+\s*years?/);
  });

  it('renders the rating distribution chart (canvas)', () => {
    cy.get('#ratingChart').should('exist');
    cy.get('#ratingChart').should('be.visible');
  });

  it('renders the genre breakdown chart (canvas)', () => {
    cy.get('#genreChart').should('exist');
    cy.get('#genreChart').should('be.visible');
  });

  it('keeps every genre color paired with a readable legend label and count', () => {
    cy.get('#genreChart').should('be.visible');
    cy.get('#genreLegend .genre-legend-item', { timeout: 10000 })
      .should('have.length.at.least', 2)
      .then(($items) => {
        const chart = Cypress.$('#genreChart')[0];
        cy.window().then((win) => {
          const instance = Object.values(win.Chart.instances)
            .find((candidate) => candidate.canvas === chart);
          expect(instance, 'Genre Breakdown Chart.js instance').to.exist;
          const labels = instance.data.labels;
          const values = instance.data.datasets[0].data;
          expect($items.length, 'legend item count').to.equal(labels.length);

          [...$items].forEach((item, index) => {
            const $item = Cypress.$(item);
            const label = $item.find('.genre-legend-label').text().trim();
            const count = $item.find('.genre-legend-count').text().trim();
            const swatch = $item.find('.genre-legend-swatch')[0];
            expect(label, `legend label ${index}`).to.equal(labels[index]);
            expect(count, `legend count ${index}`).to.equal(Number(values[index]).toLocaleString());
            expect($item.attr('data-genre'), `genre data attribute ${index}`).to.equal(labels[index]);
            expect($item.attr('data-genre-key'), `source key ${index}`).to.be.a('string').and.not.be.empty;
            const expectedColor = instance.data.datasets[0].backgroundColor[index];
            expect($item.attr('style').replace(/\s/g, ''), `legend color ${index}`).to.contain(`--genre-color:${expectedColor}`);
            expect(win.getComputedStyle(swatch).backgroundColor, `swatch color ${index}`).to.not.equal('rgba(0, 0, 0, 0)');
          });
        });
      });
  });

  it('contains the dashboard horizontally at desktop and mobile widths', () => {
    const assertContained = () => {
      cy.document().then((doc) => {
        expect(doc.documentElement.scrollWidth, 'document width').to.be.at.most(doc.documentElement.clientWidth + 1);
        expect(doc.body.scrollWidth, 'body width').to.be.at.most(doc.body.clientWidth + 1);
        expect(doc.querySelector('#mainContent').scrollWidth, 'main content width')
          .to.be.at.most(doc.querySelector('#mainContent').clientWidth + 1);
      });
    };

    assertContained();
    cy.viewport(500, 800);
    cy.wait(100);
    assertContained();
    cy.get('#genreLegend').should('be.visible');
    cy.get('#genreLegend .genre-legend-item').should('have.length.at.least', 2);
  });

  it('renders the top artists table', () => {
    // The Top Artists section is a collapsible panel that starts collapsed
    // (chevron ▶). Click the chevron open so the table is visible.
    cy.get('#topArtistsTable').closest('.chart-card').find('.collapsible-header').click({ timeout: 5000 });
    cy.get('#topArtistsTable', { timeout: 10000 }).should('be.visible');
    cy.get('#topArtistsTable').should('not.contain.text', 'Loading');
    cy.get('#topArtistsTable table.data-table').should('exist');
    cy.get('#topArtistsTable tbody tr').should('have.length.at.least', 1);
  });

  it('displays at least 5 top artists', () => {
    cy.get('#topArtistsTable').closest('.chart-card').find('.collapsible-header').click({ timeout: 5000 });
    cy.get('#topArtistsTable tbody tr').should('have.length.at.least', 5);
  });

  it('shows rank numbers with top-3 highlighting', () => {
    cy.get('#topArtistsTable').closest('.chart-card').find('.collapsible-header').click({ timeout: 5000 });
    cy.get('#topArtistsTable .artist-rank.top3').should('have.length', 3);
  });

  it('renders recent reviews', () => {
    cy.get('#recentReviews', { timeout: 10000 }).should('be.visible');
    cy.get('#recentReviews').should('not.contain.text', 'Loading');
    cy.get('#recentReviews .review-item').should('have.length.at.least', 1);
  });

  it('shows rating badges in recent reviews', () => {
    cy.get('#recentReviews .rating-badge').should('have.length.at.least', 1);
  });

  it('shows the backfill preview panel', () => {
    cy.get('.backfill-panel').should('be.visible');
    cy.get('#backfillPreviewStats', { timeout: 10000 }).should('be.visible');
    cy.get('#backfillPreviewStats').should('not.contain.text', 'Analyzing');
  });

  it('shows backfill action buttons', () => {
    cy.get('#backfillBtn').should('be.visible');
    cy.get('.backfill-actions .btn-outline').should('be.visible');
  });
});
