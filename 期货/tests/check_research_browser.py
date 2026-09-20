"""Acceptance checks for completed research and options workflow."""
import json
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

def main():
    output=Path(__file__).parents[1]/'output/playwright';output.mkdir(parents=True,exist_ok=True)
    with sync_playwright() as p:
        browser=p.chromium.launch(channel='msedge',headless=True)
        page=browser.new_page(viewport={'width':1500,'height':1000});errors=[]
        page.on('pageerror',lambda error:errors.append(str(error)))
        page.goto('http://127.0.0.1:8765/',wait_until='networkidle')
        page.wait_for_selector('#results tr[data-code]')
        assert page.locator('#results tr[data-code]').count()==68
        assert page.locator('#results tr[data-code="EG.DCE"]').inner_text().find('持续趋势')>=0
        assert page.locator('#results tr[data-code="MA.ZCE"]').inner_text().find('中短期强势')>=0
        assert page.locator('#results tr[data-code="SC.INE"]').inner_text().find('过度延伸')>=0
        page.locator('#phase-filter').select_option('趋势启动')
        assert page.locator('#results tr[data-code]').count()>0
        expected=page.locator('#results tr[data-code]').count();page.locator('#save-run').click()
        page.wait_for_timeout(200)
        assert f'{expected}品种已保存' in page.locator('#config-message').inner_text()
        page.screenshot(path=str(output/'phases-overview.png'),full_page=False)
        page.goto('http://127.0.0.1:8765/research.html',wait_until='networkidle')
        page.locator('#run-study').click();page.wait_for_function('document.querySelector("#study-summary").hidden === false')
        assert page.locator('#events tr').count()==10
        assert '25.00%' in page.locator('#study-summary').inner_text()
        assert '幸存者偏差' in page.locator('#study-limitations').inner_text()
        page.screenshot(path=str(output/'historical-validation.png'),full_page=False)
        # Custom conditions unsupported in past must be missing, not imputed.
        page.evaluate("localStorage.setItem('commodity-dashboard-config-v1',JSON.stringify({version:1,direction:'long',match:'all',rules:[{key:'oi_change5',op:'>=',value:0}]}))")
        page.locator('#mode').select_option('custom');page.locator('#run-study').click()
        page.wait_for_function('document.querySelector("#run-study").disabled === false')
        assert '0' in page.locator('#study-summary').inner_text()
        assert '12046' in page.locator('#study-limitations').inner_text()
        page.evaluate("localStorage.removeItem('commodity-dashboard-config-v1')")
        assert page.locator('#data-asof').is_visible()
        assert page.locator('#reload-data').count()==0
        page.goto('http://127.0.0.1:8765/options.html?asof=20260911&code=LC.GFE',wait_until='networkidle')
        page.locator('#min-days').fill('20');page.locator('#max-days').fill('120')
        page.locator('details').first.locator('summary').click()
        page.locator('#min-vol').fill('100');page.locator('#min-oi').fill('500');page.locator('#max-distance').fill('10')
        page.locator('#apply-options').click()
        page.wait_for_function("!document.querySelector('#apply-options').disabled")
        page.wait_for_selector('#option-rows tr[data-option]')
        assert page.locator('#option-side').input_value()=='P'
        assert page.locator('#option-rows tr[data-option]').count()==11
        assert '≈' in page.locator('#option-rows').inner_text()
        page.locator('#option-rows tr[data-option]').first.click()
        page.wait_for_selector('#option-underlying-chart path[data-series]')
        assert page.locator('#payoff-chart path[data-payoff]').count()==1
        assert page.locator('#option-underlying-chart path[data-series]').count()==3
        assert 'LC' in page.locator('#option-detail-title').inner_text()
        page.screenshot(path=str(output/'options-lithium.png'),full_page=False)
        page.locator('#min-vol').fill('100000000');page.locator('#apply-options').click()
        page.wait_for_function('document.querySelector("#apply-options").disabled === false')
        assert page.locator('#option-rows tr[data-option]').count()==0
        page.locator('#min-vol').fill('100');page.locator('#apply-options').click();page.wait_for_selector('#option-rows tr[data-option]')
        for target in ['http://127.0.0.1:8765/','http://127.0.0.1:8765/research.html','http://127.0.0.1:8765/options.html?asof=20260911&code=LC.GFE']:
            page.set_viewport_size({'width':390,'height':844});page.goto(target,wait_until='networkidle');page.wait_for_timeout(100)
            assert not page.evaluate('document.documentElement.scrollWidth > innerWidth'),target
        page.screenshot(path=str(output/'options-mobile.png'),full_page=True)
        assert not errors,errors
        print('Research browser passed: phases, phase-filter run archive, 10 real events, missing historical OI, async reload, 11 actual option puts, exact underlying, reference IV, payoff, all-page mobile; no runtime errors')
        browser.close()

if __name__=='__main__':main()
