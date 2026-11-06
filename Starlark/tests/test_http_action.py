import json

import pytest
from cryptography.fernet import Fernet

from starlark_script import http_action
from starlark_script.base import StarlarkModule
from starlark_script.http_action import HttpError, RunScriptHttpAction, do_request, parse_credentials


@pytest.fixture
def key() -> str:
    return Fernet.generate_key().decode()


def seal(key: str, value: str) -> str:
    return Fernet(key.encode()).encrypt(value.encode()).decode()


def policy(key: str, **overrides) -> str:
    cred = {
        "allowed_hosts": ["api.vendor.com"],
        "scheme": "header",
        "header": "Authorization",
        "template": "Bearer {value}",
        "value": seal(key, "s3cr3t"),
    }
    cred.update(overrides)
    return json.dumps({"vendor": cred})


class FakeResponse:
    def __init__(self, status=200, payload=None, text=""):
        self.status_code = status
        self.headers = {"Content-Type": "application/json"}
        self._payload = payload
        self.text = text

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


def test_parse_credentials_decrypts_values(key):
    creds = parse_credentials(policy(key), key)
    assert creds["vendor"]["value"] == "s3cr3t"
    assert creds["vendor"]["allowed_hosts"] == ["api.vendor.com"]


def test_parse_credentials_requires_key_when_configured(key):
    with pytest.raises(HttpError, match="has an encrypted value but encryption_key is not set"):
        parse_credentials(policy(key), None)


def test_parse_credentials_bad_token_is_sanitized(key):
    bad = json.dumps({"vendor": {"value": "not-a-token", "allowed_hosts": []}})
    with pytest.raises(HttpError, match="could not decrypt value for credential 'vendor'"):
        parse_credentials(bad, key)


def test_request_injects_secret_and_returns_response(key, monkeypatch):
    creds = parse_credentials(policy(key), key)
    captured = {}

    def fake_request(method, url, headers=None, json=None, timeout=None, allow_redirects=True):
        captured["method"], captured["url"], captured["headers"] = method, url, headers
        captured["allow_redirects"] = allow_redirects
        return FakeResponse(200, {"ok": True})

    monkeypatch.setattr(http_action.requests, "request", fake_request)
    result = do_request(creds, "get", "https://api.vendor.com/things", credential="vendor")

    assert captured["headers"]["Authorization"] == "Bearer s3cr3t"   # injected host-side
    assert captured["allow_redirects"] is False
    assert result == {"status": 200, "headers": {"Content-Type": "application/json"}, "json": {"ok": True}, "body": ""}


def test_request_refuses_disallowed_host(key):
    creds = parse_credentials(policy(key), key)
    with pytest.raises(HttpError, match="not in allowed_hosts"):
        do_request(creds, "GET", "https://evil.example.com/x", credential="vendor")


def test_request_refuses_non_https(key):
    creds = parse_credentials(policy(key), key)
    with pytest.raises(HttpError, match="only https"):
        do_request(creds, "GET", "http://api.vendor.com/x", credential="vendor")


def test_request_requires_credential(key):
    creds = parse_credentials(policy(key), key)
    with pytest.raises(HttpError, match="requires a 'credential'"):
        do_request(creds, "GET", "https://api.vendor.com/x")


def test_request_unknown_credential(key):
    creds = parse_credentials(policy(key), key)
    with pytest.raises(HttpError, match="unknown credential 'nope'"):
        do_request(creds, "GET", "https://api.vendor.com/x", credential="nope")


def test_action_exposes_http_and_never_leaks_secret(key, monkeypatch):
    def fake_request(method, url, headers=None, json=None, timeout=None, allow_redirects=True):
        return FakeResponse(200, {"echo": headers.get("Authorization")})

    monkeypatch.setattr(http_action.requests, "request", fake_request)

    action = RunScriptHttpAction(StarlarkModule())
    action.module._configuration = {"credentials": policy(key), "encryption_key": key}
    script = (
        "def main(arguments):\n"
        "    r = http('GET', 'https://api.vendor.com/things', credential='vendor')\n"
        "    return {'status': r['status'], 'echo': r['json']['echo']}\n"
    )
    results = action.run({"script": script})
    # The response the API echoed shows the injected header, but the script itself
    # never had the secret value or built the header.
    assert results["status"] == 200
    assert results["echo"] == "Bearer s3cr3t"
    assert action.outputs == {"default": True}


def test_empty_config_has_no_credentials():
    assert parse_credentials(None, None) == {}


def test_allowlist_only_credential_makes_no_injection(monkeypatch):
    # A credential with allowed_hosts but no scheme/value: scoped egress, no secret.
    pol = json.dumps({"public": {"allowed_hosts": ["api.vendor.com"]}})
    creds = parse_credentials(pol, None)
    captured = {}

    def fake_request(method, url, headers=None, json=None, timeout=None, allow_redirects=True):
        captured["headers"] = headers
        return FakeResponse(200, {"ok": True})

    monkeypatch.setattr(http_action.requests, "request", fake_request)
    do_request(creds, "GET", "https://api.vendor.com/open", credential="public")
    assert "Authorization" not in captured["headers"]


def test_disallowed_host_surfaces_as_action_error(key):
    action = RunScriptHttpAction(StarlarkModule())
    action.module._configuration = {"credentials": policy(key), "encryption_key": key}
    script = (
        "def main(arguments):\n"
        "    return http('GET', 'https://evil.example.com/x', credential='vendor')\n"
    )
    results = action.run({"script": script})
    assert results is None
    assert "not in allowed_hosts" in action.error_message


def test_redirect_to_other_host_is_returned_not_followed(key, requests_mock):
    # An allowlisted host answering 3xx must not carry the request (and the injected
    # header) to a host outside allowed_hosts: the 3xx goes back to the script as-is.
    creds = parse_credentials(policy(key, header="X-Api-Key", template="{value}"), key)
    requests_mock.get(
        "https://api.vendor.com/things", status_code=302, headers={"Location": "https://evil.example.com/x"}
    )
    target = requests_mock.get("https://evil.example.com/x", json={"leaked": True})

    result = do_request(creds, "GET", "https://api.vendor.com/things", credential="vendor")

    assert result["status"] == 302
    assert result["headers"]["Location"] == "https://evil.example.com/x"
    assert not target.called
    assert requests_mock.call_count == 1
    assert requests_mock.request_history[0].headers["X-Api-Key"] == "s3cr3t"
