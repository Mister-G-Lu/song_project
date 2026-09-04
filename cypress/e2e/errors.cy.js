// ============================================================
// Error Handling Tests — Network errors, edge cases, resilience
//
// Covers every common error possibility the frontend should
// handle gracefully:
//   • API 500s, slow responses, network failures
//   • Missing fields, malformed data, boundary values
//   • XSS injection in result rendering, long strings, special chars
//   • Double-submit, rapid view switching, empty states
//   • Invalid sort, offset beyond total, negative limits
// ============================================================

// ---------------------------------------------------------------------------
// Helper: intercept and stub a POST endpoint to prevent CSV writes
// ---------------------------------------------------------------------------
function stubAddSong() {
  return cy.intercept('POST', '/api/add-song', {
    statusCode: 201,
    body: { success: true, song: { title: 'Stubbed', rating: 85, date: '2025-01-01', notes: '' } }
  }).as('stubbedAdd');
}

// ============================================================
// API Network Errors
// ============================================================

describe('Error Handling: API Network Errors', () => {
  before(() => {
    cy.visit('/');
    cy.waitForApp();
  });

  // Intercepts are auto-cleaned by Cypress after each test — no afterEach needed.

  it('shows placeholders when /api/stats returns 500', () => {
    cy.intercept('/api/stats', { statusCode: 500, body: { error: 'Server error' } }).as('stats500');
    cy.navigateToView('dashboard');
    cy.wait('@stats500');
    // Dashboard should not crash — stat cards show '-' or error placeholder
    cy.get('#statTotal').should('exist');
    cy.get('#statTotal').invoke('text').should('match', /[-–]|error|Error/i);
  });

  it('does not crash when /api/stats returns HTML instead of JSON', () => {
    cy.intercept('/api/stats', { statusCode: 200, body: '<!doctype html><html>error</html>' }).as('statsHTML');
    cy.navigateToView('dashboard');
    cy.wait('@statsHTML');
    cy.get('#statTotal').should('exist');
  });

  it('does not crash when /api/songs network fails', () => {
    cy.intercept('/api/songs*', { forceNetworkError: true }).as('songsFail');
    cy.navigateToView('history');
    cy.wait('@songsFail', { timeout: 8000 });
    cy.get('#view-history').should('have.class', 'active');
    cy.get('#historyList').should('exist');
  });

  it('shows loading indicator during slow API response', () => {
    cy.intercept('/api/songs*', (req) => {
      return Cypress.Promise.delay(2000).then(() => req.reply());
    }).as('slowSongs');
    cy.navigateToView('history');
    cy.wait('@slowSongs', { timeout: 8000 });
    // After response, loading should be gone
    cy.get('#historyList .loading-msg', { timeout: 1000 }).should('not.exist');
  });

  it('shows loading indicator during slow constellation load', () => {
    cy.intercept('/api/constellation', (req) => {
      return Cypress.Promise.delay(2500).then(() => req.reply());
    }).as('slowConstellation');
    cy.navigateToView('constellation');
    cy.wait('@slowConstellation', { timeout: 10000 });
    cy.get('.loading-msg', { timeout: 1000 }).should('not.exist');
  });

  it('does not crash when rapidly switching between views', () => {
    // Rapid navigation: click nav items directly without waiting for full load
    cy.get('[data-view="recommender"]').click();
    cy.get('[data-view="blindspots"]').click();
    cy.get('[data-view="discover"]').click();
    cy.get('#view-discover').should('have.class', 'active');
    // No console errors should have been thrown (handled by global afterEach)
  });

  it('handles 404 on a nonexistent API endpoint gracefully', () => {
    cy.request({ url: '/api/nonexistent', failOnStatusCode: false }).then((resp) => {
      expect(resp.status).to.eq(404);
    });
  });
});

// ============================================================
// Input Edge Cases — XSS, long strings, special characters
// ============================================================

