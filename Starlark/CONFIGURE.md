# Starlark Script

Run a [Starlark](https://github.com/bazelbuild/starlark) script inside a
playbook. Starlark is a small, deterministic, Python-like language: familiar
syntax (functions, `if`, comprehensions, dicts/lists) but no I/O, no imports and
no filesystem or network access. This action lets a single script replace a
graph of transform / filter / branch nodes.

## The script contract

Your script must define an entrypoint:

```python
def main(arguments):
    # arguments is the "Arguments" input object (typically wired from
    # previous playbook nodes)
    return {"result": "any JSON-serialisable value"}
```

`main` is called with the `arguments` object and its return value becomes the
action's results. A non-object return (list, string, number) is wrapped as
`{"result": <value>}`.

## Available builtins

Beyond the Starlark core (functions, control flow, comprehensions, `str`,
`int`, `dict`, `list`, string/`dict`/`list` methods), these are enabled:

- `json.encode(v)` / `json.decode(s)`
- `map`, `filter`, `partial`
- `struct(...)`, `record(...)`, `enum(...)`
- type annotations (`Typing`)

## Host helpers

Two functions are injected by the action:

- `log(message)` — record a message in the action logs.
- `set_output(name)` — activate the named playbook output branch, so the script
  can drive conditional routing (e.g. `set_output("malicious")`).

## Example

```python
def main(arguments):
    high = [a for a in arguments["alerts"] if a["severity"] >= 8]
    if len(high) > 0:
        set_output("has_high_severity")
    log("kept %d of %d alerts" % (len(high), len(arguments["alerts"])))
    return {"high_severity": high, "count": len(high)}
```

## Limitations

- **No I/O.** A script cannot make HTTP calls, read files or import modules. It
  is a pure transform over its `arguments`.
- **No execution timeout.** The current starlark-pyo3 build cannot interrupt a
  running script, so a non-terminating script (e.g. an unbounded loop) is only
  stopped by the platform's action timeout. Keep loops bounded.
