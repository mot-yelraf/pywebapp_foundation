"""Verify the example in bundled headless Chromium at desktop and mobile widths.

A temporary local server and data directory are always cleaned up. The same script
runs on the host and in CI; screenshots are optional via --output-dir.
"""

import argparse
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

from playwright.sync_api import expect, sync_playwright


def verify(origin: str, output_dir: Path | None) -> None:
    """Exercise settings, focus, mobile layout, jobs, history, and unsafe text rendering."""
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(origin)
            expect(
                page.get_by_role("heading", name="A home for your Python tools.")
            ).to_be_visible()
            page.get_by_role("button", name="Graph", exact=True).click()
            expect(page.get_by_role("dialog", name="Graphum")).to_be_visible()
            expect(page.locator(".graph-empty")).to_have_text("No graph data available yet.")
            page.evaluate("""() => PWAF.graph.setSeries(Array.from({length: 5}, (_, i) => ({
                id: `metric${i}`, label: i === 0 ? '<script>unsafe</script>' : `Metric ${i}`,
                unit: 'ms', points: [{x: Date.now() - 60000, y: 0},
                                    {x: Date.now() - 30000, y: null}, {x: Date.now(), y: i + 1}]
            })))""")
            expect(page.locator(".graph-plot svg")).to_have_count(1)
            expect(page.locator(".graph-plot h4")).to_have_text("<script>unsafe</script> (ms)")
            assert page.locator("#graph-dialog script").count() == 0
            for index in range(1, 5):
                page.get_by_role("checkbox", name=f"Metric {index}").click()
            expect(page.locator(".graph-plot svg")).to_have_count(4)
            expect(page.locator("#graph-status")).to_have_text("Select at most four metrics.")
            page.get_by_role("button", name="1hr", exact=True).click()
            expect(page.locator("#graph-range-title")).to_have_text("Last 1 hour")
            expect(page.get_by_role("button", name="1hr", exact=True)).to_have_attribute(
                "aria-pressed", "true"
            )
            expect(page.get_by_role("button", name="24hr", exact=True)).to_have_attribute(
                "aria-pressed", "false"
            )
            if output_dir:
                output_dir.mkdir(parents=True, exist_ok=True)
                page.screenshot(path=str(output_dir / "graphum-desktop.png"))
            page.keyboard.press("Escape")
            expect(page.get_by_role("button", name="Graph", exact=True)).to_be_focused()
            page.get_by_role("button", name="Settings", exact=True).click()
            expect(page.get_by_label("App Name")).to_be_enabled()
            page.get_by_label("App Name").fill("<script>alert('unsafe')</script>")
            page.get_by_role("button", name="Save general").click()
            expect(page.locator("#pane-general .form-status")).to_have_text("Saved.")
            page.get_by_role("tab", name="Performance", exact=True).click()
            page.get_by_label("Default iterations").fill("1")
            page.get_by_role("button", name="Save performance").click()
            expect(page.locator("#pane-performance .form-status")).to_have_text("Saved.")
            page.get_by_role("tab", name="General", exact=True).click()
            page.get_by_label("Theme").select_option("dark")
            expect(page.locator("html")).to_have_attribute("data-theme", "dark")
            page.keyboard.press("Escape")
            expect(page.get_by_role("dialog")).not_to_be_visible()
            expect(page.locator("html")).to_have_attribute("data-theme", "light")
            expect(page.get_by_role("button", name="Settings", exact=True)).to_be_focused()
            page.reload()
            expect(page.locator("[data-app-name]")).to_have_text("<script>alert('unsafe')</script>")
            assert page.locator("script:not([src])").count() == 0
            page.get_by_role("button", name="Settings", exact=True).click()
            expect(page.get_by_label("App Name")).to_be_enabled()
            page.get_by_label("App Name").fill("Performance Lab")
            page.get_by_role("button", name="Save general").click()
            expect(page.locator("#pane-general .form-status")).to_have_text("Saved.")
            # Failed save remains visible and leaves the user's input intact.
            page.route(
                "**/api/settings/panes/general",
                lambda route: route.fulfill(
                    status=500,
                    content_type="application/json",
                    body=json.dumps({"error": {"message": "Storage unavailable."}}),
                ),
            )
            page.get_by_label("App Name").fill("Unsaved")
            page.get_by_role("button", name="Save general").click()
            expect(page.locator("#pane-general .form-status")).to_have_text("Storage unavailable.")
            expect(page.get_by_label("App Name")).to_have_value("Unsaved")
            page.unroute("**/api/settings/panes/general")
            general = page.get_by_role("tab", name="General", exact=True)
            general.focus()
            page.keyboard.press("ArrowDown")
            expect(page.get_by_role("tab", name="Performance", exact=True)).to_be_focused()
            expect(page.locator("#pane-performance")).to_be_visible()
            page.get_by_role("button", name="Close settings").click()
            page.get_by_role("link", name="Performance", exact=True).click()
            about = page.get_by_role("button", name="About this benchmark", exact=True)
            about.click()
            expect(page.get_by_role("dialog", name="About this benchmark")).to_be_visible()
            page.get_by_role("button", name="Close About this benchmark").click()
            expect(about).to_be_focused()
            expect(page.get_by_label("Iterations", exact=True)).to_have_value("1")
            expect(page.locator("#saved-count")).to_have_text("0")
            page.get_by_role("button", name="Run benchmark").click()
            expect(page.locator("#job-heading")).to_have_text("Run complete.", timeout=15000)
            expect(page.locator("#saved-count")).to_have_text("1")
            expect(page.locator("#history-rows tr")).to_have_count(1)
            # Reload resumes no finished job; successful results are still present.
            page.reload()
            expect(page.locator("#saved-count")).to_have_text("1")
            page.get_by_label("Iterations", exact=True).fill("5000000")
            page.get_by_role("button", name="Run benchmark").click()
            expect(page.get_by_role("button", name="Cancel", exact=True)).to_be_enabled()
            page.get_by_role("button", name="Cancel", exact=True).click()
            expect(page.locator("#job-heading")).to_have_text("Run cancelled.", timeout=15000)
            expect(page.locator("#saved-count")).to_have_text("1")
            page.get_by_label("Iterations", exact=True).fill("100000")
            if output_dir:
                page.screenshot(path=str(output_dir / "performance-desktop.png"), full_page=True)
            # A saved zero measurement and tool text must render literally, not as markup.
            page.route(
                "**/api/results?*",
                lambda route: route.fulfill(
                    content_type="application/json",
                    body=json.dumps(
                        {
                            "items": [
                                {
                                    "recorded_at": "2026-09-21T12:00:00.000000Z",
                                    "iterations": 1,
                                    "elapsed_ms": 0,
                                    "checksum": "<img onerror=alert(1)>",
                                }
                            ],
                            "total": 11,
                            "offset": 0,
                            "limit": 10,
                        }
                    ),
                ),
            )
            page.get_by_role("button", name="Refresh", exact=True).click()
            expect(page.locator("#latest-duration")).to_have_text("0 ms")
            expect(page.locator("#history-rows img")).to_have_count(0)
            expect(page.locator("#history-rows .checksum")).to_have_text("<img onerror")
            page.get_by_role("button", name="Next", exact=True).click()
            expect(page.locator("#page-label")).to_have_text("Page 2")
            page.get_by_role("button", name="Previous", exact=True).click()
            expect(page.locator("#page-label")).to_have_text("Page 1")
            page.unroute("**/api/results?*")
            # A stale job from a previous process must not appear to keep running.
            page.evaluate("sessionStorage.setItem('pwaf-job', 'expired')")
            page.reload()
            expect(page.locator("#job-heading")).to_have_text("Run status unavailable.")
            for width, height in ((390, 844), (320, 700)):
                page.set_viewport_size({"width": width, "height": height})
                expect(page.get_by_role("navigation")).not_to_be_visible()
                page.get_by_role("button", name="Menu", exact=True).click()
                expect(page.get_by_role("navigation")).to_be_visible()
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                page.evaluate("""() => PWAF.graph.setSeries([{id: 'sample',
                    label: 'Execution time', unit: 'ms', points: [
                        {x: Date.now() - 3600000, y: 0}, {x: Date.now(), y: 12}]}])""")
                page.get_by_role("button", name="Graph", exact=True).click()
                expect(page.get_by_role("dialog", name="Graphum")).to_be_visible()
                assert page.locator("#graph-dialog").evaluate(
                    "el => el.scrollWidth <= el.clientWidth"
                )
                if output_dir:
                    page.screenshot(path=str(output_dir / f"graphum-{width}.png"))
                page.get_by_role("button", name="Close Graphum").click()
                expect(page.get_by_role("button", name="Graph", exact=True)).to_be_focused()
                page.get_by_role("button", name="Settings", exact=True).click()
                expect(page.get_by_label("App Name")).to_be_enabled()
                expect(page.get_by_label("App Name")).to_have_value("Performance Lab")
                assert page.locator("#settings-dialog").evaluate(
                    "el => el.scrollWidth <= el.clientWidth"
                )
                page.keyboard.press("Escape")
                page.get_by_role("button", name="Menu", exact=True).click()
                if output_dir and width == 390:
                    page.screenshot(path=str(output_dir / "performance-mobile.png"), full_page=True)
            assert not errors, errors
            page.close()
            print(
                "Playwright passed: desktop/mobile, settings, focus, theme, "
                "jobs, history, safe text."
            )
        finally:
            browser.close()


