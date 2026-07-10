# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Unreleased

## 2026-07-10 - 1.1.1

### Changed

- Renamed the module from "Starlark Script (GCL)" to "Starlark Script" and the slug
  from `starlark-gcl` to `starlark-script`.

## 2026-07-10 - 1.1.0

### Added

- New action **Run Starlark Script (HTTP)** exposing an `http(method, url, headers,
  body, credential)` primitive so a script can call an API. Credentials follow a
  door model: the script names a credential but never receives its value — the host
  injects it and enforces a per-credential `allowed_hosts` egress allowlist
  (https-only). The script cannot read, log, return, or exfiltrate a secret.
- Module configuration for credentials: a readable `credentials` JSON policy whose
  per-credential `value` is a Fernet token, plus a single write-only `encryption_key`
  secret. Values live (encrypted) in the readable field, so one can be added/rotated
  without re-entering the others. Adds a `cryptography` dependency.
- `seal.py` helper (`genkey` / `seal <ENV_VAR>`) to generate the Fernet key and seal
  credential values, taking both inputs from the environment (never argv).
- `README.md` documenting the module (actions, script contract, HTTP credential model,
  development).

### Note

- Declaring `encryption_key` makes the module carry a secret, so every action now
  fetches secrets at start. Playbook nodes (which always have a configuration) are
  unaffected, but a config-less standalone action run errors — attach a configuration
  when testing standalone.

## 2026-07-10 - 1.0.6

### Added

- New action **Base64 Encode/Decode**: base64-encode or -decode a string, chosen
  via a `mode` argument (`encode`/`decode`). Standalone utility action, unrelated
  to the Starlark script runtime.

## 2026-07-10 - 1.0.5

### Changed

- Routing now uses a single `output(name, data=None)` builder that can address
  any branch by name, replacing the fixed `left`/`right` builders. Node output
  branches are editable in the playbook and routed by name (the manifest outputs
  are only an editor hint), so a script can target a hand-wired branch. Documented
  in CONFIGURE.md.

## 2026-07-10 - 1.0.4

### Changed

- Routing and data are now both expressed through `return`, instead of mixing a
  returned value with `output()`/`stop()` side-effects. A bare `return <data>`
  continues on the primary branch; `return stop(reason)` halts; `left`/`right`
  builders route to a side branch on the branches action.

### Added

- Second action **Run Starlark Script (branches)** with three outputs
  (`left`, `main` centered, `right`). The original **Run Starlark Script** keeps
  a single output. Both share one runtime.

## 2026-07-10 - 1.0.3

### Added

- Three output branches — `left`, `default` (centered), `right` — declared in the
  manifest so they are wireable in the playbook editor. Script `output(name)`
  helper fires one of them (validated; pick-one). Calling neither `output` nor
  `stop` fires the centered `default`.

### Changed

- `stop()` now withholds every branch (nothing fires), rather than only the
  single former `default`.

## 2026-07-10 - 1.0.2

### Changed

- The action now has a single `default` output branch. Removed the script
  `set_output` helper: with one branch there is nothing to route, and activating
  a named branch silently suppressed `default` and stalled the flow.

### Added

- Script `stop(reason=None)` helper: withholds the `default` branch to halt the
  playbook (a filter), optionally logging a reason.

## 2026-07-10 - 1.0.1

### Changed

- No functional change; version bump to exercise the platform "check for
  updates" sync flow from the tracked git branch.

## 2026-07-10 - 1.0.0

### Added

- `Run Starlark Script` action: execute a Starlark (Python-like) script that
  defines `def main(arguments):` and returns a JSON-serialisable result. The
  script runs sandboxed via starlark-pyo3 (no I/O, no filesystem, no imports)
  with the `log` and `set_output` host helpers.
