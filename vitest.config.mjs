import { defineConfig } from 'vitest/config';

export default defineConfig({
    test: {
        environment: 'jsdom',
        include: ['tests/js/**/*.test.js'],
        coverage: {
            provider: 'v8',
            reporter: ['text', 'json-summary'],
            include: ['static/js/delegate.js', 'static/js/delegate-handlers.js', 'static/js/utils.js'],
            // P1 exit gate: 80% on the delegation/escaping/loading layer.
            thresholds: {
                statements: 80,
                branches: 80,
                functions: 80,
                lines: 80,
            },
        },
    },
});
