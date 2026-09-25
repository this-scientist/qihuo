"""Focused browser acceptance check for concrete commodity homepage reminders."""
from pathlib import Path
from playwright.sync_api import sync_playwright


def main():
    output = Path(__file__).parents[1] / 'output/playwright'
    output.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(channel='msedge', headless=True)
        page = browser.new_page(viewport={'width': 1440, 'height': 960})
        page.goto('http://127.0.0.1:8765', wait_until='networkidle', timeout=15000)
        reminders = page.locator('.opportunity-risk')
        assert reminders.count() > 0
        assert '等待后续商品信号确认' not in '\n'.join(reminders.all_inner_texts())
        sections = page.locator('[data-opportunity-section]')
        assert sections.count() == 4
        for index in range(sections.count()):
            section = sections.nth(index)
            total = int(section.locator('.queue-count').inner_text())
            assert section.locator('.opportunity-card').count() == total
            assert section.evaluate('(node) => node.open') is True
        focus = page.locator('[data-opportunity-section="focus"]')
        focus.locator('summary').click()
        assert focus.evaluate('(node) => node.open') is False
        focus.locator('summary').click()
        assert focus.evaluate('(node) => node.open') is True
        first = reminders.first
        visible = first.locator('.opportunity-risk-reasons p')
        assert 1 <= visible.count() <= 2
        full = first.get_attribute('title')
        assert full
        for reason in visible.all_inner_texts():
            assert reason in full
        assert not any(word in full for word in ['期权量仓', '单张期权', '期权不推荐'])
        page.screenshot(path=str(output / 'commodity-reminders.png'), full_page=False)
        browser.close()
        print('Commodity reminders passed: concrete visible reasons, full hover detail, no option leakage')


if __name__ == '__main__':
    main()
