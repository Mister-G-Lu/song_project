// Focused regression spec for the Artist Constellation layout guarantees:
//   1. Genre & Taste mode: genre spectrum on X (similar genres share horizontal
//      spans left→right), rating on Y (highest-rated at top, lowest at bottom)
//      across the full chart height — deterministic, no force simulation.
//   2. Followers mode: rating also sorts vertically within each genre row.
describe('Constellation layout regression', () => {
  beforeEach(() => {
    cy.visit('/');
    cy.get('.nav-item[data-view="constellation"]').click();
  });

  it('Genre & Taste: similar genres share horizontal spans, highest-rated at top', () => {
    cy.get('#constellationSvg circle', { timeout: 30000 }).should('have.length.at.least', 10);
    cy.window().then((win) => {
      const nodes = win.d3.select('#constellationSvg').selectAll('g.node').data();
      expect(nodes.length, 'nodes rendered').to.be.at.least(10);

      // --- Rating → Y monotonicity (the user's core ask) ---
      // For every genre that has both loved (avg>=90) and disliked (avg<70) artists,
      // the mean screen-y of loved nodes must be LESS (higher on the y-down canvas)
      // than the mean screen-y of disliked nodes.
      const byGenre = {};
      nodes.forEach((n) => {
        const g = n.genre || 'Uncategorized';
        (byGenre[g] = byGenre[g] || []).push(n);
      });
      const mean = (a) => a.reduce((s, v) => s + v, 0) / a.length;
      let ratingChecked = 0;
      for (const [g, arr] of Object.entries(byGenre)) {
        const hi = arr.filter((n) => n.avg_rating >= 90).map((n) => n.y);
        const lo = arr.filter((n) => n.avg_rating < 70).map((n) => n.y);
        if (hi.length >= 3 && lo.length >= 2) {
          ratingChecked += 1;
          expect(mean(hi), `loved-y above disliked-y in ${g}`).to.be.lessThan(mean(lo));
        }
      }
      expect(ratingChecked, 'genres with both loved+disliked tiers').to.be.at.least(2);

      // --- Genre spectrum X ordering ---
      // Confirm that musically similar genres are positioned close together on X.
      // Rock (0.52) should be left of Metal (0.66) and right of Pop (0.24).
      // Electronic/Dance (0.74) should be right of Metal (0.66).
      // Folk/Acoustic (0.82) should be right of Electronic (0.74).
      const genreX = {};
      nodes.forEach((n) => {
        const g = n.genre || 'Uncategorized';
        if (g && g !== 'Uncategorized' && g !== 'META/Other') {
          genreX[g] = genreX[g] || n.x;
        }
      });
      const avgX = (genre) => {
        const xs = nodes.filter(n => (n.genre || 'Uncategorized') === genre).map(n => n.x);
        return xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : null;
      };
      const rockX = avgX('Rock');
      const metalX = avgX('Metal');
      const popX = avgX('Pop');
      const electronicX = avgX('Electronic/Dance');
      const folkX = avgX('Folk/Acoustic');
      // Rock is between Pop (left) and Metal/Electronic (right) on the spectrum.
      if (rockX != null && popX != null) {
        expect(rockX, 'Rock right of Pop on spectrum').to.be.greaterThan(popX);
      }
      if (metalX != null && rockX != null) {
        expect(metalX, 'Metal right of Rock on spectrum').to.be.greaterThan(rockX);
      }
      if (electronicX != null && metalX != null) {
        expect(electronicX, 'Electronic right of Metal on spectrum').to.be.greaterThan(metalX);
      }
      if (folkX != null && electronicX != null) {
        expect(folkX, 'Folk right of Electronic on spectrum').to.be.greaterThan(electronicX);
      }
    });
  });

  it('Followers chart sorts rating vertically within genre rows', () => {
    cy.get('.mode-btn[data-mode="followers"]').click();
    cy.get('#constellationSvg circle', { timeout: 30000 }).should('have.length.at.least', 10);
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
        const hi = arr.filter((n) => n.avg_rating >= 90).map((n) => n.y);
        const lo = arr.filter((n) => n.avg_rating < 70).map((n) => n.y);
        if (hi.length >= 3 && lo.length >= 2) {
          checked += 1;
          expect(mean(hi), `loved-y above disliked-y in ${g}`).to.be.lessThan(mean(lo));
        }
      }
      expect(checked, 'genres with both tiers').to.be.at.least(2);
    });
  });

  it('Connections mode renders all artists with community clusters and edges', () => {
    cy.get('.mode-btn[data-mode="connections"]').click();
    // Wait for the force simulation to render nodes (they start at center then spread).
    cy.get('#constellationSvg circle', { timeout: 30000 }).should('have.length.at.least', 10);
    cy.wait(4000);
    cy.window().then((win) => {
      const nodes = win.d3.select('#constellationSvg').selectAll('g.node').data();
      expect(nodes.length, 'connections mode renders all nodes').to.be.at.least(100);

      // The force layout should have spread nodes away from the center seed
      // (width/2, height/2) — if nodes are still all at center, the simulation
      // didn't run.
      const xs = nodes.map(n => n.x);
      const ys = nodes.map(n => n.y);
      const meanX = xs.reduce((a, b) => a + b, 0) / xs.length;
      const meanY = ys.reduce((a, b) => a + b, 0) / ys.length;
      const varianceX = xs.reduce((s, v) => s + (v - meanX) ** 2, 0) / xs.length;
      const varianceY = ys.reduce((s, v) => s + (v - meanY) ** 2, 0) / ys.length;
      // With 1600+ nodes and charge force, variance should be substantial.
      // If variance is tiny, nodes are still stacked at center.
      expect(varianceX, 'nodes spread horizontally by force layout').to.be.greaterThan(500);
      expect(varianceY, 'nodes spread vertically by force layout').to.be.greaterThan(500);

      // Community metadata should be present — each node carries community_id.
      const nodesWithCommunity = nodes.filter(n => n.community_id != null && n.community_id >= 0);
      expect(nodesWithCommunity.length, 'nodes have community IDs').to.be.at.least(50);

      // Edges should be rendered (lines in the links group).
      const links = win.d3.select('#constellationSvg').selectAll('line.link').nodes();
      expect(links.length, 'edges rendered in connections mode').to.be.at.least(50);
    });
  });

  it('Switching between Genre & Taste and Connections preserves node count', () => {
    // Load genre mode first.
    cy.get('#constellationSvg circle', { timeout: 30000 }).should('have.length.at.least', 10);
    cy.window().then((win) => {
      const genreCount = win.d3.select('#constellationSvg').selectAll('g.node').data().length;
      expect(genreCount, 'genre mode node count').to.be.greaterThan(100);
      return genreCount;
    }).then((genreCount) => {
      // Switch to connections.
      cy.get('.mode-btn[data-mode="connections"]').click();
      cy.get('#constellationSvg circle', { timeout: 30000 }).should('have.length.at.least', 10);
      cy.window().then((win) => {
        const connCount = win.d3.select('#constellationSvg').selectAll('g.node').data().length;
        expect(connCount, 'connections mode node count').to.be.greaterThan(100);
        // Both modes should render the same number of nodes (all artists).
        expect(connCount, 'same node count in both modes').to.equal(genreCount);
      });
    });
  });
});

