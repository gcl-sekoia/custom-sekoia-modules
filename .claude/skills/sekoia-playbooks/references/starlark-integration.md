# Starlark Script integration

A custom integration that runs a [Starlark](https://github.com/bazelbuild/starlark)
script (a small, deterministic, Python-like language) inside a playbook node, to
transform data and route the flow — replacing a graph of small transform/filter/branch
nodes with one script.

## Deployed identifiers (this environment)

- Module `Starlark Script (GCL)` — uuid `b94ba300-bd6d-41d5-924a-57ebddaa054a`,
  slug `starlark-gcl`. No module configuration required.
- Action **Run Starlark Script** — uuid `c4ada6f6-0855-4e07-876e-f1a051cfa920`,
  `docker_parameters` `RunScriptAction`. One output branch: `default`.
- Action **Run Starlark Script (branches)** — uuid
  `b7491bc9-3190-4110-8a9e-0ce8c94ab952`, `docker_parameters`
  `RunScriptBranchesAction`. Three outputs: `left`, `main` (centered), `right`.

Both actions share the same script API and take the same arguments. Confirm they're
live with `GET /v1/symphony/modules/b94ba300-...` and re-check UUIDs with
`GET /v1/symphony/modules?limit=100` if this environment differs. If it isn't
installed in your environment, deploying/updating it is the integration-authoring
skill's job, not this one.

## Action arguments

```json
{
  "script": "def main(arguments):\n    return {...}\n",
  "arguments": { ...input object the script receives... }
}
```

- `script` (required): the Starlark source; must define `def main(arguments):`.
- `arguments`: the input object passed to `main` as `arguments`. In a playbook, wire
  it from upstream with templating, e.g. `{"user": "{{ node.0.user }}"}`.

## The script contract — everything is expressed through `return`

`main(arguments)` returns to say both *what data* to emit and *which branch* fires:

- `return <data>` — continue on the primary branch carrying `<data>` as the node's
  results. That's the single output of **Run Starlark Script** (`default`), or the
  centered `main` of **Run Starlark Script (branches)**. A non-object return
  (list/number/string) is wrapped as `{"result": <value>}`.
- `return output(name, data=None)` — continue on the branch called `name` carrying
  `data`. Any name works — it routes to whatever the node wires that name to (which
  need not be in the manifest). A name wired to nothing simply stops the flow there.
- `return stop(reason=None)` — fire no branch: halt the flow here (a filter). The
  optional `reason` is logged. The script still runs to completion; nothing
  downstream runs.

Plus a side-effect helper usable anywhere:
- `log(message)` — record a line in the node-run `logs`.

## Available language features

Starlark core (functions, `if`, `for`, comprehensions, `str`/`int`/`float`/`bool`,
`dict`/`list` and their methods) plus these enabled builtins: `json.encode(v)` /
`json.decode(s)`, `map`, `filter`, `partial`, `struct(...)`, `record(...)`,
`enum(...)`, and type annotations.

Builtins that **work**: `len`, `range`, `enumerate`, `zip`, `min`, `max`, `sorted`,
`reversed`, `abs`, `any`, `all`, `dict`, `int`, `float`, `str`, `"{}".format(...)`.

Builtins that are **absent** (Starlark is not Python — don't assume): **`sum` does
not exist** (accumulate with a loop or `[...]`+ a fold), and there is **no `print`**
(use `log`). If a name is missing you get a compile error like
``Variable `sum` not found`` before the script runs.

## Sandbox limits (design these around)

- **No I/O.** No network, filesystem, or imports; `load()` is disabled. A script is a
  pure transform over its `arguments` plus `log`. It cannot call the Sekoia API or
  fetch a URL — do that with other integration actions in the playbook.
- **No execution timeout.** The runtime can't interrupt a running script, so an
  unbounded loop hangs until the platform's action timeout. Keep loops bounded.

## Worked examples

**Numeric aggregation** (note: no `sum` — accumulate in a loop):
```python
def main(arguments):
    numbers = arguments["numbers"]
    total = 0
    for n in numbers:
        total += n
    return {"sum": total, "average": total / len(numbers)}
```

**Transform (single-output action):**
```python
def main(arguments):
    ips = arguments["ips"]
    private = [ip for ip in ips if ip.startswith("10.") or ip.startswith("192.168.")]
    log("%d of %d are private" % (len(private), len(ips)))
    return {"private": private, "count": len(private)}
```

**Filter (halt when nothing to do):**
```python
def main(arguments):
    alerts = [a for a in arguments["alerts"] if a["severity"] >= 8]
    if len(alerts) == 0:
        return stop("no high-severity alerts")
    return {"high": alerts}
```

**Route (branches action — left / main / right):**
```python
def main(arguments):
    score = arguments["score"]
    if score < 0:
        return stop("invalid score")
    if score >= 90:
        return output("right", {"score": score})   # e.g. escalate path
    if score < 30:
        return output("left", {"score": score})     # e.g. auto-close path
    return {"score": score}                          # normal path (center = main)
```

## Testing a script fast

Iterate with a standalone run before wiring it into a playbook:

```bash
./sekoia.py POST /v1/symphony/actions/c4ada6f6-0855-4e07-876e-f1a051cfa920/run \
  '{"arguments": {"script": "def main(arguments):\n    return {\"ok\": True}\n", "arguments": {}}}'
./sekoia.py watch /v1/symphony/node-runs/<node_run_uuid>
```

Check the node-run's `results` (your return), `outputs` (which branch fired), and
`logs`. A script error surfaces as `status: error` with the Starlark traceback
(including the failing line) in `error`.
