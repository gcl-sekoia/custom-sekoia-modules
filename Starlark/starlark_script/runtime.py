"""Sandboxed Starlark runtime for the Run Script action.

A playbook author supplies a `.star` script that defines `main(arguments)` and
returns a JSON-serialisable value. The script runs in-process via starlark-pyo3
with only the language builtins we opt into (json/map/filter/struct/...):
Starlark itself has no I/O, no filesystem and no `import`/`exec`, and `load()`
is neutralised because no FileLoader is passed to `eval`. So a script is a pure
transform over its `arguments` plus whatever host callables the action injects
(`log`, `set_output`); it cannot reach the network, the disk or other files.

Runaway scripts: this starlark-pyo3 build (2026.1) does NOT accept a
`check_cancelled` callback on `FrozenModule.call`, and a Python-thread timeout
cannot preempt a CPU-bound script because the eval holds the GIL for its whole
duration. A non-terminating script is therefore bounded only by the platform's
action timeout. Accepted for trusted, playbook-authored scripts; revisit with
subprocess isolation if untrusted scripts ever become a use case.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

import starlark

ENTRYPOINT = "main"

# Language extensions exposed on top of Globals.standard() (which is bare -- no
# json, no print, no map). We omit Debug/Breakpoint/CallStack/Internal (a
# debugging/introspection surface with no place in a data transform).
_EXTENSIONS = [
    starlark.LibraryExtension.Json,
    starlark.LibraryExtension.Print,
    starlark.LibraryExtension.Pprint,
    starlark.LibraryExtension.Map,
    starlark.LibraryExtension.Filter,
    starlark.LibraryExtension.Partial,
    starlark.LibraryExtension.Typing,
    starlark.LibraryExtension.StructType,
    starlark.LibraryExtension.RecordType,
    starlark.LibraryExtension.EnumType,
    starlark.LibraryExtension.RustDecimal,
]

_GLOBALS = starlark.Globals.extended_by(_EXTENSIONS)


class ScriptError(Exception):
    """A script that failed to compile or run. The message carries the Starlark
    error text, which already includes the source location and a snippet -- safe
    to surface here because the script author is the person reading the logs and
    there is no credential material in scope (unlike the credproxy runtime)."""


class StarlarkScript:
    """A compiled `.star` script. Parsing, resolution and top-level evaluation
    happen once at construction, so a syntax error, a `load()`, or a reference to
    an unknown name fails here rather than at run time. `run(arguments)` then
    calls `main(arguments)` for each invocation."""

    def __init__(
        self,
        source: str,
        *,
        primitives: dict[str, Callable[..., Any]] | None = None,
        filename: str = "script.star",
    ):
        self._filename = filename
        module = starlark.Module()
        # Injected host callables must be registered before eval so the resolver
        # sees them; they become module globals the script can call by name.
        for name, fn in (primitives or {}).items():
            module.add_callable(name, fn)
        try:
            starlark.eval(module, starlark.parse(filename, source), _GLOBALS)
        except starlark.StarlarkError as exc:
            raise ScriptError(f"script failed to compile: {exc}") from exc
        self._frozen = module.freeze()

    def run(self, arguments: Any) -> Any:
        """Call `main(arguments)` and return its value converted to Python. The
        argument is passed positionally (starlark-pyo3 JSON-converts it), so it
        must be JSON-serialisable -- which playbook arguments always are."""
        try:
            return self._frozen.call(ENTRYPOINT, arguments)
        except starlark.StarlarkError as exc:
            message = str(exc)
            if f"Module has no symbol `{ENTRYPOINT}`" in message:
                raise ScriptError(
                    f"script must define an entrypoint `def {ENTRYPOINT}(arguments):`"
                ) from exc
            raise ScriptError(f"script raised an error: {message}") from exc
