# 🧪 S.S.I. SHADOW - Testing Suite

Comprehensive testing suite with 80%+ code coverage target.

## 📁 Structure

```
tests/
├── unit/
│   ├── workers/           # TypeScript tests (Vitest)
│   │   ├── hash.test.ts
│   │   ├── trust-score.test.ts
│   │   ├── event-validation.test.ts
│   │   └── bid-optimizer.test.ts
│   └── python/            # Python tests (Pytest)
│       ├── test_groas_system.py
│       └── test_ml_modules.py
├── integration/           # Integration tests
│   └── platform-dispatch.test.ts
├── e2e/                   # E2E tests (Playwright)
│   ├── dashboard.spec.ts
│   ├── global-setup.ts
│   └── global-teardown.ts
├── load/                  # Load tests (k6)
│   └── worker-load.js
├── fixtures/              # Test data
│   └── index.ts
├── setup.ts              # Global test setup
├── conftest.py           # Pytest configuration
└── package.json          # Test dependencies
```

## 🚀 Quick Start

### Install Dependencies

```bash
# Install Node.js dependencies
npm install

# Install Python dependencies
pip install pytest pytest-cov pytest-asyncio black isort flake8 mypy

# Install Playwright browsers
npx playwright install

# Install k6 (macOS)
brew install k6

# Install k6 (Linux)
sudo gpg -k
sudo gpg --no-default-keyring --keyring /usr/share/keyrings/k6-archive-keyring.gpg --keyserver hkp://keyserver.ubuntu.com:80 --recv-keys C5AD17C747E3415A3642D57D77C6C491D6AC1D69
echo "deb [signed-by=/usr/share/keyrings/k6-archive-keyring.gpg] https://dl.k6.io/deb stable main" | sudo tee /etc/apt/sources.list.d/k6.list
sudo apt-get update
sudo apt-get install k6
```

### Run Tests

```bash
# Run all tests
npm test

# Run unit tests only
npm run test:unit

# Run TypeScript unit tests with watch mode
npm run test:unit:ts:watch

# Run Python unit tests
npm run test:unit:py

# Run integration tests
npm run test:integration

# Run E2E tests
npm run test:e2e

# Run load tests
npm run test:load
```

## 📊 Coverage Targets

| Category | Target | Current |
|----------|--------|---------|
| TypeScript (Workers) | 80% | - |
| Python (Engines) | 80% | - |
| Integration | 90% | - |
| E2E | N/A | - |

## 🧪 Test Categories

### Unit Tests

**TypeScript (Vitest)**
- `hash.test.ts` - SHA-256 hashing, normalization
- `trust-score.test.ts` - Bot detection, score calculation
- `event-validation.test.ts` - Input validation, sanitization
- `bid-optimizer.test.ts` - Strategy calculation, multipliers

**Python (Pytest)**
- `test_groas_system.py` - Search intent, agents
- `test_ml_modules.py` - LTV, churn, propensity predictions

### Integration Tests

- Worker → Meta CAPI
- Worker → TikTok Events API
- Worker → Google Measurement Protocol
- Worker → BigQuery
- Full event flow (Ghost → Worker → Platforms)

### E2E Tests (Playwright)

- Dashboard navigation
- Overview tab metrics
- Platform status display
- Trust score visualization
- ML predictions charts
- Funnel analysis
- Real-time updates
- Export functionality
- Responsive design
- Error handling
- Accessibility

### Load Tests (k6)

| Test Type | Description | Duration |
|-----------|-------------|----------|
| **Standard** | Ramp to 1000 VUs | 10 min |
| **Spike** | Sudden 5000 VUs spike | 6 min |
| **Soak** | 200 VUs for 4 hours | 4 hours |
| **Stress** | Find breaking point | 37 min |

**Performance Targets:**
- ✅ 1000 req/s sustained
- ✅ Latency p99 < 300ms
- ✅ Error rate < 0.1%

## 📋 Test Commands

### Unit Tests

