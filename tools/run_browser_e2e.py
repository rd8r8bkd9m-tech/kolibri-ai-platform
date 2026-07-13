#!/usr/bin/env python3
from __future__ import annotations

import base64
import contextlib
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.request

import httpx
from playwright.sync_api import Page, sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "var" / "e2e-v2.1"
SCREENSHOTS = EVIDENCE / "screenshots"
DOWNLOADS = EVIDENCE / "downloads"
API_PORT = 8191
API_URL = f"http://127.0.0.1:{API_PORT}"


def _port_free(port: int) -> bool:
    with socket.socket() as sock:
        return sock.connect_ex(("127.0.0.1", port)) != 0


def _wait_json(url: str, timeout: float = 30.0) -> dict:
    deadline = time.time() + timeout
    last: Exception | None = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1) as response:
                if response.status == 200:
                    return json.loads(response.read())
        except Exception as exc:  # noqa: BLE001
            last = exc
        time.sleep(0.15)
    raise RuntimeError(f"Timed out waiting for {url}: {last}")


def _terminate(process: subprocess.Popen[str] | None) -> None:
    if process is None or process.poll() is not None:
        return
    with contextlib.suppress(ProcessLookupError):
        os.killpg(process.pid, signal.SIGTERM)
    try:
        process.wait(timeout=8)
    except subprocess.TimeoutExpired:
        with contextlib.suppress(ProcessLookupError):
            os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=5)


def _production_html() -> str:
    dist = ROOT / "apps" / "shell" / "dist"
    index = (dist / "index.html").read_text(encoding="utf-8")
    css_match = re.search(r'href="(/assets/[^"]+\.css)"', index)
    js_match = re.search(r'src="(/assets/[^"]+\.js)"', index)
    if not css_match or not js_match:
        raise RuntimeError("Could not locate production CSS/JS assets")
    css = (dist / css_match.group(1).lstrip("/")).read_text(encoding="utf-8")
    js = (dist / js_match.group(1).lstrip("/")).read_text(encoding="utf-8")
    bird = (dist / "kolibri-bird.svg").read_bytes()
    bird_uri = "data:image/svg+xml;base64," + base64.b64encode(bird).decode("ascii")
    js = js.replace("/kolibri-bird.svg", bird_uri).replace("</script", "<\\/script")
    bridge = r'''
<script>
(() => {
  const nativeFetch = window.fetch.bind(window);
  function bytesFromBase64(value) {
    const binary = atob(value || '');
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
    return bytes;
  }
  window.fetch = async (input, init = {}) => {
    const request = input instanceof Request ? input : null;
    const path = typeof input === 'string' ? input : request?.url || String(input);
    if (path.startsWith('/v1') || path.startsWith('/api')) {
      const headers = {};
      if (request) request.headers.forEach((value, key) => { headers[key] = value; });
      new Headers(init.headers || {}).forEach((value, key) => { headers[key] = value; });
      let body = init.body ?? null;
      if (body !== null && typeof body !== 'string') {
        if (body instanceof URLSearchParams) body = body.toString();
        else throw new Error('Unsupported E2E bridge request body');
      }
      const result = await window.__kolibriHttp({
        method: init.method || request?.method || 'GET',
        path,
        headers,
        body,
      });
      return new Response(bytesFromBase64(result.body_b64), {
        status: result.status,
        headers: result.headers,
      });
    }
    return nativeFetch(input, init);
  };
})();
</script>
'''
    return (
        "<!doctype html><html lang='ru'><head><meta charset='UTF-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1,viewport-fit=cover'>"
        f"<style>{css}</style></head><body><div id='root'></div>{bridge}"
        f"<script type='module'>{js}</script></body></html>"
    )


def _mount(page: Page, html: str) -> None:
    page.set_content(html, wait_until="domcontentloaded", timeout=30_000)
    page.wait_for_selector("#composer", timeout=20_000)


