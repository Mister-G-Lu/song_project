// ============================================================
// Recommender Save-Button Regression — apostrophes in titles
//
// Bug: renderRecommendations() embedded song/artist into inline
// onclick via escapeHtml(). escapeHtml turns ' into &#039;, which
// the HTML parser decodes back to ' INSIDE the attribute before
// the JS engine runs — so a song like "He's a Pirate (Violin
// Cover)" produced onclick="...('He's a Pirate ...')", a silent
// SyntaxError, and clicking "+ Save" did nothing.
//
// Fix: escapeJsAttr() in utils.js escapes for the JS layer
// (apostrophe -> \') and the HTML attribute layer (& -> &amp;,
// " -> &quot;, ...), so the decoded attribute value is valid JS.
// ============================================================

describe('escapeJsAttr — deterministic round-trip (regression core)', () => {
  beforeEach(() => {
    cy.visit('/');
    cy.waitForApp();
  });

  it('produces parseable onclick handlers that evaluate back to the original text', () => {
    // Simulates exactly what the views do: embed escapeJsAttr output into
    // onclick="fn('${escaped}')", let the browser HTML-decode the attribute,
    // then compile & run the handler. Pre-fix (escapeHtml) this throws.
    const cases = [
      "He's a Pirate (Violin Cover)",
      "O'Brien & Sons",
      'A "quoted" title',
      'Back\\slash',
      'New\nline',
      'Amp &ersand <tag>',
    ];
    cy.window().then((win) => {
      cases.forEach((s) => {
        const escaped = win.escapeJsAttr(s);
        const div = win.document.createElement('div');
        div.innerHTML = `<button onclick="verifyRoundTrip('${escaped}')">x</button>`;
        const attr = div.firstElementChild.getAttribute('onclick'); // HTML-decoded
        let got = null;
        // Compile and run the handler with verifyRoundTrip bound to a capture fn.
        expect(() => new Function('verifyRoundTrip', attr), `case: ${JSON.stringify(s)}`).not.to.throw();
        new Function('verifyRoundTrip', attr)((v) => { got = v; });
        expect(got, `round-trip: ${JSON.stringify(s)}`).to.eq(s);
      });
    });
  });
});

describe('Recommender Save Button — apostrophe-safe', () => {
  beforeEach(() => {
    cy.visit('/');
    cy.waitForApp();
    cy.navigateToView('recommender');
    cy.get('.rec-card', { timeout: 15000 }).should('have.length.at.least', 1);
  });

  it('Save button opens the quick-add modal with the correct title (apostrophe song)', () => {
    // Resolve the expected title into plain variables BEFORE asserting, so
    // .should('have.value', ...) compares against the string, not a chainable.
    cy.get('.rec-card').filter((i, el) => ((el.querySelector('.song-title') || {}).textContent || '').includes("'"))
      .first()
      .then(($card) => {
        const artist = $card.find('.song-artist').text().trim();
        const song = $card.find('.song-title').text().replace(/[“”]/g, '').trim();
        const expected = `${artist} – ${song}`;

        cy.wrap($card.find('.rec-btn-add')).click();
        cy.get('#quickAddOverlay').should('be.visible');
        cy.get('#qaTitle').should('have.value', expected);
        cy.get('.modal-close').click();
        cy.get('#quickAddOverlay').should('not.be.visible');
      });
  });

  it('every Save + Listen + Ignore button in the recommender has a parseable onclick handler', () => {
    cy.get('.rec-btn-add, .rec-btn-listen, .rec-btn-ignore').each(($btn) => {
      const onclick = $btn.attr('onclick');
      expect(onclick, 'onclick present').to.be.a('string');
      // Any broken inline handler (SyntaxError) fails to compile as a Function.
      expect(() => new Function(onclick), onclick).not.to.throw();
    });
  });

  it('Ignore removes the card and bans the song (self-cleaning)', () => {
    cy.get('.rec-card').first().then(($card) => {
      const artist = $card.find('.song-artist').text().trim();
      const song = $card.find('.song-title').text().replace(/[“”]/g, '').trim();
      const bannedValue = `${artist} – ${song}`;
      const total = Cypress.$('.rec-card').length;

      cy.wrap($card.find('.rec-btn-ignore')).click();

      // Card disappears from the view immediately.
      cy.get('.rec-card').should('have.length', total - 1);

      // Song landed in the ban list.
      cy.request('/api/ban-list').then((resp) => {
        const songs = (resp.body.songs || []).map((s) => s.toLowerCase());
        expect(songs).to.include(bannedValue.toLowerCase());
      });

      // Clean up so the user's real ban list is untouched.
      cy.request({
        method: 'POST',
        url: '/api/ban-list/remove',
        body: { type: 'songs', value: bannedValue },
        headers: { 'Content-Type': 'application/json' },
      }).then((resp) => {
        expect(resp.body.ban_list.songs || []).to.not.include(bannedValue);
      });
    });
  });

  it('Save button works on cards WITHOUT apostrophes too (sanity)', () => {
    cy.get('.rec-card').first().find('.rec-btn-add').click();
    cy.get('#quickAddOverlay').should('be.visible');
    cy.get('#qaTitle').should('not.have.value', '');
    cy.get('.modal-close').click();
    cy.get('#quickAddOverlay').should('not.be.visible');
  });

  it('Listen button on an apostrophe card runs without uncaught errors', () => {
    // Pre-fix, clicking this handler threw an uncaught SyntaxError, which the
    // support file's uncaught:exception handler propagates -> test fails.
    cy.get('.rec-card').filter((i, el) => ((el.querySelector('.song-title') || {}).textContent || '').includes("'"))
      .first()
      .then(($card) => {
        cy.wrap($card.find('.rec-btn-listen')).click();
      });
    // Give the async handler a beat; the afterEach assertNoConsoleErrors + the
    // uncaught:exception propagation are what catch a pre-fix failure.
    cy.wait(500);
  });
});

describe('Weekly & Challenge Save buttons — apostrophe-safe', () => {
  beforeEach(() => {
    cy.visit('/');
    cy.waitForApp();
  });

  it('every weekly + challenge inline onclick parses', () => {
    cy.navigateToView('weekly');
    cy.get('.weekly-pick', { timeout: 15000 }).should('have.length.at.least', 1);
    cy.get('.weekly-pick .rec-btn-add, .weekly-pick .rec-btn-listen, .weekly-pick .rec-btn-ignore').each(($btn) => {
      expect(() => new Function($btn.attr('onclick')), $btn.attr('onclick')).not.to.throw();
    });

    cy.navigateToView('challenge');
    cy.get('.challenge-card', { timeout: 15000 }).should('have.length.at.least', 1);
    cy.get('.challenge-card .rec-btn-add, .challenge-card .rec-btn-listen, .challenge-card .rec-btn-ignore').each(($btn) => {
      expect(() => new Function($btn.attr('onclick')), $btn.attr('onclick')).not.to.throw();
    });
  });
});
