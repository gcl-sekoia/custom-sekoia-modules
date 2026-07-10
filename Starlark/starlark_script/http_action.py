"""HTTP-capable Starlark action with door-model credential injection.

Unlike the pure transform/branch actions, this one exposes an `http()` primitive
so a script can call out to an API. Credentials follow the credproxy "door" model:
the script never receives a secret value — it only names a credential, and the host
injects the secret into the outbound request and enforces an egress allowlist. So a
script can *use* a credential but cannot read, log, return, or exfiltrate it.

Config (module level, all optional):
- `credentials`: PLAIN JSON string (readable/reviewable) mapping a credential name to
  its policy `{allowed_hosts, scheme, header, template, value}`, where `value` is a
  Fernet-encrypted token — not the plaintext secret.
- `encryption_key`: the write-only SECRET Fernet key that decrypts those `value`
  tokens. It is the module's only secret; the values live (encrypted) in the plain,
  readable `credentials` field, so a credential can be added/rotated with an ordinary
  read-modify-write of that field (no re-entering the others).

Symmetric envelope: the operator seals values with the key and the module unseals
with the same key, so there is no seal-without-unseal need that would call for an
asymmetric scheme. v1 supports one injection `scheme`, "header": render `template`
(default `{value}`) into the named request header. `scheme` is a discriminator, so
query/signing schemes can be added later without changing the config shape or the
`http()` signature.
"""
from __future__ import annotations

import json
import time
from typing import Any
from urllib.parse import urlparse

import requests
from cryptography.fernet import Fernet, InvalidToken

from .run_script import BaseRunScriptAction, format_time, parse_time

HTTP_TIMEOUT = 30
SEKOIA_API_BASE = "https://api.sekoia.io"
POLL_INTERVAL = 1.5  # seconds between async-job status polls


def _api(creds: dict, method: str, path: str, credential: Any, body: Any = None) -> Any:
    """Authenticated call to the Sekoia API via the same door-model as http(): the
    named credential must allowlist api.sekoia.io. Returns parsed JSON; raises on >=300."""
    resp = do_request(creds, method, SEKOIA_API_BASE + path, body=body, credential=credential)
    if resp["status"] >= 300:
        raise HttpError("sekoia api %s %s -> HTTP %s" % (method, path, resp["status"]))
    return resp["json"]


def do_search_events(creds, query, earliest="-1h", latest="now", limit=100,
                     communities=None, eternal=False, timeout=90, credential="sekoia_api"):
    """Async Lucene event search (create -> poll -> fetch), host-side. Returns the
    list of event objects. Relative/ISO/epoch times are normalised to ISO."""
    body = {
        "term": str(query), "filters": [], "visible": False,
        "only_eternal": bool(eternal), "lenient": True,
        "community_uuids": list(communities or []),
        "earliest_time": format_time(parse_time(earliest)),
        "latest_time": format_time(parse_time(latest)),
    }
    job = _api(creds, "POST", "/v1/sic/conf/events/search/jobs", credential, body)
    uuid = job["uuid"]
    deadline = time.monotonic() + float(timeout)
    status = None
    while True:
        status = _api(creds, "GET", "/v1/sic/conf/events/search/jobs/%s" % uuid, credential)
        if status.get("status") in (2, 3):
            break
        if time.monotonic() > deadline:
            raise HttpError("search_events timed out after %ss" % timeout)
        time.sleep(POLL_INTERVAL)
    if status.get("status") == 3:
        raise HttpError("search_events: job was cancelled/failed")
    evs = _api(creds, "GET",
               "/v1/sic/conf/events/search/jobs/%s/events?limit=%d" % (uuid, int(limit)), credential)
    return evs.get("items") or []


def do_sol(creds, query, communities=None, intakes=None, limit=1000, timeout=90, credential="sekoia_api"):
    """Async SOL / notebook query (create -> poll -> paginate results), host-side.
    Returns the list of result rows."""
    qd = {"ql_query": str(query), "community_uuids": list(communities or [])}
    if intakes is not None:
        qd["intake_uuids"] = list(intakes)
    created = _api(creds, "POST", "/v1/notebooks/queries/runs", credential, {"query_definition": qd})
    uuid = created["uuid"]
    terminal = {"finished", "failed", "error", "cancelled", "canceled"}
    deadline = time.monotonic() + float(timeout)
    run = None
    while True:
        run = _api(creds, "GET", "/v1/notebooks/queries/runs/%s?limit=1" % uuid, credential)
        if (run.get("status") or "").lower() in terminal:
            break
        if time.monotonic() > deadline:
            raise HttpError("sol timed out after %ss" % timeout)
        time.sleep(POLL_INTERVAL)
    if (run.get("status") or "").lower() != "finished":
        raise HttpError("sol: run ended with status %r" % run.get("status"))
    rows, off, lim = [], 0, int(limit)
    while len(rows) < lim:
        page = _api(creds, "GET",
                    "/v1/notebooks/queries/runs/%s?limit=%d&offset=%d" % (uuid, min(1000, lim - len(rows)), off),
                    credential)
        batch = page.get("results") or []
        rows.extend(batch)
        off += len(batch)
        total = page.get("total")
        if not batch or (total is not None and off >= total):
            break
    return rows


