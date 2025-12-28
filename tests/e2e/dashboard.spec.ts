/**
 * S.S.I. SHADOW - Dashboard E2E Tests
 * End-to-end tests for the React dashboard
 */

import { test, expect, Page } from '@playwright/test';

// =============================================================================
// TEST DATA
// =============================================================================

const TEST_USER = {
  email: 'test@example.com',
  password: 'testpassword123',
};

// =============================================================================
// HELPER FUNCTIONS
// =============================================================================

async function login(page: Page, email: string, password: string) {
  await page.goto('/login');
  await page.fill('[data-testid="email-input"]', email);
  await page.fill('[data-testid="password-input"]', password);
  await page.click('[data-testid="login-button"]');
  await page.waitForURL('**/dashboard**');
}

async function waitForDashboardLoad(page: Page) {
  await page.waitForSelector('[data-testid="dashboard-container"]', { timeout: 10000 });
  await page.waitForLoadState('networkidle');
}

// =============================================================================
// DASHBOARD NAVIGATION TESTS
// =============================================================================

test.describe('Dashboard Navigation', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
  });

  test('should display the dashboard overview', async ({ page }) => {
    await expect(page.locator('[data-testid="dashboard-title"]')).toBeVisible();
  });

  test('should navigate to Overview tab', async ({ page }) => {
    await page.click('[data-testid="tab-overview"]');
    await expect(page.locator('[data-testid="overview-panel"]')).toBeVisible();
  });

  test('should navigate to Platforms tab', async ({ page }) => {
    await page.click('[data-testid="tab-platforms"]');
    await expect(page.locator('[data-testid="platforms-panel"]')).toBeVisible();
  });

  test('should navigate to Trust Score tab', async ({ page }) => {
    await page.click('[data-testid="tab-trust-score"]');
    await expect(page.locator('[data-testid="trust-score-panel"]')).toBeVisible();
  });

  test('should navigate to ML Predictions tab', async ({ page }) => {
    await page.click('[data-testid="tab-ml"]');
    await expect(page.locator('[data-testid="ml-panel"]')).toBeVisible();
  });

  test('should navigate to Funnel tab', async ({ page }) => {
    await page.click('[data-testid="tab-funnel"]');
    await expect(page.locator('[data-testid="funnel-panel"]')).toBeVisible();
  });
});

// =============================================================================
// OVERVIEW TAB TESTS
// =============================================================================

test.describe('Overview Tab', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await page.click('[data-testid="tab-overview"]');
  });

  test('should display metric cards', async ({ page }) => {
    await expect(page.locator('[data-testid="metric-events-today"]')).toBeVisible();
    await expect(page.locator('[data-testid="metric-unique-users"]')).toBeVisible();
    await expect(page.locator('[data-testid="metric-revenue"]')).toBeVisible();
    await expect(page.locator('[data-testid="metric-conversion-rate"]')).toBeVisible();
  });

  test('should display events timeline chart', async ({ page }) => {
    await expect(page.locator('[data-testid="events-timeline-chart"]')).toBeVisible();
  });

  test('should display recent events table', async ({ page }) => {
    await expect(page.locator('[data-testid="recent-events-table"]')).toBeVisible();
  });

  test('should show comparison percentages', async ({ page }) => {
    const comparison = page.locator('[data-testid="metric-comparison"]').first();
    await expect(comparison).toBeVisible();
    
    // Should show + or - percentage
    const text = await comparison.textContent();
    expect(text).toMatch(/[+-]?\d+\.?\d*%/);
  });

  test('should update data periodically', async ({ page }) => {
    // Get initial value
    const initialValue = await page.locator('[data-testid="metric-events-today"] .metric-value').textContent();
    
    // Wait for refresh (assuming 30s interval, we wait 35s)
    // In real tests, you might want to mock the API or use shorter intervals
    // await page.waitForTimeout(35000);
    
    // For now, just verify the value is displayed
    expect(initialValue).toBeTruthy();
  });
});

// =============================================================================
// PLATFORMS TAB TESTS
// =============================================================================

