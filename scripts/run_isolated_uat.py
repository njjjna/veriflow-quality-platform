"""Run API/Chromium UAT with separate disposable demo databases, without Docker.

python scripts/run_isolated_uat.py --suite all
Browser suite requires Playwright and its Chromium installation.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
import uuid

ROOT = Path(__file__).resolve().parents[1]


def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def run_suite(suite, output):
    with tempfile.TemporaryDirectory(prefix=f'veriflow-{suite}-') as temporary:
        temp = Path(temporary)
        port = free_port()
        env = os.environ.copy()
        env.update(
            DATABASE_URL='sqlite:///' + (temp / 'demo.db').as_posix(),
            VERIFLOW_MODE='demo', COOKIE_SECURE='false',
            ALLOWED_ORIGIN=f'http://127.0.0.1:{port}',
            VERIFLOW_UPLOAD_DIR=str(temp / 'uploads'),
            VERIFLOW_UI_URL=f'http://127.0.0.1:{port}',
            VERIFLOW_UI_EMAIL='isolated-admin@demo.invalid',
            VERIFLOW_UI_PASSWORD=secrets.token_urlsafe(30),
            VERIFLOW_SCREENSHOT_DIR=str(output),
            VERIFLOW_API_REPORT=str(output / 'api_uat.md'), PYTHONUNBUFFERED='1',
        )
        bootstrap = subprocess.run(
            [sys.executable, '-m', 'app.bootstrap', '--email', env['VERIFLOW_UI_EMAIL']],
            input=(env['VERIFLOW_UI_PASSWORD'] + '\n') * 2,
            text=True, capture_output=True, cwd=ROOT, env=env,
        )
        if bootstrap.returncode:
            raise RuntimeError(f'{suite} bootstrap failed; no browser assertions ran')
        with (output / f'{suite}_server.log').open('w', encoding='utf-8') as log:
            server = subprocess.Popen(
                [sys.executable, '-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', str(port)],
                cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT,
            )
            try:
                for _ in range(100):
                    if server.poll() is not None:
                        raise RuntimeError(f'{suite} server exited before becoming healthy')
                    try:
                        with urllib.request.urlopen(env['VERIFLOW_UI_URL'] + '/api/health', timeout=1) as response:
                            health = json.load(response)
                            if health['status'] == 'ok' and health['mode'] == 'demo': break
                    except (OSError, ValueError):
                        time.sleep(0.1)
                else:
                    raise RuntimeError(f'{suite} server health timeout')
                scripts = ['api_smoke.py', 'live_api_uat.py'] if suite == 'api' else ['browser_uat.py']
                for script in scripts:
                    result = subprocess.run(
                        [sys.executable, str(ROOT / 'scripts' / script)],
                        cwd=ROOT, env=env, text=True, stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT, timeout=600,
                    )
                    (output / f'{Path(script).stem}.log').write_text(result.stdout, encoding='utf-8')
                    print(result.stdout, end='')
                    if result.returncode:
                        raise RuntimeError(f'{script} failed (exit {result.returncode})')
            finally:
                server.terminate()
                try: server.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    server.kill()
                    server.wait()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--suite', choices=['api', 'browser', 'all'], default='all')
    parser.add_argument('--output', type=Path, default=ROOT / 'test-artifacts' / 'isolated')
    args = parser.parse_args()
    output = args.output.resolve() / (time.strftime('%Y%m%dT%H%M%SZ', time.gmtime()) + '-' + uuid.uuid4().hex[:8])
    output.mkdir(parents=True, exist_ok=True)
    summary = {'api': 'not_run', 'browser': 'not_run'}
    selected = ['api', 'browser'] if args.suite == 'all' else [args.suite]
    try:
        for suite in selected:
            suite_output = output / suite
            suite_output.mkdir(exist_ok=True)
            for filename in ['browser_automatic_uat.md', 'browser_result.json', 'api_uat.md']:
                (suite_output / filename).unlink(missing_ok=True)
            summary[suite] = 'running'
            try: run_suite(suite, suite_output)
            except Exception:
                summary[suite] = 'failed'
                raise
            summary[suite] = 'passed'
    finally:
        (output / 'run_summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    print(json.dumps(summary))
    print('Artifacts:', output)


if __name__ == '__main__': main()
