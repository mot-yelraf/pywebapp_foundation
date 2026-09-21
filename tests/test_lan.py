"""Verify direct LAN access and opt-in trusted proxy authentication.

Test requests simulate peer addresses; real Caddy verification is a separate smoke check.
"""

from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from app.app import create_example_app
from pwaf_foundation.config import RuntimeConfig


@pytest.fixture
def proxy_config(tmp_path):
    token = tmp_path / "proxy-token"
    token.write_text("a" * 64)
    return RuntimeConfig(
        mode="lan",
        lan_auth="proxy",
        public_origin="https://tool.example",
        proxy_token_file=token,
        lan_users=frozenset({"operator", "other", "viewer"}),
        lan_operators=frozenset({"operator", "other"}),
        data_dir=tmp_path / "data",
    )


def test_direct_lan_has_no_login_by_default(tmp_path):
    config = RuntimeConfig.from_env(
        {
            "PWAF_MODE": "lan",
            "PWAF_PUBLIC_ORIGIN": "http://tool.example:8191",
            "PWAF_DATA_DIR": str(tmp_path),
        }
    )
    assert config.host == "0.0.0.0" and config.lan_auth == "none"
    with TestClient(
        create_example_app(config), base_url=config.public_origin, client=("192.168.1.10", 123)
    ) as client:
        assert client.get("/").status_code == 200
        token = client.get("/api/csrf").json()["csrf_token"]
        headers = {"Origin": config.public_origin, "X-CSRF-Token": token, "Idempotency-Key": "lan"}
        assert (
            client.post(
                "/api/jobs",
                json={"operation": "performance", "parameters": {"iterations": 1}},
                headers=headers,
            ).status_code
            == 202
        )
        assert (
            client.patch("/api/settings", json={"app_name": "LAN app"}, headers=headers).status_code
            == 200
        )
        assert client.patch("/api/settings", json={}).status_code == 403
        assert client.get("/", headers={"Host": "evil.example"}).status_code == 400


def test_optional_proxy_auth_and_job_ownership(proxy_config):
    config = proxy_config
    headers = {"X-PWAF-Proxy-Token": config.proxy_token, "X-PWAF-User": "operator"}
    with TestClient(
        create_example_app(config), base_url=config.public_origin, client=("127.0.0.1", 123)
    ) as client:
        assert client.get("/").status_code == 401
        assert client.get("/", headers={"X-PWAF-User": "operator"}).status_code == 401
        assert (
            client.get("/", headers={**headers, "X-PWAF-Proxy-Token": "forged"}).status_code == 401
        )
        assert client.get("/", headers={**headers, "X-PWAF-User": "stranger"}).status_code == 403
        assert client.get("/", headers=headers).status_code == 200
        token = client.get("/api/csrf", headers=headers).json()["csrf_token"]
        mutations = {
            **headers,
            "Origin": config.public_origin,
            "X-CSRF-Token": token,
            "Idempotency-Key": "same",
        }
        payload = {"operation": "performance", "parameters": {"iterations": 100000}}
        first = client.post("/api/jobs", json=payload, headers=mutations).json()
        other = {**mutations, "X-PWAF-User": "other"}
        second = client.post("/api/jobs", json=payload, headers=other).json()
        assert first["id"] != second["id"]
        assert "owner" not in first
        assert client.get(first["status_url"], headers=other).status_code == 404
        assert client.post(first["status_url"] + "/cancel", headers=other).status_code == 404
        assert client.get(first["status_url"], headers=headers).status_code == 200
        viewer = {**mutations, "X-PWAF-User": "viewer"}
        assert client.get("/api/settings", headers=viewer).status_code == 200
        assert client.post("/api/jobs", json=payload, headers=viewer).status_code == 403
        assert client.patch("/api/settings", json={}, headers=viewer).status_code == 403
        assert (
            client.get(
                "/",
                headers=[
                    ("X-PWAF-User", "operator"),
                    ("X-PWAF-User", "viewer"),
                    ("X-PWAF-Proxy-Token", config.proxy_token),
                ],
            ).status_code
            == 403
        )
    for peer in ("192.168.1.10", "not-an-ip"):
        with TestClient(
            create_example_app(config), base_url=config.public_origin, client=(peer, 123)
        ) as client:
            assert client.get("/", headers=headers).status_code == 401


def test_proxy_configuration_from_environment(proxy_config):
    config = RuntimeConfig.from_env(
        {
            "PWAF_MODE": "lan",
            "PWAF_LAN_AUTH": "proxy",
            "PWAF_PUBLIC_ORIGIN": proxy_config.public_origin,
            "PWAF_PROXY_TOKEN_FILE": str(proxy_config.proxy_token_file),
            "PWAF_LAN_USERS": "operator, viewer",
            "PWAF_LAN_OPERATORS": "operator",
        }
    )
    assert config.host == "127.0.0.1"
    assert config.origins == {"https://tool.example"}
    assert config.proxy_token not in repr(config)


@pytest.mark.parametrize(
    "changes",
    [
        {"mode": "invalid"},
        {"lan_auth": "bad"},
        {"mode": "local"},
        {"host": "0.0.0.0"},
        {"public_origin": "http://tool.example"},
        {"public_origin": "https://user:pw@tool.example"},
        {"public_origin": "https://tool.example/path"},
        {"public_origin": "https://tool.example:999999"},
        {"public_origin": "https://tool.example:0"},
        {"lan_users": frozenset()},
        {"lan_users": frozenset({"bad user"}), "lan_operators": frozenset()},
        {"lan_operators": frozenset({"unknown"})},
        {"proxy_token_file": None},
    ],
)
def test_invalid_proxy_configuration(proxy_config, changes):
    with pytest.raises(ValueError):
        replace(proxy_config, **changes)


def test_bad_token_and_direct_origin(proxy_config, tmp_path):
    with pytest.raises(ValueError):
        replace(proxy_config, proxy_token_file=tmp_path / "missing")
    proxy_config.proxy_token_file.write_text("too-short")
    with pytest.raises(ValueError):
        replace(proxy_config)
    with pytest.raises(ValueError):
        RuntimeConfig(mode="lan", public_origin="http://tool.example:8000")
    with pytest.raises(ValueError):
        RuntimeConfig(lan_users=frozenset({"operator"}))


def test_origins_are_normalized_for_browsers(proxy_config):
    assert replace(proxy_config, public_origin="https://TOOL.example:443").public_origin == (
        "https://tool.example"
    )
    direct = RuntimeConfig(mode="lan", port=80, public_origin="http://TOOL.example:80")
    assert direct.origins == {"http://tool.example"}