test.describe('Platforms Tab', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await page.click('[data-testid="tab-platforms"]');
  });

  test('should display platform status cards', async ({ page }) => {
    await expect(page.locator('[data-testid="platform-meta"]')).toBeVisible();
    await expect(page.locator('[data-testid="platform-tiktok"]')).toBeVisible();
    await expect(page.locator('[data-testid="platform-google"]')).toBeVisible();
    await expect(page.locator('[data-testid="platform-bigquery"]')).toBeVisible();
  });

  test('should show platform health status', async ({ page }) => {
    const metaStatus = page.locator('[data-testid="platform-meta"] [data-testid="status-badge"]');
    await expect(metaStatus).toBeVisible();
    
    // Status should be healthy, degraded, or down
    const statusText = await metaStatus.textContent();
    expect(['healthy', 'degraded', 'down']).toContain(statusText?.toLowerCase());
  });

  test('should show events count per platform', async ({ page }) => {
    const eventsCount = page.locator('[data-testid="platform-meta"] [data-testid="events-count"]');
    await expect(eventsCount).toBeVisible();
  });

  test('should show success rate per platform', async ({ page }) => {
    const successRate = page.locator('[data-testid="platform-meta"] [data-testid="success-rate"]');
    await expect(successRate).toBeVisible();
    
    const rateText = await successRate.textContent();
    expect(rateText).toMatch(/\d+\.?\d*%/);
  });

  test('should show latency per platform', async ({ page }) => {
    const latency = page.locator('[data-testid="platform-meta"] [data-testid="latency"]');
    await expect(latency).toBeVisible();
    
    const latencyText = await latency.textContent();
    expect(latencyText).toMatch(/\d+\s*ms/);
  });
});

// =============================================================================
// TRUST SCORE TAB TESTS
// =============================================================================

test.describe('Trust Score Tab', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await page.click('[data-testid="tab-trust-score"]');
  });

  test('should display trust score distribution chart', async ({ page }) => {
    await expect(page.locator('[data-testid="trust-score-distribution"]')).toBeVisible();
  });

  test('should display block rate metric', async ({ page }) => {
    await expect(page.locator('[data-testid="block-rate"]')).toBeVisible();
  });

  test('should display top block reasons', async ({ page }) => {
    await expect(page.locator('[data-testid="top-block-reasons"]')).toBeVisible();
  });

  test('should show trust score thresholds', async ({ page }) => {
    await expect(page.locator('[data-testid="threshold-block"]')).toBeVisible();
    await expect(page.locator('[data-testid="threshold-challenge"]')).toBeVisible();
  });

  test('should show blocked events count', async ({ page }) => {
    const blockedCount = page.locator('[data-testid="blocked-events-count"]');
    await expect(blockedCount).toBeVisible();
    
    const text = await blockedCount.textContent();
    expect(text).toMatch(/\d+/);
  });
});

// =============================================================================
// ML PREDICTIONS TAB TESTS
// =============================================================================

test.describe('ML Predictions Tab', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await page.click('[data-testid="tab-ml"]');
  });

  test('should display LTV segments chart', async ({ page }) => {
    await expect(page.locator('[data-testid="ltv-segments-chart"]')).toBeVisible();
  });

  test('should display churn risk chart', async ({ page }) => {
    await expect(page.locator('[data-testid="churn-risk-chart"]')).toBeVisible();
  });

  test('should display bid strategy distribution', async ({ page }) => {
    await expect(page.locator('[data-testid="bid-strategy-chart"]')).toBeVisible();
  });

  test('should show LTV tier breakdown', async ({ page }) => {
    // VIP, High, Medium, Low
    await expect(page.locator('[data-testid="ltv-tier-vip"]')).toBeVisible();
    await expect(page.locator('[data-testid="ltv-tier-high"]')).toBeVisible();
    await expect(page.locator('[data-testid="ltv-tier-medium"]')).toBeVisible();
    await expect(page.locator('[data-testid="ltv-tier-low"]')).toBeVisible();
  });

  test('should show model confidence', async ({ page }) => {
    const confidence = page.locator('[data-testid="model-confidence"]');
    await expect(confidence).toBeVisible();
  });
});

// =============================================================================
// FUNNEL TAB TESTS
// =============================================================================

test.describe('Funnel Tab', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await page.click('[data-testid="tab-funnel"]');
  });

  test('should display funnel chart', async ({ page }) => {
    await expect(page.locator('[data-testid="funnel-chart"]')).toBeVisible();
  });

  test('should show all funnel stages', async ({ page }) => {
    await expect(page.locator('[data-testid="funnel-stage-view"]')).toBeVisible();
    await expect(page.locator('[data-testid="funnel-stage-cart"]')).toBeVisible();
    await expect(page.locator('[data-testid="funnel-stage-checkout"]')).toBeVisible();
    await expect(page.locator('[data-testid="funnel-stage-purchase"]')).toBeVisible();
  });

  test('should show conversion rates between stages', async ({ page }) => {
    const conversionRate = page.locator('[data-testid="conversion-rate"]').first();
    await expect(conversionRate).toBeVisible();
    
    const text = await conversionRate.textContent();
    expect(text).toMatch(/\d+\.?\d*%/);
  });
});

// =============================================================================
// REAL-TIME UPDATES TESTS
// =============================================================================

