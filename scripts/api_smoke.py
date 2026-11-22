"""Unauthenticated API and resource smoke test for a running deployment."""
import os
import urllib.request
import urllib.error
base = os.environ.get("VERIFLOW_UI_URL", "http://127.0.0.1:8000").rstrip("/")
for path in ("/api/health", "/", "/app.js", "/style.css"):
    with urllib.request.urlopen(base + path, timeout=10) as resp:
        assert resp.status == 200, (path, resp.status)
        print("PASS", path, resp.status)
try:
    urllib.request.urlopen(base + "/api/projects", timeout=10)
    raise AssertionError("匿名用户意外获得项目列表")
except urllib.error.HTTPError as error:
    assert error.code == 401, f"预期401，得到{error.code}"
    print("PASS /api/projects -> 401 (未登录被拒绝)")
