// Development-only browser capture. Run against the isolated server in docs/demo.md.
// Playwright is provisioned separately; no application behavior or providers are replaced.
const assert = require('node:assert/strict');
const path = require('node:path');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');

(async () => {
  const browser = await chromium.launch({ headless: true });
  try {
    const context = await browser.newContext({
      viewport: { width: 1440, height: 1000 }, deviceScaleFactor: 1,
      serviceWorkers: 'block',
    });
    const origin = 'http://127.0.0.1:8519';
    const blocked = new Set();
    await context.route('**/*', route => {
      if (new URL(route.request().url()).origin === origin) return route.continue();
      blocked.add(new URL(route.request().url()).origin);
      return route.abort();
    });
    const page = await context.newPage();
    await page.goto(origin);
    await page.getByRole('heading', { name: 'Your sources. One conversation.' }).waitFor();
    await page.getByRole('combobox', { name: 'Answer mode', exact: true }).waitFor();
    await page.getByText('Model setup required', { exact: true }).waitFor();
    await page.getByText('Model settings', { exact: true }).click();
    const model = page.getByRole('textbox', { name: 'Model', exact: true });
    assert.equal(await model.inputValue(), 'gemini-3.5-flash');
    await page.getByText('Model settings', { exact: true }).click();
    const example = page.getByRole('button', {
      name: 'Explain when retrieval-augmented generation is useful.', exact: true,
    });
    await example.click();
    const composer = page.getByPlaceholder('Ask a question across your sources…');
    await page.waitForFunction(() =>
      document.querySelector('[data-testid="stChatInput"] textarea')?.value ===
      'Explain when retrieval-augmented generation is useful.');
    assert.equal(await page.getByTestId('stChatMessage').count(), 0);
    await composer.fill('');
    await page.getByRole('button', { name: 'Reset workspace', exact: true }).click();
    await page.waitForTimeout(1000); // Settle the reset rerun and native layout.
    const output = name => path.resolve(__dirname, '../docs/screenshots', name);
    await page.screenshot({ path: output('overview.png'), animations: 'disabled' });
    await page.getByText('SQLite database', { exact: true }).click();
    const sample = page.getByRole('checkbox', { name: 'Use Chinook sample database', exact: true });
    await page.getByText('Use Chinook sample database', { exact: true }).click();
    assert.equal(await sample.isChecked(), true);
    await page.getByRole('textbox', { name: 'Database URI', exact: true }).waitFor({ state: 'detached' });
    await page.getByRole('button', { name: 'Connect', exact: true }).click();
    const schema = page.getByText('Schema (11 tables)', { exact: true });
    await schema.waitFor();
    await schema.click();
    await page.getByText(/Album\s+Artist\s+Customer/).waitFor();
    await page.getByText('SQLite · connected', { exact: true }).waitFor();
    const closeToast = page.getByRole('button', { name: 'Close', exact: true });
    if (await closeToast.count()) await closeToast.click();
    assert.equal(await page.getByTestId('stException').count(), 0);
    await page.screenshot({ path: output('chinook-schema.png'), animations: 'disabled' });
    await page.getByRole('button', { name: 'Disconnect', exact: true }).click();
    await schema.waitFor({ state: 'detached' });
    await page.getByRole('button', { name: 'Connect', exact: true }).click();
    await schema.waitFor();
    await page.getByRole('button', { name: 'Reset workspace', exact: true }).click();
    await schema.waitFor({ state: 'detached' });
    assert.equal(await sample.isChecked(), false);
    assert.equal(await page.getByTestId('stException').count(), 0);
    console.log(`PASS: startup, example draft, sample connect/schema/disconnect/reconnect/reset; Chromium ${browser.version()}`);
    console.log('Blocked browser origins:', [...blocked].join(', '));
  } finally {
    await browser.close();
  }
})();
