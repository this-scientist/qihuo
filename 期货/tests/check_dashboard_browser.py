"""One-off browser acceptance check for the 7-view trading dashboard."""
from pathlib import Path
from playwright.sync_api import sync_playwright


def main():
    output=Path(__file__).parents[1]/'output/playwright'
    output.mkdir(parents=True,exist_ok=True)
    with sync_playwright() as p:
        browser=p.chromium.launch(channel='msedge',headless=True)
        page=browser.new_page(viewport={'width':1500,'height':1000},device_scale_factor=1)
        errors=[]
        page.on('pageerror',lambda error:errors.append(str(error)))
        page.goto('http://127.0.0.1:8765',wait_until='networkidle')
        page.evaluate('localStorage.clear()')
        page.reload(wait_until='networkidle')

        assert page.locator('.top-tabs button').count()==7
        assert page.locator('.radar-stats .metric-card').count()==5
        page.wait_for_selector('.decision-table tbody tr[data-code]')
        assert page.locator('.decision-table tbody tr[data-code]').count()>20
        assert '启动信号数' in page.locator('.radar-stats').inner_text()
        assert page.locator('.term-tip[title*="方向分"]').count()>=1
        table_text=page.locator('.decision-table thead').inner_text()
        for raw in ['DIR','START','VOL RPS']:
            assert raw not in table_text
        assert '期权动作' in table_text
        first_row_text=page.locator('.decision-table tbody tr[data-code]').first.inner_text()
        assert any(label in first_row_text for label in ['买认购','买认沽','不做'])
        assert page.locator('#chart path[data-series]').count()>=1

        page.locator('.top-tabs button[data-view="candidates"]').click()
        assert page.locator('.candidate-tabs button').count()==3
        page.locator('.candidate-tabs button[data-candidate-tab="PREPARE"]').click()
        assert page.locator('.candidate-tabs button:has-text("准备观察")').count()==1

        page.locator('.decision-table tbody tr[data-code]').first.click()
        assert '商品详情' in page.locator('.page-hero h1').inner_text()
        assert page.locator('#single-chart path[data-series]').count()>=1
        assert page.locator('.timeframe-tabs span').count()==4

        page.locator('button[data-jump-options]').click()
        assert '期权 T 型报价' in page.locator('.page-hero h1').inner_text()
        page.wait_for_selector('.t-chain table')
        assert page.locator('.mode-tabs button').count()==3
        option_head=page.locator('.t-chain thead').inner_text()
        assert '认购' in option_head and '行权价' in option_head and '认沽' in option_head
        assert page.locator('.t-chain .term-tip[title*="Delta"]').count()>=1

        page.locator('.top-tabs button[data-view="positions"]').click()
        assert '持仓监控' in page.locator('.page-hero h1').inner_text()
        assert page.locator('.position-card').count()>=1
        pos_text=page.locator('.position-card').first.inner_text()
        assert '正常持有' in pos_text or '正在转弱' in pos_text or '逻辑失效' in pos_text

        page.locator('.top-tabs button[data-view="alerts"]').click()
        assert '预警中心' in page.locator('.page-hero h1').inner_text()
        assert page.locator('.alert-row').count()>=1

        page.locator('.top-tabs button[data-view="review"]').click()
        assert '复盘 / 系统设置' in page.locator('.page-hero h1').inner_text()
        assert page.locator('.settings-list input').count()>=2

        page.screenshot(path=str(output/'overview-7views-desktop.png'),full_page=False)
        page.set_viewport_size({'width':390,'height':844})
        page.wait_for_timeout(150)
        overflow=page.evaluate('document.documentElement.scrollWidth > window.innerWidth')
        assert not overflow,'Unexpected mobile overflow'
        page.screenshot(path=str(output/'overview-7views-mobile.png'),full_page=True)

        assert not errors,errors
        browser.close()
        print('Browser acceptance passed: 7 views, market KPIs, candidates, detail, options, positions, alerts, review, mobile; no runtime errors')


if __name__=='__main__':
    main()
