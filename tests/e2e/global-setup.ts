/**
 * S.S.I. SHADOW - Playwright Global Setup
 * Runs before all E2E tests
 */

import { chromium, FullConfig } from '@playwright/test';

async function globalSetup(config: FullConfig) {
  console.log('[E2E Setup] Starting global setup...');
  
  // Check if the server is running
  const baseURL = config.projects[0].use?.baseURL || 'http://localhost:3000';
  
  try {
    const browser = await chromium.launch();
    const page = await browser.newPage();
    
    // Try to connect to the app
    await page.goto(baseURL, { timeout: 10000 });
    console.log(`[E2E Setup] Server is running at ${baseURL}`);
    
    await browser.close();
  } catch (error) {
    console.error(`[E2E Setup] Server not available at ${baseURL}`);
    console.error('[E2E Setup] Make sure to run: npm run dev --prefix dashboard');
    throw new Error('E2E server not available');
  }
  
  // Setup test data if needed
  console.log('[E2E Setup] Global setup complete');
}

export default globalSetup;