def main() -> int:
    if not _port_free(API_PORT):
        raise SystemExit(f"Port {API_PORT} must be free before browser E2E")

    shutil.rmtree(EVIDENCE, ignore_errors=True)
    SCREENSHOTS.mkdir(parents=True, exist_ok=True)
    DOWNLOADS.mkdir(parents=True, exist_ok=True)
    logs = EVIDENCE / "logs"
    logs.mkdir()

    api_env = os.environ.copy()
    api_env.update(
        {
            "PYTHONPATH": str(ROOT / "services" / "api-gateway"),
            "KOLIBRI_ENV": "test",
            "KOLIBRI_DATA_DIR": str(EVIDENCE / "data"),
            "KOLIBRI_DB_PATH": str(EVIDENCE / "data" / "kolibri.db"),
            "KOLIBRI_ARTIFACT_DIR": str(EVIDENCE / "data" / "artifacts"),
            "KOLIBRI_SESSION_SECRET": "e2e-session-secret-change-isolated",
            "KOLIBRI_ALLOWED_ORIGINS": "http://e2e.invalid",
        }
    )

    api_log = (logs / "api.log").open("w", encoding="utf-8")
    api: subprocess.Popen[str] | None = None
    report: dict = {
        "status": "running",
        "api_url": API_URL,
        "bundle_mode": "production-assets-inline-with-real-http-bridge",
        "checks": [],
        "console_errors": [],
        "page_errors": [],
        "screenshots": [],
    }

    try:
        api = subprocess.Popen(
            [str(ROOT / ".venv" / "bin" / "python"), "-m", "uvicorn", "main:app", "--app-dir", "services/api-gateway", "--host", "127.0.0.1", "--port", str(API_PORT)],
            cwd=ROOT,
            env=api_env,
            stdout=api_log,
            stderr=subprocess.STDOUT,
            text=True,
            start_new_session=True,
        )
        readiness = _wait_json(f"{API_URL}/ready")
        if readiness.get("status") != "ready":
            raise AssertionError(readiness)
        report["checks"].append("api.readiness")

        html = _production_html()
        report["checks"].append("production_bundle.loaded")
        with httpx.Client(base_url=API_URL, timeout=30.0, follow_redirects=True) as api_client:
            def bridge(payload: dict) -> dict:
                response = api_client.request(
                    payload.get("method", "GET"),
                    payload["path"],
                    headers=payload.get("headers") or {},
                    content=payload.get("body"),
                )
                return {
                    "status": response.status_code,
                    "headers": dict(response.headers),
                    "body_b64": base64.b64encode(response.content).decode("ascii"),
                }

            with sync_playwright() as playwright:
                chromium_path = os.environ.get("KOLIBRI_CHROMIUM_PATH") or shutil.which("chromium") or shutil.which("chromium-browser")
                launch_options = {
                    "headless": True,
                    "args": ["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
                }
                if chromium_path:
                    launch_options["executable_path"] = chromium_path
                browser = playwright.chromium.launch(**launch_options)
                context = browser.new_context(
                    viewport={"width": 1440, "height": 960},
                    locale="ru-RU",
                    accept_downloads=True,
                )
                page = context.new_page()
                page.expose_function("__kolibriHttp", bridge)
                page.on("console", lambda message: report["console_errors"].append(message.text) if message.type == "error" else None)
                page.on("pageerror", lambda error: report["page_errors"].append(str(error)))

                started = time.perf_counter()
                _mount(page, html)
                report["first_ui_ms"] = round((time.perf_counter() - started) * 1000, 1)
                expect(page.locator(".bird")).to_have_count(1)
                expect(page.get_by_role("heading", name="Что создадим?")).to_be_visible()
                home = SCREENSHOTS / "01_home_desktop.png"
                page.screenshot(path=str(home), full_page=True)
                report["screenshots"].append(str(home.relative_to(ROOT)))
                report["checks"].extend(["shell.single_entry", "shell.single_bird"])

                page.get_by_role("button", name="Сделай смету на ремонт квартиры 72 м²").click()
                page.get_by_role("button", name="Отправить").click()
                page.wait_for_selector('[data-testid="estimate-canvas"]', timeout=20_000)
                expect(page.locator(".status")).to_contain_text("Нужны данные")
                report["checks"].append("response.opens_contextual_estimate")

                page.get_by_role("button", name="Добавить строку").click()
                page.get_by_label("Работа").fill("Шпатлёвка и грунт")
                page.get_by_label("Работа").press("Tab")
                page.wait_for_timeout(220)
                page.get_by_label("Единица").fill("м²")
                page.get_by_label("Единица").press("Tab")
                page.wait_for_timeout(220)
                page.get_by_label("Количество").fill("180")
                page.get_by_label("Количество").press("Tab")
                page.wait_for_timeout(260)
                page.get_by_label("Цена").fill("420")
                page.get_by_label("Цена").press("Tab")
                expect(page.locator(".status")).to_contain_text("Предварительно", timeout=10_000)
                expect(page.locator(".estimate-status-row strong")).to_contain_text("75")
                preliminary = SCREENSHOTS / "02_estimate_preliminary_desktop.png"
                page.screenshot(path=str(preliminary), full_page=True)
                report["screenshots"].append(str(preliminary.relative_to(ROOT)))
                report["checks"].append("estimate.server_calculation_preliminary")

                source_inputs = page.locator(".source-form input")
                source_inputs.nth(0).fill("Прайс поставщика · Москва")
                source_inputs.nth(1).fill("https://example.com/prices/moscow")
                source_inputs.nth(2).fill("Москва")
                page.get_by_role("button", name="Сохранить и привязать").click()
                expect(page.locator(".status")).to_contain_text("Проверено", timeout=10_000)
                verified = SCREENSHOTS / "03_estimate_verified_desktop.png"
                page.screenshot(path=str(verified), full_page=True)
                report["screenshots"].append(str(verified.relative_to(ROOT)))
                report["checks"].append("estimate.source_backed_verified")

                page.get_by_role("button", name="Сформировать PDF и XLSX").click()
                page.wait_for_selector('[data-testid="documents-canvas"]', timeout=20_000)
                expect(page.locator(".artifact-list article")).to_have_count(5)
                docs = SCREENSHOTS / "04_documents_desktop.png"
                page.screenshot(path=str(docs), full_page=True)
                report["screenshots"].append(str(docs.relative_to(ROOT)))
                report["checks"].append("documents.materialized")

                pdf_href = page.locator(".artifact-list article").filter(has_text="application/pdf").get_by_role("link", name="Скачать").get_attribute("href")
                if not pdf_href:
                    raise AssertionError("PDF download link missing")
                pdf_response = api_client.get(pdf_href)
                pdf_response.raise_for_status()
                pdf_path = DOWNLOADS / "Коммерческое предложение.pdf"
                pdf_path.write_bytes(pdf_response.content)
                payload = pdf_response.content
                if not payload.startswith(b"%PDF-"):
                    raise AssertionError("Downloaded artifact is not a real PDF")
                report["downloaded_pdf"] = {
                    "path": str(pdf_path.relative_to(ROOT)),
                    "bytes": len(payload),
                    "sha256": hashlib.sha256(payload).hexdigest(),
                }
                report["checks"].append("documents.real_pdf_download")

                page.set_content("<html><body></body></html>")
                _mount(page, html)
                page.get_by_role("button", name="Инструменты").click()
                page.get_by_role("button", name="Смета", exact=True).click()
                page.wait_for_selector('[data-testid="estimate-canvas"]', timeout=10_000)
                expect(page.locator(".status")).to_contain_text("Проверено")
                assistant_messages = page.locator(".message--assistant")
                if assistant_messages.count() != 1:
                    raise AssertionError(f"Expected one assistant message after reload, got {assistant_messages.count()}")
                report["checks"].extend(["workspace.reload_restore", "responses.no_duplicate_assistant"])

                page.set_viewport_size({"width": 390, "height": 844})
                page.wait_for_timeout(300)
                overflow = page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
                if overflow > 1:
                    raise AssertionError(f"Mobile horizontal overflow: {overflow}px")
                table_overflow = page.evaluate("(() => { const el=document.querySelector('.estimate-table'); return el ? el.scrollWidth-el.clientWidth : 0 })()")
                if table_overflow > 1:
                    raise AssertionError(f"Mobile estimate overflow: {table_overflow}px")
                mobile = SCREENSHOTS / "05_estimate_mobile.png"
                page.screenshot(path=str(mobile), full_page=True)
                report["screenshots"].append(str(mobile.relative_to(ROOT)))
                report["checks"].append("mobile.no_horizontal_overflow")

                if report["console_errors"]:
                    raise AssertionError(f"Browser console errors: {report['console_errors']}")
                if report["page_errors"]:
                    raise AssertionError(f"Browser page errors: {report['page_errors']}")
                report["checks"].extend(["browser.console_errors_zero", "browser.page_errors_zero"])
                context.close()
                browser.close()

        report["status"] = "passed"
        (EVIDENCE / "e2e-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"ok: browser E2E passed ({len(report['checks'])} checks)")
        return 0
    except Exception as exc:  # noqa: BLE001
        report["status"] = "failed"
        report["error"] = f"{type(exc).__name__}: {exc}"
        (EVIDENCE / "e2e-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(report["error"], file=sys.stderr)
        return 1
    finally:
        _terminate(api)
        api_log.close()


if __name__ == "__main__":
    raise SystemExit(main())
