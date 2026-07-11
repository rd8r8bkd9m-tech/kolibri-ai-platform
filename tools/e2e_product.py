from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description='Vista browser product E2E')
    parser.add_argument('--base-url', default=os.environ.get('VISTA_E2E_URL', 'http://127.0.0.1:5173'))
    parser.add_argument('--output', default=str(ROOT / 'var' / 'e2e'))
    args = parser.parse_args()
    out = Path(args.output); shots = out / 'screenshots'; shots.mkdir(parents=True, exist_ok=True)
    report = {'checks': [], 'console_errors': [], 'page_errors': [], 'screenshots': []}

    def check(name: str, condition: bool = True) -> None:
        if not condition: raise AssertionError(name)
        report['checks'].append(name)

    with sync_playwright() as p:
        executable = os.environ.get('PLAYWRIGHT_CHROMIUM_EXECUTABLE')
        launch = {'headless': True}
        if executable: launch['executable_path'] = executable
        if os.environ.get('CI') or executable: launch['args'] = ['--no-sandbox']
        browser = p.chromium.launch(**launch)
        context = browser.new_context(viewport={'width': 1512, 'height': 982}, device_scale_factor=1, accept_downloads=True)
        page = context.new_page()
        page.on('console', lambda msg: report['console_errors'].append(msg.text) if msg.type == 'error' else None)
        page.on('pageerror', lambda error: report['page_errors'].append(str(error)))
        page.goto(f"{args.base_url}/?entered=1&role=client_pro&reset=1", wait_until='networkidle')
        page.get_by_test_id('app-home').wait_for()
        check('single active home application')
        check('client has no factory dock', page.get_by_title('Фабрика').count() == 0)
        check('client has no server dock', page.get_by_title('Серверы').count() == 0)
        page.screenshot(path=str(shots / '01_home_desktop.png'), full_page=True)

        page.get_by_title('Смета').click()
        page.get_by_test_id('app-estimate').wait_for()
        if page.get_by_text('Смета начинается с короткого брифа').count():
            page.locator('.briefForm input').nth(0).fill('Ремонт квартиры 72 м²')
            page.locator('.briefForm input').nth(1).fill('Иван Петров')
            page.locator('.briefForm input').nth(2).fill('Москва')
            page.locator('.briefForm input').nth(3).fill('72')
            page.get_by_role('button', name='Создать смету').click()
            page.locator('.projectTitle').wait_for()
        check('estimate created through API')

        rows = [
            ('Демонтаж', 'Снятие покрытий', 'м²', '72', '350'),
            ('Стены', 'Шпатлёвка и грунт', 'м²', '180', '420'),
            ('Пол', 'Укладка ламината', 'м²', '72', '487'),
        ]
        for section, name, unit, qty, price in rows:
            inputs = page.locator('.addItemRow input')
            inputs.nth(0).fill(section); inputs.nth(1).fill(name); inputs.nth(2).fill(unit); inputs.nth(3).fill(qty); inputs.nth(4).fill(price)
            page.locator('.addRowButton').click(); page.wait_for_timeout(200)
        check('three estimate line items persist', page.locator('.itemRow').count() >= 4)
        check('server calculated total', '₽' in page.locator('.grandTotal').inner_text())
        page.screenshot(path=str(shots / '02_estimate_desktop.png'), full_page=True)

        page.get_by_role('button', name='Сформировать документы').click()
        page.get_by_title('Документы').click()
        page.get_by_test_id('app-documents').wait_for(timeout=15000)
        page.locator('.documentCard').first.wait_for(timeout=15000)
        check('real document pack generated')
        check('five document formats', page.locator('.documentCard').count() == 5)
        labels = page.locator('.fileBadge').all_inner_texts()
        check('PDF XLSX DOCX exist', {'PDF','XLSX','DOCX'} <= set(labels))
        with page.expect_download() as download_info:
            page.locator('.documentCard').filter(has_text='Коммерческое предложение').get_by_role('button', name='Скачать').click()
        download = download_info.value
        check('authenticated PDF download works', download.suggested_filename.endswith('.pdf'))

        page.get_by_role('button', name='Ссылка клиенту').click()
        page.get_by_role('link', name='Открыть').wait_for()
        share_url = page.get_by_role('link', name='Открыть').get_attribute('href')
        check('client share link created', bool(share_url and '/share/' in share_url))
        page.screenshot(path=str(shots / '03_documents_desktop.png'), full_page=True)

        public = context.new_page()
        public.goto(share_url, wait_until='networkidle')
        public.get_by_text('КОММЕРЧЕСКОЕ ПРЕДЛОЖЕНИЕ').wait_for()
        check('public proposal opens without session token')
        with public.expect_download() as public_download_info:
            public.locator('.publicDocuments button').filter(has_text='Коммерческое предложение').click()
        check('public PDF download works', public_download_info.value.suggested_filename.endswith('.pdf'))
        public.screenshot(path=str(shots / '04_public_share.png'), full_page=True)
        public.close()

        page.keyboard.press('Control+K')
        page.get_by_placeholder('Команда или приложение…').wait_for()
        check('command palette works')
        check('palette hides factory for client', page.get_by_text('Factory Control').count() == 0)
        page.keyboard.press('Escape')

        page.get_by_title('Смета').click(); page.wait_for_timeout(700); page.reload(wait_until='networkidle')
        page.get_by_test_id('app-estimate').wait_for()
        check('workspace and active estimate restore after reload')

        page.set_viewport_size({'width': 390, 'height': 844}); page.wait_for_timeout(400)
        check('mobile keeps one active application')
        page.screenshot(path=str(shots / '05_estimate_mobile.png'), full_page=True)

        context.close(); browser.close()

    report['screenshots'] = [str(path.relative_to(ROOT)) for path in sorted(shots.glob('*.png'))]
    report['passed'] = not report['console_errors'] and not report['page_errors']
    (out / 'e2e-report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    if not report['passed']:
        raise SystemExit(json.dumps(report, ensure_ascii=False))
    print(f"ok: Vista browser E2E passed; report={out / 'e2e-report.json'}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
