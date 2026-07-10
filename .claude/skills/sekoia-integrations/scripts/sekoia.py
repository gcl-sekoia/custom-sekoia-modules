#!/usr/bin/env python3
"""Tiny Sekoia API client for interactive use.

Requests:
    ./sekoia.py GET  /v1/tasks/<uuid>
    ./sekoia.py POST /v1/symphony/modules/from-git '{"git": "..."}'
    echo '{"k":1}' | ./sekoia.py POST /v1/some/path -

Watch a task / run until it reaches a terminal state (polls until the top-level
`status` — or `playbook_run.status` — is FINISHED/FAILED/ERROR/SUCCESS/CANCELLED):
    ./sekoia.py watch /v1/tasks/<uuid>
    ./sekoia.py watch /v1/symphony/node-runs/<uuid>
    ./sekoia.py watch /v1/symphony/playbook-runs/<uuid>

Reads the bearer token from $SEKOIA_PURPLE_LAB_API_TOKEN. Base URL defaults to
https://app.sekoia.io/api (override with $SEKOIA_API_BASE).
"""
import json
import os
import sys
import time

import requests

BASE = os.environ.get("SEKOIA_API_BASE", "https://app.sekoia.io/api").rstrip("/")
TOKEN = os.environ.get("SEKOIA_PURPLE_LAB_API_TOKEN")
TERMINAL = {"finished", "failed", "error", "success", "cancelled", "canceled"}


def _headers():
    return {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}


def _url(path: str) -> str:
    return f"{BASE}/{path.lstrip('/')}"


def _status_of(body) -> str | None:
    if not isinstance(body, dict):
        return None
    if isinstance(body.get("status"), str):
        return body["status"]
    pr = body.get("playbook_run")
    if isinstance(pr, dict) and isinstance(pr.get("status"), str):
        return pr["status"]
    return None


def request(method: str, path: str, body=None) -> int:
    resp = requests.request(method, _url(path), headers=_headers(), json=body, timeout=60)
    print(f"[HTTP {resp.status_code}] {method} {_url(path)}", file=sys.stderr)
    try:
        print(json.dumps(resp.json(), indent=2))
    except ValueError:
        print(resp.text)
    return 0 if resp.ok else 1


def watch(path: str, interval: float = 3.0, timeout: float = 600.0) -> int:
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        resp = requests.get(_url(path), headers=_headers(), timeout=60)
        if not resp.ok:
            print(f"[HTTP {resp.status_code}] {path}", file=sys.stderr)
            print(resp.text)
            return 1
        body = resp.json()
        status = _status_of(body)
        if status != last:
            print(f"[{time.strftime('%H:%M:%S')}] status={status}", file=sys.stderr)
            last = status
        if status and status.lower() in TERMINAL:
            print(json.dumps(body, indent=2))
            return 0 if status.lower() in {"finished", "success"} else 1
        time.sleep(interval)
    print(f"timed out after {timeout}s (last status={last})", file=sys.stderr)
    return 1


def main(argv: list[str]) -> int:
    if not argv or not TOKEN:
        print(__doc__, file=sys.stderr)
        return 2
    if argv[0] == "watch":
        if len(argv) < 2:
            print(__doc__, file=sys.stderr)
            return 2
        return watch(argv[1])
    if len(argv) < 2:
        print(__doc__, file=sys.stderr)
        return 2
    method, path = argv[0].upper(), argv[1]
    body = None
    if len(argv) >= 3:
        raw = sys.stdin.read() if argv[2] == "-" else argv[2]
        body = json.loads(raw)
    return request(method, path, body)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
