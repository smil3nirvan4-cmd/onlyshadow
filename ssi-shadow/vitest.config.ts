import { defineConfig } from 'vitest/config';
import path from 'path';

export default defineConfig({
  test: {
    // Test environment
    environment: 'miniflare',
    environmentOptions: {
      modules: true,
      scriptPath: './workers/gateway/src/index.ts',
      kvNamespaces: ['RATE_LIMIT_KV'],
    },
    
    // Test files pattern
    include: [
      'tests/unit/workers/**/*.test.ts',
      'tests/unit/workers/**/*.spec.ts',
    ],
    
    // Exclude patterns
    exclude: [
      'node_modules',
      'dist',
      '.wrangler',
    ],
    
    // Coverage configuration
    coverage: {
      provider: 'v8',
      reporter: ['text', 'json', 'html', 'lcov'],
      reportsDirectory: './coverage/workers',
      include: [
        'workers/gateway/src/**/*.ts',
      ],
      exclude: [
        'workers/gateway/src/**/*.d.ts',
        'workers/gateway/src/types/**',
        'node_modules',
      ],
      // Target 80% coverage
      thresholds: {
        lines: 80,
        functions: 80,
        branches: 75,
        statements: 80,
      },
    },
    
    // Global setup
    setupFiles: ['./tests/setup.ts'],
    
    // Timeout for tests
    testTimeout: 10000,
    
    // Reporter
    reporters: ['verbose', 'json'],
    outputFile: {
      json: './test-results/workers.json',
    },
    
    // Globals
    globals: true,
  },
  
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './workers/gateway/src'),
      '@fixtures': path.resolve(__dirname, './tests/fixtures'),
    },
  },
});
