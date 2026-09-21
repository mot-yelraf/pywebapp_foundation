"""Exercise HTTP boundaries and the real application lifespan.

TestClient uses the configured local authority; no production server is started.
"""

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi import APIRouter, HTTPException
from fastapi.testclient import TestClient
from pydantic import Field

from app.app import create_app
from pwaf_foundation.config import RuntimeConfig
from pwaf_foundation.database import Migration
from pwaf_foundation.health import ReadinessCheck
from pwaf_foundation.settings import FoundationSettings

BASE = "http://127.0.0.1:8191"


@pytest.fixture
def application(tmp_path):
    return create_app(RuntimeConfig(data_dir=tmp_path / "data"))


@pytest.fixture
def client(application):
    with TestClient(application, base_url=BASE, raise_server_exceptions=False) as browser:
        yield browser


def mutation_headers(client):
    return {"Origin": BASE, "X-CSRF-Token": client.get("/api/csrf").json()["csrf_token"]}


def test_lifecycle_and_readiness(application):
    directory = application.state.config.data_dir
    assert not directory.exists()
    assert not application.state.started
    with TestClient(application, base_url=BASE) as browser:
        token = browser.get("/api/csrf").json()["csrf_token"]
        assert browser.get("/healthz").json() == {"status": "ready", "checks": {"database": True}}
        assert application.state.started
    assert not application.state.started
    assert not application.state.csrf_token
    with TestClient(application, base_url=BASE) as browser:
        assert browser.get("/api/csrf").json()["csrf_token"] != token
        application.state.started = False
        assert browser.get("/healthz").status_code == 503


def test_landing_page_and_settings(client, application):
    assert "Python Web App" in client.get("/").text
    headers = mutation_headers(client)
    updated = client.patch(
        "/api/settings", json={"app_name": "<script>tool</script>"}, headers=headers
    )
    assert updated.status_code == 200
    assert "&lt;script&gt;" in client.get("/").text
    assert "<script>tool" not in client.get("/").text
    path = application.state.config.data_dir / "settings.json"
    assert json.loads(path.read_text())["app_name"] == "<script>tool</script>"
    assert client.get("/api/settings").json() == updated.json()
    for body in ({"app_name": ""}, {"unknown": 1}, {"app_name": None}):
        response = client.patch("/api/settings", json=body, headers=headers)
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "validation_error"
    assert "cache-control" in updated.headers
    assert "access-control-allow-origin" not in updated.headers


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Origin": BASE},
        {"Origin": "https://evil.example", "X-CSRF-Token": "bad"},
        {"Origin": "null"},
        {"Origin": "http://127.0.0.1:9999"},
    ],
)
def test_csrf_rejections(client, headers):
    response = client.patch("/api/settings", json={"app_name": "changed"}, headers=headers)
    assert response.status_code == 403
    assert client.get("/api/settings").json()["app_name"] == "Python Web App"


def test_host_and_origin_validation(client):
    for host in ("evil.example", "localhost.evil.example:8191", "127.0.0.1:9999"):
        response = client.get("/api/csrf", headers={"Host": host})
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "invalid_host"
    assert client.get("/api/csrf", headers={"Host": "localhost:8191"}).status_code == 200
    headers = mutation_headers(client)
    headers["Origin"] = "http://localhost:8191"
    assert client.patch("/api/settings", json={}, headers=headers).status_code == 200
    assert (
        client.patch(
            "/api/settings",
            json={},
            headers=[("Origin", BASE), ("Origin", BASE), ("X-CSRF-Token", headers["X-CSRF-Token"])],
        ).status_code
        == 403
    )


def test_error_contract_and_openapi(client):
    headers = mutation_headers(client)
    malformed = client.patch(
        "/api/settings", content="{", headers={**headers, "Content-Type": "application/json"}
    )
    assert malformed.status_code == 400
    assert client.patch("/api/settings", json=[], headers=headers).status_code == 422
    assert client.get("/api/missing").json()["error"]["code"] == "not_found"
    method = client.post("/api/settings", json={}, headers=headers)
    assert method.status_code == 405
    assert "allow" in method.headers
    schema = client.get("/openapi.json").json()
    assert "ErrorResponse" in schema["components"]["schemas"]
    assert "422" in schema["paths"]["/api/settings"]["patch"]["responses"]
    assert client.get("/docs").status_code == 200


def test_errors_do_not_leak(tmp_path):
    router = APIRouter()

    @router.get("/api/crash")
    def crash():
        raise RuntimeError("private-path-and-secret")

    @router.get("/api/denied")
    def denied():
        raise HTTPException(403, "private-path-and-secret")

    app = create_app(RuntimeConfig(data_dir=tmp_path), routers=[router])
    with TestClient(app, base_url=BASE, raise_server_exceptions=False) as client:
        for path, status in (("/api/crash", 500), ("/api/denied", 403)):
            response = client.get(path)
            assert response.status_code == status
            assert "private-path-and-secret" not in response.text