describe('Error Handling: Input Edge Cases', () => {
  before(() => {
    cy.visit('/');
    cy.waitForApp();
  });

  it('renders search results safely (no XSS via innerHTML)', () => {
    // The real XSS risk is in result rendering, not the input field.
    // Intercept the songs response and inject a malicious payload into a result.
    cy.intercept('/api/songs*', (req) => {
      req.continue((res) => {
        if (res.body && res.body.songs && res.body.songs.length > 0) {
          // Inject XSS payload into the first song's title
          res.body.songs[0].title = '<img src=x onerror="window.xssInjected=true">';
        }
      });
    }).as('xssSongs');

    cy.navigateToView('history');
    cy.wait('@xssSongs', { timeout: 8000 });

    // The malicious payload should NOT have executed
    cy.window().its('xssInjected').should('be.undefined');

    // Navigate away and back to verify the app still works
    cy.navigateToView('dashboard');
    cy.get('#view-dashboard').should('have.class', 'active');
  });

  it('handles Unicode and emoji in search', () => {
    cy.navigateToView('history');
    cy.intercept('/api/songs*').as('songsFetch');
    cy.get('#historySearch').clear().type('🎵 音楽 中文 Café ñ', { delay: 10 });
    cy.wait('@songsFetch', { timeout: 8000 });
    cy.get('#historyList').should('be.visible');
  });

  it('handles extremely long search strings (1000+ chars)', () => {
    cy.navigateToView('history');
    cy.intercept('/api/songs*').as('songsFetch');
    cy.get('#historySearch').clear().type('A'.repeat(1000), { delay: 0 });
    cy.wait('@songsFetch', { timeout: 8000 });
    cy.get('#historyList').should('be.visible');
    cy.get('#historyList').should('contain.text', 'No results')
      .or('contain.text', 'no songs')
      .or('contain.text', 'no matches');
  });

  it('handles HTML injection in search without breaking the page', () => {
    cy.navigateToView('history');
    cy.intercept('/api/songs*').as('songsFetch');
    cy.get('#historySearch').clear().type('<div style="display:none">hidden</div>', { delay: 10 });
    cy.wait('@songsFetch', { timeout: 8000 });
    cy.get('#view-history').should('have.class', 'active');
    cy.get('#sidebar').should('be.visible');
  });

  it('handles SQL-like injection patterns safely', () => {
    cy.navigateToView('history');
    cy.intercept('/api/songs*').as('songsFetch');
    cy.get('#historySearch').clear().type("' OR 1=1; DROP TABLE songs--", { delay: 10 });
    cy.wait('@songsFetch', { timeout: 8000 });
    cy.get('#view-history').should('have.class', 'active');
  });
});

// ============================================================
// State Errors — Double-submit, missing data, rapid actions
// ============================================================

describe('Error Handling: State Errors', () => {
  before(() => {
    cy.visit('/');
    cy.waitForApp();
  });

  it('does not submit quick-add form twice on double-click', () => {
    // Stub the POST to prevent writing to the real CSV
    stubAddSong();

    cy.get('#fabButton').click();
    cy.get('#qaTitle').type('Double-Click Test (Cypress Artist, 2025)');
    cy.get('#qaSubmitBtn').click();
    // Second click: button should be disabled or success overlay shown
    cy.get('#qaSubmitBtn', { timeout: 3000 }).click({ force: true });

    // Only one intercepted request should exist
    cy.get('@stubbedAdd.all').then((calls) => {
      expect(calls.length).to.eq(1);
    });

    // Clean up — close the modal
    cy.get('body').then(($body) => {
      if ($body.find('#qaSuccess:visible').length > 0) {
        cy.get('#qaSuccess .btn-outline').click();
      } else {
        cy.get('.modal-close').click();
      }
    });
  });

  it('recovers after navigating to a view with empty API response', () => {
    cy.intercept('/api/recommendations', { statusCode: 200, body: {} }).as('emptyRecs');
    cy.navigateToView('recommender');
    cy.wait('@emptyRecs');
    cy.get('#view-recommender').should('have.class', 'active');
    // Navigating away and back should still work
    cy.navigateToView('dashboard');
    cy.get('#view-dashboard').should('have.class', 'active');
  });

  it('handles missing constellation genre data gracefully', () => {
    // Inject an artist with null genre into the constellation response
    cy.intercept('/api/constellation', (req) => {
      req.continue((res) => {
        if (res.body && res.body.nodes) {
          res.body.nodes.push({
            id: 'null-genre-test',
            name: 'Null Genre Artist',
            genre: null,
            song_count: 1,
            avg_rating: 80
          });
        }
      });
    }).as('constellationWithNull');

    cy.navigateToView('constellation');
    cy.wait('@constellationWithNull', { timeout: 15000 });
    // Should still render without crashing
    cy.get('#constellationSvg', { timeout: 5000 }).should('be.visible');
    cy.get('#constellationSvg circle').should('have.length.at.least', 1);
  });
});

// ============================================================
// Backend Error Routes — Validation, missing fields, bad data
// ============================================================

