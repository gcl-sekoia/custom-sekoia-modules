# Starlark Script (GCL)

A custom Sekoia integration that runs a [Starlark](https://github.com/bazelbuild/starlark)
script — a small, deterministic, Python-like language — inside a playbook node, so a
single script can replace a graph of transform / filter / branch nodes. One action can
also make outbound HTTP calls with injected credentials the script never sees.

Module UUID `b94ba300-bd6d-41d5-924a-57ebddaa054a`, slug `starlark-gcl`.

## Actions

| Action | `docker_parameters` | Outputs | Purpose |
|---|---|---|---|
| Run Starlark Script | `RunScriptAction` | `default` | Transform / filter data. |
| Run Starlark Script (branches) | `RunScriptBranchesAction` | `left` / `main` / `right` | Transform + route to one of three branches. |
| Run Starlark Script (HTTP) | `RunScriptHttpAction` | `default` | Transform + call HTTP APIs with injected credentials. |
| Base64 Encode/Decode | `Base64Action` | `default` | Standalone base64 utility. |

The three script actions share the same script API and arguments (`script` + an input
`arguments` object); they differ only in their output branches and whether `http()` is
available.

## The script contract

Define `main(arguments)` and express the outcome entirely through `return`:

```python
def main(arguments):
    return {"result": "any JSON-serialisable value"}   # continue on the primary branch
```

- `return <data>` — continue on the primary branch (`default`, or the centered `main`
  on the branches action), carrying `<data>` as the node's results. A non-object return
  is wrapped as `{"result": <value>}`.
- `return output(name, data=None)` — continue on the branch called `name` (any name;
  routing is by name-match against the node's wiring, see the playbook docs).
- `return stop(reason=None)` — fire no branch: halt the flow here (a filter).
- `log(message)` — record a line in the node-run logs (usable anywhere).

### Language

Starlark core (functions, `if`/`for`, comprehensions, `str`/`int`/`float`/`bool`,
`dict`/`list` methods) plus `json.encode`/`json.decode`, `map`, `filter`, `partial`,
`struct`, `record`, `enum`, type annotations. Notably **no `sum`** (accumulate in a
loop) and **no `print`** (use `log`). Available: `len`, `range`, `enumerate`, `zip`,
`min`, `max`, `sorted`, `reversed`, `abs`, `any`, `all`, `.format`.

### Sandbox limits

- **No I/O** in the pure actions — no network, filesystem, or imports; `load()` is
  disabled. Only the HTTP action can reach the network, and only via `http()`.
- **No execution timeout** — the runtime can't interrupt a running script, so an
  unbounded loop runs until the platform's action timeout. Keep loops bounded.

## The HTTP action and credential injection

`Run Starlark Script (HTTP)` adds:

```python
def main(arguments):
    r = http("GET", "https://api.vendor.com/things", credential="vendor_api")
    return {"count": r["json"]["count"]}
```

`http(method, url, headers={}, body=None, credential=NAME)` returns
`{"status", "headers", "json", "body"}`. Credentials follow a **door model**: the
script only *names* a credential — it never receives the secret value. The host
resolves the name, enforces the credential's egress allowlist, injects the secret into
the request, and performs it. So a script can *use* a credential but cannot read, log,
return, or exfiltrate it. Every request must name a credential, and its policy must
allowlist the target host (https only).

### Configuring credentials

Two module-configuration fields:

- **`credentials`** (plain, readable JSON) — a map of credential name → policy:
  ```json
  {
    "vendor_api": {
      "allowed_hosts": ["api.vendor.com"],
      "scheme": "header",
      "header": "Authorization",
      "template": "Bearer {value}",
      "value": "<Fernet-encrypted token>"
    }
  }
  ```
  Each `value` is a Fernet token, not plaintext, so this field is safe to review. A
  credential with only `allowed_hosts` (no `scheme`/`value`) permits auth-less but
  still-allowlisted egress.
- **`encryption_key`** (write-only secret) — the Fernet key that decrypts the `value`
  tokens, host-side, at run time. It is the module's only secret.

Because the encrypted values live in the readable `credentials` field, you can add or
rotate one credential with an ordinary edit of that field — no need to re-enter the
others (secret fields are write-only and can't be read back). `scheme` is v1-limited to
`header`; it's a discriminator, so query/signing schemes can be added later without
changing this shape.

### Sealing values — `seal.py`

Use the bundled `seal.py` to generate the key and seal values (both inputs come from
the environment, never argv):

```bash
export STARLARK_FERNET_KEY=$(.venv/bin/python seal.py genkey)   # generate + capture the key
export VENDOR_API_TOKEN='sk-...'
.venv/bin/python seal.py seal VENDOR_API_TOKEN                  # -> the token to paste as "value"
```

Put the sealed token in the `credentials` policy and set `STARLARK_FERNET_KEY`'s value
in the module configuration's write-only `encryption_key` field.

## Development

```bash
uv venv .venv --python 3.11
uv pip install --python .venv/bin/python "sekoia-automation-sdk==1.22.3" "pydantic==2.10" cryptography starlark-pyo3 pytest pytest-cov
.venv/bin/python -m pytest -q
```

`sekoia-automation-sdk` is pinned to `1.22.3` (pydantic **v1** argument models); 1.23
migrated to pydantic v2 and would break them. Deploy/sync from git and use these actions
in playbooks per the `sekoia-integrations` and `sekoia-playbooks` skills.

## Note on the shared module secret

Declaring `encryption_key` makes the module carry a secret, so *every* action attempts a
secret fetch at start. Playbook nodes always have a module configuration, so they're
unaffected; but a **config-less standalone action run** now errors — attach a
configuration when testing an action standalone.
