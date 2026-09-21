"""Verify direct LAN browsing and optional real Caddy authentication over HTTPS.

All listeners and credentials are temporary. No system trust store is modified.
Pass --caddy with a separately installed Caddy executable for the proxy check.
"""

import argparse
import base64
import json
import os
import secrets
import socket
import ssl
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from contextlib import ExitStack
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]


def free_port() -> int:
    """Choose a free loopback port for a temporary test listener."""
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


def request(url, *, headers=None, payload=None, context=None):
    """Return status/body including expected authentication failures."""
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode() if payload is not None else None,
        headers=headers or {},
    )
    try:
        with urllib.request.urlopen(req, context=context, timeout=3) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as exc:
        with exc:
            return exc.code, exc.read()


def stop(process):
    """Stop a temporary child and bound cleanup waiting."""
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


def start(stack, command, env):
    """Start a managed process with a file-backed log."""
    log = stack.enter_context(tempfile.TemporaryFile(mode="w+"))
    process = subprocess.Popen(command, env=env, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
    stack.callback(stop, process)
    return process


def wait_http(url, headers):
    """Wait for a server socket even when its authentication rejects the probe."""
    for _ in range(100):
        try:
            request(url, headers=headers)
            return
        except urllib.error.URLError:
            time.sleep(0.1)
    raise RuntimeError("Listener did not start")


def verify_direct(root, stack):
    """Use an insecure HTTP LAN hostname to exercise browser APIs without a login."""
    port = free_port()
    origin = f"http://pwaf.test:{port}"
    env = {key: value for key, value in os.environ.items() if not key.startswith("PWAF_")}
    env.update(
        PWAF_MODE="lan",
        PWAF_HTTP_HOST="127.0.0.1",
        PWAF_HTTP_PORT=str(port),
        PWAF_PUBLIC_ORIGIN=origin,
        PWAF_DATA_DIR=str(root / "direct"),
    )
    start(stack, [sys.executable, "-m", "app"], env)
    wait_http(f"http://127.0.0.1:{port}/healthz", {"Host": f"pwaf.test:{port}"})
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            args=["--host-resolver-rules=MAP pwaf.test 127.0.0.1", "--no-proxy-server"]
        )
        try:
            page = browser.new_page()
            page.goto(origin + "/performance")
            assert page.evaluate("window.isSecureContext") is False
            page.get_by_label("Iterations", exact=True).fill("1")
            page.get_by_role("button", name="Run benchmark").click()
            expect(page.locator("#job-heading")).to_have_text("Run complete.", timeout=15000)
            expect(page.locator("#saved-count")).to_have_text("1")
        finally:
            browser.close()
    print("Direct LAN HTTP verified without password authentication.")


def verify_proxy(root, stack, caddy):
    """Run the documented proxy with TLS trust scoped only to this test client."""
    port, tls_port = free_port(), free_port()
    origin = f"https://localhost:{tls_port}"
    token = secrets.token_hex(32)
    password = secrets.token_urlsafe(24)
    token_file = root / "token"
    token_file.write_text(token)
    token_file.chmod(0o600)
    hashed = subprocess.check_output(
        [str(caddy), "hash-password", "--plaintext", password], text=True
    ).strip()
    env = {key: value for key, value in os.environ.items() if not key.startswith("PWAF_")}
    env.update(
        PWAF_MODE="lan",
        PWAF_LAN_AUTH="proxy",
        PWAF_HTTP_PORT=str(port),
        PWAF_PUBLIC_ORIGIN=origin,
        PWAF_PROXY_TOKEN_FILE=str(token_file),
        PWAF_LAN_USERS="operator,viewer",
        PWAF_LAN_OPERATORS="operator",
        PWAF_DATA_DIR=str(root / "proxy-app"),
        PWAF_PROXY_TOKEN=token,
        PWAF_OPERATOR_HASH=hashed,
        PWAF_VIEWER_HASH=hashed,
        XDG_DATA_HOME=str(root / "caddy-data"),
        XDG_CONFIG_HOME=str(root / "caddy-config"),
    )
    start(stack, [sys.executable, "-m", "app"], env)
    upstream = f"http://127.0.0.1:{port}"
    wait_http(upstream + "/healthz", {"Host": f"localhost:{tls_port}"})
    assert (
        request(
            upstream + "/api/csrf",
            headers={"Host": f"localhost:{tls_port}", "X-PWAF-User": "operator"},
        )[0]
        == 401
    )
    start(
        stack,
        [str(caddy), "run", "--config", str(ROOT / "deploy/Caddyfile"), "--adapter", "caddyfile"],
        env,
    )
    certificate = root / "caddy-data/caddy/pki/authorities/local/root.crt"
    for _ in range(150):
        if certificate.exists():
            break
        time.sleep(0.1)
    context = ssl.create_default_context(cafile=str(certificate))
    for _ in range(100):
        try:
            assert request(origin + "/api/csrf", context=context)[0] == 401
            break
        except urllib.error.URLError:
            time.sleep(0.1)
    else:
        raise RuntimeError("HTTPS listener did not start")

    def auth(user, pw):
        return "Basic " + base64.b64encode(f"{user}:{pw}".encode()).decode()

    assert (
        request(
            origin + "/", headers={"Authorization": auth("operator", "wrong")}, context=context
        )[0]
        == 401
    )
    valid = {"Authorization": auth("operator", password)}
    code, body = request(origin + "/api/csrf", headers=valid, context=context)
    assert code == 200, (code, body.decode())
    csrf = json.loads(body)["csrf_token"]
    mutation = {
        **valid,
        "Origin": origin,
        "X-CSRF-Token": csrf,
        "Content-Type": "application/json",
        "Idempotency-Key": "tls",
    }
    payload = {"operation": "performance", "parameters": {"iterations": 1}}
    code, body = request(origin + "/api/jobs", headers=mutation, payload=payload, context=context)
    assert code == 202
    location = json.loads(body)["status_url"]
    for _ in range(100):
        record = json.loads(request(origin + location, headers=valid, context=context)[1])
        if record["status"] in ("succeeded", "failed"):
            break
        time.sleep(0.1)
    assert record["status"] == "succeeded"
    forged = {
        **mutation,
        "Authorization": auth("viewer", password),
        "X-PWAF-User": "operator",
        "X-PWAF-Proxy-Token": "forged",
    }
    assert request(origin + "/api/jobs", headers=forged, payload=payload, context=context)[0] == 403
    print(
        "Optional Caddy HTTPS verified: bad credentials, direct bypass, "
        "forged identity, operator execution."
    )


def main():
    """Run isolated direct and optional authenticated LAN deployment checks."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--caddy", type=Path)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="pwaf-lan-") as directory, ExitStack() as stack:
        root = Path(directory)
        verify_direct(root, stack)
        if args.caddy:
            verify_proxy(root, stack, args.caddy)


if __name__ == "__main__":
    main()