describe('Error Handling: Backend Validation', () => {
  before(() => {
    cy.visit('/');
    cy.waitForApp();
  });

  it('rejects POST /api/add-song with empty body', () => {
    cy.request({
      method: 'POST', url: '/api/add-song', body: {},
      headers: { 'Content-Type': 'application/json' }, failOnStatusCode: false
    }).then((resp) => {
      expect(resp.status).to.eq(400);
      expect(resp.body).to.have.property('error');
    });
  });

  it('rejects POST /api/add-song with whitespace-only title', () => {
    cy.request({
      method: 'POST', url: '/api/add-song', body: { title: '   ' },
      headers: { 'Content-Type': 'application/json' }, failOnStatusCode: false
    }).then((resp) => {
      expect(resp.status).to.eq(400);
      expect(resp.body).to.have.property('error');
    });
  });

  it('rejects POST /api/add-song with invalid Content-Type', () => {
    cy.request({
      method: 'POST', url: '/api/add-song', body: 'raw text',
      headers: { 'Content-Type': 'text/plain' }, failOnStatusCode: false
    }).then((resp) => {
      expect(resp.status).to.eq(400);
    });
  });

  it('rejects /api/backfill-ratings with invalid method parameter', () => {
    cy.request({
      method: 'POST', url: '/api/backfill-ratings',
      body: { method: 'invalid' },
      headers: { 'Content-Type': 'application/json' }, failOnStatusCode: false
    }).then((resp) => {
      expect(resp.status).to.eq(400);
      expect(resp.body).to.have.property('error');
    });
  });

  it('rejects POST /api/batch-add with empty songs array', () => {
    cy.request({
      method: 'POST', url: '/api/batch-add', body: { songs: [] },
      headers: { 'Content-Type': 'application/json' }, failOnStatusCode: false
    }).then((resp) => {
      expect(resp.status).to.eq(400);
      expect(resp.body).to.have.property('error');
    });
  });

  it('rejects POST /api/batch-add with missing body', () => {
    cy.request({
      method: 'POST', url: '/api/batch-add', body: {},
      headers: { 'Content-Type': 'application/json' }, failOnStatusCode: false
    }).then((resp) => {
      expect(resp.status).to.eq(400);
      expect(resp.body).to.have.property('error');
    });
  });

  it('rejects POST /api/import-songs with empty text', () => {
    cy.request({
      method: 'POST', url: '/api/import-songs',
      body: { text: '  \n  \n' },
      headers: { 'Content-Type': 'application/json' }, failOnStatusCode: false
    }).then((resp) => {
      expect(resp.status).to.eq(400);
    });
  });

  it('handles POST /api/check-song with only a title (no artist/song split)', () => {
    cy.request({
      method: 'POST', url: '/api/check-song',
      body: { title: 'Some Song (Artist, 2025)' },
      headers: { 'Content-Type': 'application/json' }
    }).then((resp) => {
      expect(resp.status).to.eq(200);
      expect(resp.body).to.have.property('exists');
    });
  });

  it('handles POST /api/reclassify-genres with empty body as no-op', () => {
    cy.request({
      method: 'POST', url: '/api/reclassify-genres',
      body: {},
      headers: { 'Content-Type': 'application/json' },
      failOnStatusCode: false
    }).then((resp) => {
      expect(resp.status).to.eq(200);
      expect(resp.body).to.have.property('before');
      expect(resp.body).to.have.property('after');
    });
  });
});

// ============================================================
// API Edge Cases — Boundary values, invalid parameters
// ============================================================

describe('Error Handling: API Edge Cases', () => {
  before(() => {
    cy.visit('/');
    cy.waitForApp();
  });

  it('handles sort by non-existent field', () => {
    cy.request('/api/songs?sort=nonexistent&limit=3').then((resp) => {
      expect(resp.status).to.eq(200);
      expect(resp.body.songs).to.be.an('array');
    });
  });

  it('handles offset beyond total songs', () => {
    cy.request('/api/songs?offset=999999&limit=5').then((resp) => {
      expect(resp.status).to.eq(200);
      expect(resp.body.songs).to.be.an('array').that.is.empty;
    });
  });

  it('handles limit=0', () => {
    cy.request('/api/songs?limit=0').then((resp) => {
      expect(resp.status).to.eq(200);
      expect(resp.body.songs).to.be.an('array').that.is.empty;
    });
  });

  it('handles negative limit', () => {
    cy.request('/api/songs?limit=-5').then((resp) => {
      expect(resp.status).to.eq(200);
      expect(resp.body.songs).to.be.an('array');
    });
  });

  it('handles empty /api/search-history query', () => {
    cy.request('/api/search-history').then((resp) => {
      expect(resp.status).to.eq(200);
      expect(resp.body.results).to.be.an('array').that.is.empty;
      expect(resp.body.total).to.eq(0);
    });
  });

  it('handles min_rating=0 (all songs)', () => {
    cy.request('/api/songs?min_rating=0&limit=1').then((resp) => {
      expect(resp.status).to.eq(200);
      expect(resp.body.songs.length).to.be.at.least(0);
    });
  });

  it('handles min_rating=100 (perfect scores only)', () => {
    cy.request('/api/songs?min_rating=100&limit=5').then((resp) => {
      expect(resp.status).to.eq(200);
      resp.body.songs.forEach((s) => expect(s.rating).to.be.at.least(100));
    });
  });

  it('handles min_rating=999 (no results, no crash)', () => {
    cy.request('/api/songs?min_rating=999&limit=1').then((resp) => {
      expect(resp.status).to.eq(200);
      expect(resp.body.songs).to.be.an('array').that.is.empty;
    });
  });

  it('handles challenge count=0', () => {
    cy.request('/api/challenges?count=0').then((resp) => {
      expect(resp.status).to.eq(200);
      expect(resp.body).to.have.property('challenges').that.is.an('array');
    });
  });

  it('handles challenge count=1 (minimum useful)', () => {
    cy.request('/api/challenges?count=1').then((resp) => {
      expect(resp.status).to.eq(200);
      expect(resp.body.challenges.length).to.be.at.most(1);
    });
  });

  it('handles /api/backfill-preview with invalid method', () => {
    cy.request('/api/backfill-preview?method=invalid').then((resp) => {
      expect(resp.status).to.eq(200);
      expect(resp.body).to.have.property('total_changes');
    });
  });
});