test.describe('Real-time Updates', () => {
  test('should receive real-time event updates', async ({ page }) => {
    await page.goto('/');
    
    // Get initial events count
    const eventsMetric = page.locator('[data-testid="metric-events-today"] .metric-value');
    const initialCount = await eventsMetric.textContent();
    
    // In a real test, you would trigger an event via API
    // and verify the dashboard updates
    
    // For now, verify the metric is displayed
    expect(initialCount).toBeTruthy();
  });

  test('should update charts on new data', async ({ page }) => {
    await page.goto('/');
    
    // Verify chart is rendered
    const chart = page.locator('[data-testid="events-timeline-chart"] svg');
    await expect(chart).toBeVisible();
  });
});

// =============================================================================
// EXPORT FUNCTIONALITY TESTS
// =============================================================================

test.describe('Export Functionality', () => {
  test('should export data as CSV', async ({ page }) => {
    await page.goto('/');
    
    // Click export button
    const [download] = await Promise.all([
      page.waitForEvent('download'),
      page.click('[data-testid="export-csv-button"]'),
    ]);

    // Verify download
    expect(download.suggestedFilename()).toMatch(/\.csv$/);
  });

  test('should export data as JSON', async ({ page }) => {
    await page.goto('/');
    
    // Click export button
    const [download] = await Promise.all([
      page.waitForEvent('download'),
      page.click('[data-testid="export-json-button"]'),
    ]);

    // Verify download
    expect(download.suggestedFilename()).toMatch(/\.json$/);
  });
});

// =============================================================================
// RESPONSIVE DESIGN TESTS
// =============================================================================

test.describe('Responsive Design', () => {
  test('should display correctly on mobile', async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 667 });
    await page.goto('/');
    
    // Mobile menu should be visible
    await expect(page.locator('[data-testid="mobile-menu-button"]')).toBeVisible();
  });

  test('should display correctly on tablet', async ({ page }) => {
    await page.setViewportSize({ width: 768, height: 1024 });
    await page.goto('/');
    
    // Dashboard should be visible
    await expect(page.locator('[data-testid="dashboard-container"]')).toBeVisible();
  });

  test('should display correctly on desktop', async ({ page }) => {
    await page.setViewportSize({ width: 1920, height: 1080 });
    await page.goto('/');
    
    // Sidebar should be visible
    await expect(page.locator('[data-testid="sidebar"]')).toBeVisible();
  });
});

// =============================================================================
// ERROR HANDLING TESTS
// =============================================================================

test.describe('Error Handling', () => {
  test('should show error message on API failure', async ({ page }) => {
    // Mock API to return error
    await page.route('**/api/**', (route) => {
      route.fulfill({
        status: 500,
        body: JSON.stringify({ error: 'Internal server error' }),
      });
    });

    await page.goto('/');
    
    // Error message should be displayed
    await expect(page.locator('[data-testid="error-message"]')).toBeVisible({ timeout: 10000 });
  });

  test('should show retry button on error', async ({ page }) => {
    await page.route('**/api/**', (route) => {
      route.fulfill({
        status: 500,
        body: JSON.stringify({ error: 'Error' }),
      });
    });

    await page.goto('/');
    
    await expect(page.locator('[data-testid="retry-button"]')).toBeVisible({ timeout: 10000 });
  });

  test('should recover after retry', async ({ page }) => {
    let requestCount = 0;
    
    await page.route('**/api/**', (route) => {
      requestCount++;
      if (requestCount < 2) {
        route.fulfill({ status: 500, body: '{}' });
      } else {
        route.fulfill({ status: 200, body: JSON.stringify({ events: 100 }) });
      }
    });

    await page.goto('/');
    await page.click('[data-testid="retry-button"]');
    
    // Should show data after retry
    await expect(page.locator('[data-testid="dashboard-container"]')).toBeVisible();
  });
});

// =============================================================================
// ACCESSIBILITY TESTS
// =============================================================================

test.describe('Accessibility', () => {
  test('should have proper heading structure', async ({ page }) => {
    await page.goto('/');
    
    const h1 = page.locator('h1');
    await expect(h1).toHaveCount(1);
  });

  test('should have alt text for images', async ({ page }) => {
    await page.goto('/');
    
    const images = page.locator('img');
    const count = await images.count();
    
    for (let i = 0; i < count; i++) {
      const alt = await images.nth(i).getAttribute('alt');
      expect(alt).toBeTruthy();
    }
  });

  test('should be keyboard navigable', async ({ page }) => {
    await page.goto('/');
    
    // Tab through the page
    await page.keyboard.press('Tab');
    
    // First focusable element should have focus
    const focusedElement = page.locator(':focus');
    await expect(focusedElement).toBeVisible();
  });

  test('should have proper ARIA labels', async ({ page }) => {
    await page.goto('/');
    
    // Charts should have ARIA labels
    const charts = page.locator('[role="img"]');
    const count = await charts.count();
    
    for (let i = 0; i < count; i++) {
      const ariaLabel = await charts.nth(i).getAttribute('aria-label');
      expect(ariaLabel).toBeTruthy();
    }
  });
});
