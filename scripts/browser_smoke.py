"""Interactive browser smoke test for a running VeriFlow installation.

Requires: pip install playwright && python -m playwright install chromium
Example:
VERIFLOW_UI_URL=http://127.0.0.1:8000 VERIFLOW_UI_EMAIL=<account> \
  VERIFLOW_UI_PASSWORD=<password> python scripts/browser_smoke.py
Only use test accounts and synthetic data. Screenshots exclude passwords.
"""
import os
from pathlib import Path
from playwright.sync_api import sync_playwright

base = os.environ["VERIFLOW_UI_URL"].rstrip("/")
email = os.environ["VERIFLOW_UI_EMAIL"]
password = os.environ["VERIFLOW_UI_PASSWORD"]
out = Path(os.environ.get("VERIFLOW_SCREENSHOT_DIR", "./test-artifacts"))
out.mkdir(parents=True, exist_ok=True)
with sync_playwright() as p:
    launch_args={"headless": True}
    if os.getenv("VERIFLOW_CHROMIUM_PATH"):
        launch_args.update(executable_path=os.environ["VERIFLOW_CHROMIUM_PATH"], args=["--no-sandbox"])
    browser = p.chromium.launch(**launch_args)
    page = browser.new_page(viewport={"width": 1400, "height": 900}, accept_downloads=True)
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(base, wait_until="domcontentloaded")
    page.get_by_role("heading", name="欢迎使用 VeriFlow").wait_for(timeout=15000)
    page.locator("#email").fill(email)
    page.locator("#pass").fill(password)
    page.get_by_role("button", name="登录工作台").click()
    page.locator("#nav").get_by_role("button", name="总览").wait_for(timeout=15000)
    page.get_by_role("heading", name="质量总览").wait_for(timeout=15000)
    page.screenshot(path=str(out / "dashboard.png"), full_page=True)
    for label in ("问题工单", "数据质量", "UAT验收", "上线审批"):
        page.locator("#nav").get_by_role("button", name=label).click()
        page.locator("#app h1").wait_for(timeout=15000)
        page.screenshot(path=str(out / f"{label}.png"), full_page=True)
    if errors:
        raise AssertionError("浏览器JS错误：" + "; ".join(errors))
    print("PASS: 登录、总览、工单、数据质量、UAT及审批导航；JS pageerror=0")
    browser.close()
