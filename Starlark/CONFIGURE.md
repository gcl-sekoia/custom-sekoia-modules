# Starlark Script

Run a [Starlark](https://github.com/bazelbuild/starlark) script inside a
playbook. Starlark is a small, deterministic, Python-like language: familiar
syntax (functions, `if`, comprehensions, dicts/lists) but no I/O, no imports and
no filesystem or network access. This lets a single script replace a graph of
transform / filter / branch nodes.

The module provides two actions with the same script API, differing only in how
many output branches they expose:

- **Run Starlark Script** — one output. A transform or filter.
- **Run Starlark Script (branches)** — three outputs (`left`, `main`, `right`)
  for routing the flow.

## The script contract

Your script defines `main(arguments)` and expresses its outcome entirely through
`return`:

```python
def main(arguments):
    return {"result": "any JSON-serialisable value"}   # continue with this data
```

`arguments` is the input object (typically wired from previous nodes). A non-object
return (list, string, number) is wrapped as `{"result": <value>}`.

## Return values and routing

- `return <data>` — continue on the primary branch, carrying `<data>` as the
  node's results. That is the single output of **Run Starlark Script**, and the
  centered `main` of **Run Starlark Script (branches)**.
- `return output(name, data=None)` — continue on the branch called `name`,
  carrying `data`. On the branches action, `output("left", …)` / `output("right", …)`
  target the two sides.
- `return stop(reason=None)` — halt: no branch fires, so nothing downstream runs.
  The optional `reason` is logged.

### Custom / editable outputs

The output branches shown on a node are only a default. In the playbook editor
(or the workflow JSON) you can **wire additional branches by any name** — the
engine routes purely by matching the name a script emits against what the node
wires, and it does not check either against this action's declared outputs. So
`return output("quarantine", data)` works as long as a `quarantine` branch is
wired on the node; a name wired to nothing simply stops the flow there. A script
that raises an error additionally emits an `error` branch you can wire for
error handling.

## Available builtins

Beyond the Starlark core (functions, control flow, comprehensions, `str`, `int`,
`dict`, `list`, string/`dict`/`list` methods), these are enabled: `json.encode` /
`json.decode`, `map`, `filter`, `partial`, `struct`, `record`, `enum`, and type
annotations.

## Host helpers

- `log(message)` — record a message in the action logs.
- `output(name, data=None)`, `stop(reason=None)` — returned to route the flow
  (see above).

## Example (branches action)

```python
def main(arguments):
    alerts = arguments["alerts"]
    high = [a for a in alerts if a["severity"] >= 8]
    if len(high) == 0:
        return stop("no high-severity alerts")
    if len(high) > 10:
        return output("right", {"high": high, "count": len(high)})   # e.g. escalate
    log("kept %d of %d alerts" % (len(high), len(alerts)))
    return {"high": high, "count": len(high)}                        # normal path (center)
```

## Limitations

- **No I/O.** A script cannot make HTTP calls, read files or import modules. It
  is a pure transform over its `arguments`.
- **No execution timeout.** The current starlark-pyo3 build cannot interrupt a
  running script, so a non-terminating script (e.g. an unbounded loop) is only
  stopped by the platform's action timeout. Keep loops bounded.