```bash
# TypeScript
npm run test:unit:ts              # Run once
npm run test:unit:ts:watch        # Watch mode
npm run test:unit:ts -- --ui      # UI mode

# Python
npm run test:unit:py              # Run once
pytest -v -x                      # Stop on first failure
pytest -k "test_ltv"             # Run specific tests
```

### Integration Tests

```bash
npm run test:integration
npm run test:integration -- --reporter=verbose
```

### E2E Tests

```bash
npm run test:e2e                  # Run all
npm run test:e2e:headed           # With browser visible
npm run test:e2e:ui               # Interactive UI
npm run test:e2e:debug            # Debug mode
npm run test:e2e -- --project=chromium  # Specific browser
```

### Load Tests

```bash
# Standard load test
npm run test:load

# With environment variables
BASE_URL=https://your-worker.workers.dev npm run test:load

# Specific scenarios
npm run test:load:spike
npm run test:load:soak
npm run test:load:stress

# Custom options
k6 run --vus 100 --duration 1m tests/load/worker-load.js
```

## 📈 Coverage Reports

```bash
# Generate coverage
npm run test:coverage

# View coverage reports
npm run test:coverage:report

# Coverage locations:
# - TypeScript: coverage/workers/index.html
# - Python: coverage/python/index.html
```

## 🔧 Configuration Files

| File | Purpose |
|------|---------|
| `vitest.config.ts` | Vitest configuration |
| `pytest.ini` | Pytest configuration |
| `playwright.config.ts` | Playwright configuration |
| `tests/load/worker-load.js` | k6 configuration |
| `tests/setup.ts` | Global test setup |
| `tests/conftest.py` | Pytest fixtures |

## 🏷️ Test Markers (Python)

```bash
# Run only unit tests
pytest -m unit

# Run only integration tests
pytest -m integration

# Skip slow tests
pytest -m "not slow"

# Run API tests
pytest -m api
```

## 📝 Writing New Tests

### TypeScript (Vitest)

```typescript
import { describe, it, expect, vi } from 'vitest';
import { mockPageViewFull } from '@fixtures';

describe('MyComponent', () => {
  it('should do something', () => {
    const result = myFunction(mockPageViewFull);
    expect(result).toBeDefined();
  });
});
```

### Python (Pytest)

```python
import pytest
from my_module import my_function

class TestMyModule:
    def test_something(self, mock_purchase_event):
        result = my_function(mock_purchase_event.to_dict())
        assert result is not None
```

### E2E (Playwright)

```typescript
import { test, expect } from '@playwright/test';

test('should display dashboard', async ({ page }) => {
  await page.goto('/');
  await expect(page.locator('[data-testid="dashboard"]')).toBeVisible();
});
```

## 🔍 Debugging

### Vitest

```bash
# Debug mode
npm run test:unit:ts -- --reporter=verbose

# Run specific test
npm run test:unit:ts -- hash.test.ts
```

### Pytest

```bash
# Verbose output
pytest -vvv

# Print statements
pytest -s

# Debug on failure
pytest --pdb
```

### Playwright

```bash
# Debug mode
npm run test:e2e:debug

# Trace viewer
npx playwright show-trace trace.zip
```

### k6

```bash
# Verbose output
k6 run --verbose tests/load/worker-load.js

# Debug single VU
k6 run --vus 1 --iterations 1 tests/load/worker-load.js
```

## 📊 CI Integration

```yaml
# GitHub Actions example
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Setup Node.js
        uses: actions/setup-node@v4
        with:
          node-version: '20'
      
      - name: Install dependencies
        run: npm ci
      
      - name: Run unit tests
        run: npm run test:unit
      
      - name: Run integration tests
        run: npm run test:integration
      
      - name: Install Playwright
        run: npx playwright install --with-deps
      
      - name: Run E2E tests
        run: npm run test:e2e
      
      - name: Upload coverage
        uses: codecov/codecov-action@v3
```

## 📈 Metrics

After running tests, check:

- `coverage/workers/index.html` - TypeScript coverage
- `coverage/python/index.html` - Python coverage
- `test-results/e2e-report/index.html` - E2E report
- `test-results/load-test-summary.json` - Load test results
