# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Unreleased

## 2026-07-10 - 1.0.0

### Added

- `Run Starlark Script` action: execute a Starlark (Python-like) script that
  defines `def main(arguments):` and returns a JSON-serialisable result. The
  script runs sandboxed via starlark-pyo3 (no I/O, no filesystem, no imports)
  with the `log` and `set_output` host helpers.
