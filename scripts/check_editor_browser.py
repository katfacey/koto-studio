"""Exercise real editor panel resizing in Chromium against an isolated backend."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from koto.runtime import runtime_environment


def main():
    from playwright.sync_api import sync_playwright
    output = ROOT / "runtime" / "validation"
    output.mkdir(parents=True, exist_ok=True)
    url = "http://127.0.0.1:18765"
    with tempfile.TemporaryDirectory(prefix="KOTO browser project ") as tmp:
        env = runtime_environment()
        env.update({"KOTO_DATA_DIR": tmp, "PYTHONPATH": str(ROOT / "backend"), "PLAYWRIGHT_BROWSERS_PATH": str(ROOT / "runtime/cache/playwright")})
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = env["PLAYWRIGHT_BROWSERS_PATH"]
        with (output / "browser-server.log").open("w", encoding="utf-8") as log:
            server = subprocess.Popen([sys.executable, "-m", "uvicorn", "koto.app:app", "--host", "127.0.0.1", "--port", "18765"], cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
            try:
                opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
                for _ in range(100):
                    if server.poll() is not None:
                        raise RuntimeError((output / "browser-server.log").read_text(encoding="utf-8"))
                    try:
                        with opener.open(url + "/api/health", timeout=1) as response:
                            if json.load(response).get("local"):
                                break
                    except OSError:
                        pass
                    time.sleep(.2)
                else:
                    raise RuntimeError("Browser test backend did not start")
                errors = []
                with sync_playwright() as p:
                    browser = p.chromium.launch(headless=True)
                    page = browser.new_page(viewport={"width": 1600, "height": 1000})
                    page.on("pageerror", lambda error: errors.append(str(error)))
                    page.goto(url, wait_until="networkidle")
                    page.locator('.app-shell').wait_for()
                    assert page.locator('[data-panel-resize]').count() == 4
                    def dimension(selector, prop):
                        return page.locator(selector).bounding_box()[prop]
                    def drag(kind, dx, dy):
                        box = page.locator(f'[data-panel-resize="{kind}"]').bounding_box()
                        x, y = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
                        page.mouse.move(x, y)
                        page.mouse.down()
                        page.mouse.move(x + dx, y + dy, steps=8)
                        page.mouse.up()
                    left = dimension('.left-panel', 'width')
                    right = dimension('.right-panel', 'width')
                    timeline = dimension('.timeline-panel', 'height')
                    dialogue = dimension('.dialogue-editor', 'height')
                    drag('left', 60, 0)
                    assert abs(dimension('.left-panel', 'width') - left - 60) < 2
                    drag('right', -40, 0)
                    assert abs(dimension('.right-panel', 'width') - right - 40) < 2
                    drag('timeline', 0, -40)
                    assert abs(dimension('.timeline-panel', 'height') - timeline - 40) < 2
                    drag('dialogue', 0, -25)
                    assert abs(dimension('.dialogue-editor', 'height') - dialogue - 25) < 2
                    page.reload(wait_until='networkidle')
                    page.locator('.app-shell').wait_for()
                    assert abs(dimension('.left-panel', 'width') - left - 60) < 2
                    handle = page.locator('[data-panel-resize="left"]')
                    handle.focus()
                    page.keyboard.press('ArrowRight')
                    assert abs(dimension('.left-panel', 'width') - left - 70) < 2
                    handle.dblclick()
                    assert abs(dimension('.left-panel', 'width') - left) < 2
                    page.evaluate('document.fonts.ready')
                    page.screenshot(path=str(output / 'koto-editor.png'), full_page=True)
                    # The queue data below is an explicit UI fixture; no inference is simulated.
                    fixture = [{"id": "ui-fixture", "kind": "prepare", "status": "running", "progress": .5, "message": "UI fixture progress", "result": {}}]
                    page.route('**/api/projects/*/jobs', lambda route: route.fulfill(json=fixture))
                    page.reload(wait_until='networkidle')
                    page.locator('.queue-summary [data-act="cancel"]').wait_for()
                    cancel = page.locator('.queue-summary [data-act="cancel"] svg path')
                    assert cancel.get_attribute('d') == 'm6 6 12 12M6 18 18 6'
                    assert not errors, errors
                    browser.close()
                print('Real Chromium checks passed: four panel drags, persistence, keyboard resize, reset, and Cancel X.')
            finally:
                if server.poll() is None:
                    server.terminate()
                    try:
                        server.wait(timeout=15)
                    except subprocess.TimeoutExpired:
                        server.kill()
                        server.wait(timeout=5)


if __name__ == "__main__":
    main()
