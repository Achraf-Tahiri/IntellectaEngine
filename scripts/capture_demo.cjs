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
    await page.getByText('Welcome to IntellectaEngine!', { exact: false }).waitFor();
    const model = page.getByRole('textbox', { name: '🧠 Model', exact: true });
    await model.waitFor();
    assert.equal(await model.inputValue(), 'gemini-3.5-flash');
    await page.getByRole('radio', { name: '🔄 Auto (Router decides)', exact: true }).waitFor();
    await page.waitForTimeout(2000); // Finish browser font/layout settling, not a provider wait.
    const output = name => path.resolve(__dirname, '../docs/screenshots', name);
    await page.screenshot({ path: output('overview.png'), animations: 'disabled' });
    const sample = page.getByRole('checkbox', { name: 'Use Chinook sample database', exact: true });
    await page.getByText('Use Chinook sample database', { exact: true }).click();
    assert.equal(await sample.isChecked(), true);
    await page.getByRole('button', { name: '🔗 Connect', exact: true }).click();
    const schema = page.getByText('📊 Schema (11 tables)', { exact: true });
    await schema.waitFor();
    await schema.click();
    await page.getByText('InvoiceLine', { exact: true }).waitFor();
    // Scroll the existing sidebar through normal browser interaction.
    await page.getByText('🗄️ SQL Database', { exact: true }).scrollIntoViewIfNeeded();
    await page.getByTestId('stSidebar').hover();
    await page.mouse.wheel(0, 290);
    await page.waitForTimeout(1500);
    assert.equal(await page.getByTestId('stException').count(), 0);
    await page.screenshot({ path: output('chinook-schema.png'), animations: 'disabled' });
    await page.getByRole('button', { name: '✖ Disconnect', exact: true }).click();
    await schema.waitFor({ state: 'detached' });
    await page.getByRole('button', { name: '🔗 Connect', exact: true }).click();
    await schema.waitFor();
    await page.getByRole('button', { name: '🔄 Reset', exact: true }).click();
    await schema.waitFor({ state: 'detached' });
    assert.equal(await sample.isChecked(), false);
    assert.equal(await page.getByTestId('stException').count(), 0);
    console.log(`PASS: startup, sample connect/schema/disconnect/reconnect/reset; Chromium ${browser.version()}`);
    console.log('Blocked browser origins:', [...blocked].join(', '));
  } finally {
    await browser.close();
  }
})();