def test_extensible_application(tmp_path):
    class CustomSettings(FoundationSettings):
        retries: int = Field(default=2, ge=0)

    async def working():
        return True

    app = create_app(
        RuntimeConfig(data_dir=tmp_path),
        settings_schema=CustomSettings,
        migrations={"custom": [Migration(1, ("CREATE TABLE example (value TEXT)",))]},
        readiness_checks=[ReadinessCheck("custom", working)],
    )
    with TestClient(app, base_url=BASE) as client:
        assert client.get("/api/settings").json()["retries"] == 2
        assert (
            client.patch(
                "/api/settings", json={"retries": 0}, headers=mutation_headers(client)
            ).json()["retries"]
            == 0
        )
        assert client.get("/healthz").json()["checks"]["custom"]


def test_readiness_failures(tmp_path):
    cancelled = []

    async def stuck():
        try:
            await asyncio.sleep(10)
        finally:
            cancelled.append(True)

    async def broken():
        raise RuntimeError("private failure")

    app = create_app(
        RuntimeConfig(data_dir=tmp_path),
        readiness_checks=[
            ReadinessCheck("slow", stuck, timeout=0.01),
            ReadinessCheck("broken", broken),
        ],
    )
    with TestClient(app, base_url=BASE) as client:
        response = client.get("/healthz")
        assert response.status_code == 503
        assert response.json()["checks"] == {"database": True, "slow": False, "broken": False}
        assert "private failure" not in response.text
    assert cancelled


def test_startup_failure_cleanup(tmp_path):
    (tmp_path / "settings.json").write_text("broken")
    app = create_app(RuntimeConfig(data_dir=tmp_path))
    with pytest.raises(RuntimeError), TestClient(app, base_url=BASE):
        pass
    assert not app.state.started
    assert app.state.csrf_token == ""
    assert not (tmp_path / "app.sqlite3").exists()


def test_invalid_extension_registration(tmp_path):
    config = RuntimeConfig(data_dir=tmp_path)

    async def ready():
        return True

    check = ReadinessCheck("test", ready)
    for options in (
        {"migrations": {"foundation": []}},
        {"readiness_checks": [check, check]},
        {"readiness_checks": [ReadinessCheck("database", ready)]},
    ):
        with pytest.raises(ValueError):
            create_app(config, **options)
    with pytest.raises(ValueError):
        ReadinessCheck("", ready)


def test_imports_are_inert(tmp_path):
    root = str(Path(__file__).resolve().parents[1])
    result = subprocess.run(
        [sys.executable, "-c", "import app.app; import app.__main__; app.app.create_app()"],
        cwd=tmp_path,
        env={**os.environ, "PYTHONPATH": root, "PWAF_DATA_DIR": str(tmp_path / "data")},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert not (tmp_path / "data").exists()


def test_entrypoint(monkeypatch, tmp_path):
    from app.__main__ import main

    monkeypatch.setenv("PWAF_DATA_DIR", str(tmp_path))
    captured = {}

    def run(app, **kwargs):
        captured.update(kwargs)

    monkeypatch.setattr("app.__main__.uvicorn.run", run)
    main()
    assert captured["workers"] == 1
    assert captured["proxy_headers"] is False
    monkeypatch.setenv("PWAF_HTTP_PORT", "invalid")
    with pytest.raises(SystemExit, match="PWAF_HTTP_PORT"):
        main()


def test_settings_patch_schema(client):
    schema = client.get("/openapi.json").json()
    body = schema["paths"]["/api/settings"]["patch"]["requestBody"]
    name = body["content"]["application/json"]["schema"]["$ref"].split("/")[-1]
    patch = schema["components"]["schemas"][name]
    assert not patch.get("required")
    assert patch["properties"]["app_name"]["maxLength"] == 100
    assert patch["additionalProperties"] is False


def test_settings_write_error_contract(client, application, monkeypatch):
    def fail(document):
        raise OSError("private storage path")

    monkeypatch.setattr(application.state.settings, "_save", fail)
    response = client.patch(
        "/api/settings", json={"app_name": "new"}, headers=mutation_headers(client)
    )
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "settings_write_failed"
    assert "private storage path" not in response.text
    assert client.get("/api/settings").json()["app_name"] == "Python Web App"


@pytest.mark.parametrize('enabled', [False, True])
def test_graphum_is_an_explicit_application_option(tmp_path, enabled):
    from pwaf_foundation.ui import UIConfig

    ui = UIConfig(graph_enabled=True) if enabled else UIConfig()
    app = create_app(RuntimeConfig(data_dir=tmp_path), ui=ui)
    with TestClient(app, base_url=BASE) as browser:
        page = browser.get('/').text
        for marker in ('id="open-graph"', 'id="graph-dialog"', '/graph.js'):
            assert (marker in page) is enabled
        assert 'id="open-settings"' in page
        assert browser.get('/static/foundation/icons/dashboard-graph.svg').status_code == 200
