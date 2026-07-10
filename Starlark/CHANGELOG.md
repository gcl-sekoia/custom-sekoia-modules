# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Unreleased

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