class HttpError(Exception):
    """A credential/egress policy violation or transport failure. Messages never
    include a secret value (the value only ever lives in a request header the host
    builds, never in an error or the returned response headers)."""


def parse_credentials(credentials_json: str | None, encryption_key: str | None) -> dict[str, dict]:
    """Resolve name -> credential from the plain policy JSON, decrypting each `value`
    Fernet token with `encryption_key`. Decryption happens host-side; the plaintext
    never leaves this process (and never reaches the Starlark VM)."""
    policy = json.loads(credentials_json) if credentials_json else {}
    if not policy:
        return {}
    # Build the cipher lazily: a credential with only allowed_hosts (no encrypted
    # value) needs no key, so requiring one upfront would break allowlist-only creds.
    fernet = None

    creds: dict[str, dict] = {}
    for name, pol in policy.items():
        token = pol.get("value")
        value = None
        if token is not None:
            if not encryption_key:
                raise HttpError(f"credential {name!r} has an encrypted value but encryption_key is not set")
            if fernet is None:
                fernet = Fernet(encryption_key.encode() if isinstance(encryption_key, str) else encryption_key)
            try:
                value = fernet.decrypt(token.encode()).decode()
            except (InvalidToken, ValueError, TypeError):
                # Sanitized: never surface the token or key material.
                raise HttpError(f"could not decrypt value for credential {name!r}")
        creds[name] = {
            "allowed_hosts": pol.get("allowed_hosts") or [],
            "scheme": pol.get("scheme"),
            "header": pol.get("header"),
            "template": pol.get("template", "{value}"),
            "value": value,
        }
    return creds


def _inject(headers: dict, cred: dict) -> dict:
    scheme = cred["scheme"]
    if scheme != "header":
        raise HttpError(f"unsupported scheme {scheme!r} (this action supports 'header')")
    if not cred.get("header"):
        raise HttpError("credential policy is missing 'header'")
    headers = dict(headers)
    headers[cred["header"]] = cred["template"].format(value=cred["value"])
    return headers


def do_request(creds: dict[str, dict], method: Any, url: Any, headers: Any = None,
               body: Any = None, credential: Any = None) -> dict:
    """Perform one HTTP request on a script's behalf. Requires a named credential
    whose policy allowlists the URL's host; injects the secret host-side. Returns
    the RESPONSE (status/headers/json/body) — never the request headers, so the
    injected secret is not reflected back to the script."""
    if not credential:
        raise HttpError("http() requires a 'credential' name; all egress must be allowlisted")
    cred = creds.get(str(credential))
    if cred is None:
        raise HttpError(f"unknown credential {str(credential)!r}")

    parsed = urlparse(str(url))
    if parsed.scheme != "https":
        raise HttpError("only https:// URLs are allowed")
    if (parsed.hostname or "") not in cred["allowed_hosts"]:
        raise HttpError(f"host {parsed.hostname!r} is not in allowed_hosts for {str(credential)!r}")

    req_headers = dict(headers or {})
    if cred["scheme"] is not None:
        req_headers = _inject(req_headers, cred)

    try:
        resp = requests.request(
            str(method).upper(), str(url), headers=req_headers,
            json=body if body is not None else None, timeout=HTTP_TIMEOUT,
        )
    except requests.RequestException as error:
        # Sanitized: type only, never the message (which could echo a URL/creds).
        raise HttpError(f"request failed: {type(error).__name__}")

    try:
        parsed_json = resp.json()
    except ValueError:
        parsed_json = None
    return {
        "status": resp.status_code,
        "headers": dict(resp.headers),
        "json": parsed_json,
        "body": resp.text,
    }


class RunScriptHttpAction(BaseRunScriptAction):
    name = "Run Starlark Script (HTTP)"
    description = (
        "Execute a Starlark script that can call HTTP APIs via http(method, url, ..., "
        "credential=NAME). Credentials are injected host-side from the module "
        "configuration and never exposed to the script; each request must name a "
        "credential whose policy allowlists the target host."
    )
    CENTER = "default"

    def _primitives(self) -> dict[str, Any]:
        primitives = super()._primitives()
        cfg = self._config_dict()
        creds = parse_credentials(cfg.get("credentials"), cfg.get("encryption_key"))
        primitives["http"] = lambda method, url, headers=None, body=None, credential=None: do_request(
            creds, method, url, headers, body, credential
        )
        primitives["search_events"] = lambda query, earliest="-1h", latest="now", limit=100, \
            communities=None, eternal=False, timeout=90, credential="sekoia_api": do_search_events(
                creds, query, earliest, latest, limit, communities, eternal, timeout, credential)
        primitives["sol"] = lambda query, communities=None, intakes=None, limit=1000, \
            timeout=90, credential="sekoia_api": do_sol(
                creds, query, communities, intakes, limit, timeout, credential)
        return primitives

    def _config_dict(self) -> dict:
        try:
            cfg = self.module.configuration
        except Exception:
            return {}
        if isinstance(cfg, dict):
            return cfg
        if cfg is None:
            return {}
        try:
            return cfg.dict()
        except Exception:
            return {}