def main() -> None:
    """Start an isolated server, verify it, and stop it on every exit path."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    if args.output_dir:
        args.output_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="pwaf-browser-") as directory:
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        origin = f"http://127.0.0.1:{port}"
        env = {
            **os.environ,
            "PWAF_HTTP_HOST": "127.0.0.1",
            "PWAF_HTTP_PORT": str(port),
            "PWAF_DATA_DIR": directory,
            "PWAF_LOG_LEVEL": "WARNING",
        }
        # A file avoids filling a PIPE while the browser exercises many requests.
        with tempfile.TemporaryFile(mode="w+") as log:
            process = subprocess.Popen(
                [sys.executable, "-c", """
from dataclasses import replace
import uvicorn
from app.app import create_app
from app.example import example_options
from pwaf_foundation.config import RuntimeConfig
config = RuntimeConfig.from_env()
options = example_options()
options['ui'] = replace(options['ui'], graph_enabled=True)
uvicorn.run(create_app(config, **options), host=config.host, port=config.port,
            log_level=config.log_level.lower(), proxy_headers=False)
"""],
                env=env,
                cwd=Path(__file__).resolve().parents[1],
                stdout=log,
                stderr=subprocess.STDOUT,
            )
            try:
                for _ in range(100):
                    try:
                        with urllib.request.urlopen(origin + "/healthz", timeout=1) as response:
                            if response.status == 200:
                                break
                    except urllib.error.URLError:
                        if process.poll() is not None:
                            log.seek(0)
                            raise RuntimeError(log.read()) from None
                        time.sleep(0.1)
                else:
                    raise RuntimeError("Server readiness timed out")
                verify(origin, args.output_dir)
            finally:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()


if __name__ == "__main__":
    main()
