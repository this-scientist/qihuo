const {chromium} = require('playwright');
const assert = require('node:assert/strict');
const {mkdirSync} = require('node:fs');

(async () => {
  mkdirSync('output', {recursive:true});
  const browser = await chromium.launch({channel:process.env.BROWSER_CHANNEL || 'chrome', headless:true});
  try {
    const page = await browser.newPage({viewport:{width:1500,height:1000}});
    const errors = [];
    page.on('pageerror', error => errors.push(String(error)));
    await page.goto((process.env.DASHBOARD_URL || 'http://127.0.0.1:8765')+'/?asof=20260921', {waitUntil:'networkidle'});
    assert.equal(await page.locator('.top-tabs button').count(),3);
    assert.equal(await page.locator('tr[data-code]').count(),68);
    const headers = await page.locator('.decision-table thead').innerText();
    for (const field of ['趋势方向','当日','5日','20日','RPS5','RPS20','RPS加速度','主力持仓','主次OI','跨期价差','期限结构','结构方向','爆发指数']) assert(headers.includes(field),field);
    await page.screenshot({path:'output/unified-desktop.png'});
    await page.locator('#commodity-search').fill('LC');
    const row = page.locator('tr[data-code]');
    assert.equal(await row.count(),1);
    assert.equal(await row.locator('td').nth(1).innerText(),'偏空');
    assert((await row.locator('td').nth(2).innerText()).includes('偏多'));
    console.log('LC overview:', await row.innerText());
    await row.click();
    assert((await page.locator('.detail-metrics').innerText()).includes('RPS5'));
    assert((await page.locator('.structure-grid').last().innerText()).includes('500.00'));
    assert(await page.locator('#single-chart path[data-series]').count()>0);
    await page.screenshot({path:'output/unified-lc.png'});
    await page.locator('[data-jump-options]').click();
    await page.waitForSelector('.t-chain');
    assert((await page.locator('.underlying-state').innerText()).includes('偏空'));
    await page.locator('.top-tabs [data-view="market"]').click();
    await page.locator('#commodity-search').fill('');
    await page.locator('#side-filter').selectOption('long');
    for (const value of await page.locator('tr[data-code] td:nth-child(2)').allTextContents()) assert.equal(value,'偏多');
    await page.locator('#side-filter').selectOption('all');
    await page.setViewportSize({width:390,height:844});
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
    await page.screenshot({path:'output/unified-mobile.png',fullPage:true});
    const scanner = await page.request.get(new URL('/api/scanner?asof=20260921',page.url()).href);
    assert(scanner.ok());
    const scan = await scanner.json();
    const lc = scan.structure.find(item=>item.ts_code==='LC.GFE');
    assert.equal(lc.dominant,'long');
    assert.equal(lc.trend_direction,'short');
    assert.deepEqual(errors,[]);
    console.log('Passed: overview, filters, LC direction/structure, detail, options, scanner consistency, desktop/mobile, no JS errors');
  } finally {
    await browser.close();
  }
})().catch(error=>{console.error(error);process.exitCode=1});
