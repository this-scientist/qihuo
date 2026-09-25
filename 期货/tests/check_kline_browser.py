"""Focused browser acceptance check for the interactive commodity K-line modal."""
from pathlib import Path
from playwright.sync_api import sync_playwright


def main():
    output = Path(__file__).parents[1] / 'output/playwright'
    output.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(channel='msedge', headless=True)
        page = browser.new_page(viewport={'width': 1440, 'height': 960})
        page.set_default_timeout(3000)
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.goto('http://127.0.0.1:8765', wait_until='networkidle', timeout=15000)
        page.locator('.decision-table tbody tr[data-code]').first.click()
        page.locator('button[data-open-kline]').click()
        modal = page.locator('#kline-modal[open]')
        assert modal.count() == 1
        assert modal.locator('[data-volume-bar]').count() > 10
        assert modal.locator('path[data-open-interest]').count() == 1
        assert modal.locator('[data-price-level="support"]').count() >= 1
        assert modal.locator('[data-price-level="resistance"]').count() >= 1
        support_line = modal.locator('[data-level-line="support"]')
        resistance_line = modal.locator('[data-level-line="resistance"]')
        assert support_line.get_attribute('stroke') == '#21835d'
        assert resistance_line.get_attribute('stroke') == '#c43f3f'
        assert support_line.get_attribute('stroke-dasharray')
        assert resistance_line.get_attribute('stroke-dasharray')

        before = modal.locator('[data-candle]').count()
        modal.locator('.kline-chart-surface').hover()
        page.mouse.wheel(0, -500)
        page.wait_for_timeout(80)
        assert modal.locator('[data-candle]').count() < before
        chart_svg = modal.locator('.kline-svg')
        visible_start = chart_svg.get_attribute('data-visible-start')
        overlay = modal.locator('[data-kline-overlay]')
        overlay_box = overlay.bounding_box()
        page.mouse.move(overlay_box['x'] + overlay_box['width'] / 2, overlay_box['y'] + 80)
        page.mouse.down()
        page.mouse.move(overlay_box['x'] + overlay_box['width'] / 2 + 180, overlay_box['y'] + 80, steps=4)
        page.mouse.up()
        assert chart_svg.get_attribute('data-visible-start') != visible_start

        support = modal.locator('[data-price-level="support"]').first
        label = modal.locator('[data-level-label="support"]').first
        legend = modal.locator('[data-level-legend="support"]')
        original = label.text_content()
        original_legend = legend.text_content()
        box = support.bounding_box()
        page.mouse.move(box['x'] + box['width'] / 2, box['y'] + box['height'] / 2)
        page.mouse.down()
        page.mouse.move(box['x'] + box['width'] / 2, box['y'] - 24)
        page.mouse.up()
        assert label.text_content() != original
        assert legend.text_content() != original_legend
        modal.locator('[data-reset-levels]').click()
        assert label.text_content() == original
        assert legend.text_content() == original_legend

        page.screenshot(path=str(output / 'kline-modal-desktop.png'), full_page=False)
        page.set_viewport_size({'width': 390, 'height': 844})
        page.wait_for_timeout(100)
        assert not page.evaluate('document.documentElement.scrollWidth > window.innerWidth')
        page.screenshot(path=str(output / 'kline-modal-mobile.png'), full_page=False)
        modal.locator('[data-close-kline]').click()
        assert page.locator('#kline-modal[open]').count() == 0
        assert not errors, errors
        browser.close()
        print('K-line modal acceptance passed: volume/OI, zoom, editable levels, reset, close')


if __name__ == '__main__':
    main()
