"""Verify the complete example and independent UI extension contracts.

A temporary second application exercises overrides without editing foundation code.
"""

import json
import subprocess
import sys
import time

import pytest
from fastapi import APIRouter, Request
from fastapi.testclient import TestClient

from app.app import create_app, create_example_app
from app.cli import main
from app.services.performance import PerformanceInput, benchmark
from app.services.results import ResultRepository
from pwaf_foundation.config import RuntimeConfig
from pwaf_foundation.database import Migration
from pwaf_foundation.settings import FoundationSettings
from pwaf_foundation.ui import NavigationItem, SettingsPane, UIConfig, render_page

BASE = "http://127.0.0.1:8191"


def headers(client, key="test"):
    return {
        "Origin": BASE,
        "X-CSRF-Token": client.get("/api/csrf").json()["csrf_token"],
        "Idempotency-Key": key,
    }


def await_job(client, job_id):
    for _ in range(300):
        record = client.get(f"/api/jobs/{job_id}").json()
        if record["status"] in {"succeeded", "failed", "cancelled"}:
            return record
        time.sleep(0.01)
    raise AssertionError("Job did not finish")


def test_example_cli_web_and_restart(tmp_path, capsys):
    app = create_example_app(RuntimeConfig(data_dir=tmp_path))
    with TestClient(app, base_url=BASE) as client:
        assert client.get("/performance").status_code == 200
        assert client.get("/static/app/performance.js").status_code == 200
        assert client.get("/static/foundation/foundation.css").status_code == 200
        assert client.get("/api/results").json()["total"] == 0
        response = client.post(
            "/api/jobs",
            json={"operation": "performance", "parameters": {"iterations": 1}},
            headers=headers(client),
        )
        assert response.status_code == 202
        assert response.headers["location"] == response.json()["status_url"]
        job_id = response.json()["id"]
        record = await_job(client, job_id)
        assert record["status"] == "succeeded"
        result = record["result"]
        main(["--iterations", "1"])
        cli = json.loads(capsys.readouterr().out)
        assert cli.keys() == result.keys()
        assert cli["checksum"] == result["checksum"]
        assert cli["iterations"] == result["iterations"] == 1
        assert (
            client.post(
                "/api/jobs",
                json={"operation": "performance", "parameters": {"iterations": 1}},
                headers=headers(client),
            ).json()["id"]
            == job_id
        )
        assert client.post(f"/api/jobs/{job_id}/cancel", headers=headers(client)).status_code == 409
        pane = client.patch(
            "/api/settings/panes/performance",
            json={"default_iterations": 42},
            headers=headers(client),
        )
        assert pane.json()["default_iterations"] == 42
        assert (
            client.patch(
                "/api/settings/panes/performance",
                json={"app_name": "wrong"},
                headers=headers(client),
            ).status_code
            == 422
        )
        assert (
            client.patch(
                "/api/settings/panes/missing", json={}, headers=headers(client)
            ).status_code
            == 404
        )
        assert client.get("/api/results?limit=0").status_code == 422
        assert client.post("/api/jobs", json={"operation": "performance"}).status_code == 403
        assert (
            client.post(
                "/api/jobs",
                json={"operation": "performance", "parameters": {"iterations": 0}},
                headers=headers(client, "bad"),
            ).status_code
            == 422
        )
        assert client.get("/api/jobs/absent").status_code == 404
    with TestClient(app, base_url=BASE) as client:
        assert client.get(f"/api/jobs/{job_id}").status_code == 404
        saved = client.get("/api/results").json()
        assert saved["total"] == 1
        assert saved["items"][0]["checksum"] == result["checksum"]
        assert client.get("/api/settings").json()["default_iterations"] == 42
        repository = ResultRepository(app.state.database)
        for index in range(12):
            repository.save(
                f"history-{index}", {"iterations": 1, "elapsed_ms": 0, "checksum": "safe"}
            )
        page = client.get("/api/results?offset=10&limit=10").json()
        assert page["total"] == 13 and len(page["items"]) == 3
        with pytest.raises(ValueError):
            repository.history(limit=101)


def test_running_job_keeps_endpoints_responsive_and_cancels(tmp_path):
    app = create_example_app(RuntimeConfig(data_dir=tmp_path))
    with TestClient(app, base_url=BASE) as client:
        job = client.post(
            "/api/jobs",
            json={"operation": "performance", "parameters": {"iterations": 5000000}},
            headers=headers(client),
        ).json()
        assert client.get("/healthz").status_code == 200
        assert client.get("/api/settings").status_code == 200
        assert (
            client.post(f"/api/jobs/{job['id']}/cancel", headers=headers(client)).status_code == 202
        )
        assert await_job(client, job["id"])["status"] == "cancelled"
        assert client.get("/api/results").json()["total"] == 0


def test_cli_validation_and_checkpoint(capsys):
    with pytest.raises(SystemExit):
        main(["--iterations", "0"])
    assert "between 1 and 5000000" in capsys.readouterr().err
    progress = []
    result = benchmark(PerformanceInput(iterations=1), progress=progress.append)
    assert progress == [0, 1] and result.elapsed_ms >= 0
    process = subprocess.run(
        [sys.executable, "-m", "app.cli", "--iterations", "1"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert json.loads(process.stdout)["checksum"] == result.checksum


def test_second_app_overrides_navigation_panes_assets_and_migrations(tmp_path):
    class OtherSettings(FoundationSettings):
        count: int = 0

    templates, assets = tmp_path / "templates", tmp_path / "assets"
    templates.mkdir()
    assets.mkdir()
    (templates / "base.html").write_text(
        "<title>Custom base</title>{% block content %}{% endblock %}"
    )
    (templates / "other.html").write_text(
        "{% extends 'base.html' %}{% block content %}Value: {{ settings.count }}{% endblock %}"
    )
    (assets / "custom.css").write_text("body {color: teal}")
    router = APIRouter()

    @router.get("/other")
    async def other(request: Request):
        return await render_page(request, "other.html")

    app = create_app(
        RuntimeConfig(data_dir=tmp_path / "data"),
        settings_schema=OtherSettings,
        migrations={"other": [Migration(1, ("CREATE TABLE other (value INTEGER)",))]},
        routers=[router],
        ui=UIConfig(
            template_dir=templates,
            static_dir=assets,
            navigation=(NavigationItem("Other", "/other"),),
            settings_panes=(SettingsPane("other", "Other", ("count",)),),
        ),
    )
    with TestClient(app, base_url=BASE) as client:
        assert client.get("/other").text == "<title>Custom base</title>Value: 0"
        assert client.get("/static/app/custom.css").status_code == 200
        assert (
            client.patch(
                "/api/settings/panes/other", json={"count": 2}, headers=headers(client)
            ).json()["count"]
            == 2
        )
        assert client.get("/api/jobs/anything").status_code == 404
        assert app.state.ui.navigation[0].path == "/other"
        with app.state.database.transaction(read_only=True) as connection:
            assert connection.execute("SELECT * FROM other").fetchall() == []


def test_invalid_ui_configuration(tmp_path):
    with pytest.raises(ValueError):
        NavigationItem("Remote", "//evil.example")
    with pytest.raises(ValueError):
        SettingsPane("invalid-key", "Invalid", ())
    for pane in (
        SettingsPane("general", "Duplicate", ()),
        SettingsPane("other", "Overlap", ("app_name",)),
        SettingsPane("other", "Missing", ("missing",)),
    ):
        with pytest.raises(ValueError):
            create_app(RuntimeConfig(data_dir=tmp_path), ui=UIConfig(settings_panes=(pane,)))
