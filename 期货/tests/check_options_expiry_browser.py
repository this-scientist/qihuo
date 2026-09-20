"""Browser acceptance for simplified option scanner and option detail pages."""
from pathlib import Path
from playwright.sync_api import sync_playwright


def main():
    output=Path(__file__).parents[1]/'output/playwright'
    output.mkdir(parents=True,exist_ok=True)
    with sync_playwright() as p:
        browser=p.chromium.launch(channel='msedge',headless=True)
        page=browser.new_page(viewport={'width':1440,'height':1000})
        errors=[]
        page.on('pageerror',lambda error:errors.append(str(error)))

        page.goto('http://127.0.0.1:8765/scanner.html?asof=20260911',wait_until='networkidle')
        assert page.locator('h1').inner_text()=='期权候选验证'
        assert page.locator('.workflow-link').count()>=1
        assert page.locator('#advanced-radars').is_hidden()
        assert page.locator('#dir-long').is_visible()
        assert page.locator('#dir-short').is_visible()
        assert page.locator('#dir-structure').is_visible()
        assert page.locator('#dir-radar').is_hidden()
        assert page.locator('#dir-extended').is_hidden()
        page.wait_for_selector('#scan-rows tr[data-code]')
        page.locator('#scan-rows tr[data-code]').first.click()
        assert page.locator('#tb-summary').inner_text().find('10倍潜力')>=0
        assert page.locator('#tb-rows tr').count()>=1
        assert page.locator('#contract-rows tr').count()>=1
        assert page.locator('#detail-option-link').get_attribute('href').find('/options.html')>=0

        page.goto('http://127.0.0.1:8765/options.html?asof=20260911',wait_until='networkidle')
        assert page.locator('h1').inner_text()=='期权明细'
        assert page.locator('#core-option-controls').is_visible()
        assert page.locator('#advanced-option-controls').is_hidden()
        assert page.locator('#min-days').input_value()=='0'
        assert page.locator('#max-days').input_value()=='10'
        assert page.locator('table').filter(has=page.locator('#option-rows')).locator('thead th').count()==8
        assert page.locator('#option-error').inner_text()==''
        page.wait_for_selector('#option-rows tr[data-option]')
        for value in page.locator('#option-rows tr[data-option] td:nth-child(4)').all_text_contents():
            assert 0<=int(value)<=10
        assert page.locator('#tradability-panel').inner_text().find('Gamma/Delta')>=0
        assert page.locator('#tradability-panel').inner_text().find('IV贵贱')>=0
        assert page.locator('#option-underlying-chart path[data-series]').count()>=1
        assert page.locator('#payoff-chart path[data-payoff]').count()==1

        page.locator('#advanced-option-summary').click()
        assert page.locator('#advanced-option-controls').is_visible()
        page.locator('[data-days="11,30"]').click()
        page.wait_for_function("!document.querySelector('#apply-options').disabled")
        page.wait_for_selector('#option-rows tr[data-option]')
        for value in page.locator('#option-rows tr[data-option] td:nth-child(4)').all_text_contents():
            assert 11<=int(value)<=30
        page.locator('#option-rows tr[data-option]').nth(1).click()
        page.wait_for_selector('#option-underlying-chart path[data-series]')
        assert page.locator('#option-detail-title').inner_text()==page.locator('#option-rows tr[data-option]').nth(1).get_attribute('data-option')
        page.locator('#min-days').fill('1000')
        page.locator('#max-days').fill('1001')
        page.locator('#apply-options').click()
        page.wait_for_function("!document.querySelector('#apply-options').disabled")
        assert page.locator('#option-rows tr[data-option]').count()==0
        assert page.locator('#option-detail').is_hidden()

        page.set_viewport_size({'width':390,'height':844})
        assert not page.evaluate('document.documentElement.scrollWidth > innerWidth')
        page.screenshot(path=str(output/'options-simplified-mobile.png'),full_page=True)
        assert not errors,errors
        browser.close()
        print('PASS: simplified scanner, simplified option detail, scores, Greeks, IV, payoff, range filtering, mobile, no JS errors')


if __name__=='__main__':
    main()
