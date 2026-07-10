---
name: sekoia-playbooks
description: >-
  Create, edit, run and debug Sekoia (Sekoia.io / Symphony) automation playbooks
  via the platform API — including using the "Starlark Script" integration that runs
  Python-like scripts inside a playbook. Use this whenever the user mentions Sekoia
  playbooks, Symphony, automation nodes/actions/triggers, running or debugging a
  playbook or a node, wiring nodes together, output branches, or writing/running a
  Starlark script action — even if they don't name the API explicitly. (For
  building, installing, or updating a custom integration/module from git, use the
  Sekoia integration-authoring skill instead.)
---

# Sekoia playbooks

Sekoia's automation ("Symphony") runs **playbooks**: directed graphs of **nodes**
(a trigger, then actions/operators) that pass data along wired **output branches**.
This skill drives the platform through its HTTP API to build, run, and debug those
playbooks, using the actions that installed **integrations** (modules) provide. It
does not cover building or installing an integration — that's a separate skill.

Most of the API used here is **not in the public OpenAPI spec** — it was mapped
empirically. Trust the concrete recipes below over any schema you find.

## Setup (do this first)

Every call needs a bearer token from the environment and the API base
`https://app.sekoia.io/api`. A helper script is bundled — **use it instead of
hand-writing curl**, so output is consistent and status codes are visible:

```bash
# from the skill's scripts/ dir; copy it next to your work if convenient
./sekoia.py GET  /v1/symphony/playbooks/<uuid>
./sekoia.py POST /v1/symphony/actions/<uuid>/run '{"arguments": {...}}'
echo '{...}' | ./sekoia.py POST /v1/some/path -              # body from stdin
./sekoia.py watch /v1/symphony/node-runs/<uuid>              # poll a run to terminal
```

It reads `$SEKOIA_PURPLE_LAB_API_TOKEN`, prepends the base URL (leading slash
optional), pretty-prints JSON to stdout, and prints the HTTP status to stderr.
Confirm the token is set (`test -n "$SEKOIA_PURPLE_LAB_API_TOKEN"`) before starting.

For anything beyond a single call (finding a run, driving a multi-node build), it
is usually faster to write a short throwaway Python script using `requests` and the
same token/base than to chain many `sekoia.py` invocations.

## Async is the rule: everything returns a run to poll

Action runs and playbook runs are **asynchronous**. A POST returns a
`node_run_uuid` (standalone action) or a playbook run you must find; then you
**poll to a terminal state** — lowercase `finished` / `error`. `./sekoia.py watch
<path>` polls a node-run or playbook-run until terminal. Cold-starting an action
container can take 30–60s the first time; keep polling.

## The core workflows

Pick the workflow that matches the request. Each references a detailed file — read
it before executing, because the JSON shapes and gotchas matter.

### 1. Run one action, once (fastest way to test an action)

No playbook or trigger needed. Best for iterating on a script.

```bash
./sekoia.py POST /v1/symphony/actions/<action_uuid>/run '{"arguments": {<action args>}}'
# -> {"node_run_uuid": "..."}
./sekoia.py watch /v1/symphony/node-runs/<node_run_uuid>
# -> status, results, outputs, logs, error
```

### 2. Build or edit a playbook

Playbooks are a JSON graph. Fetch, mutate `content.nodes`, PATCH back. Node
positions, output wiring and inter-node data templating all have specific rules —
**read `references/playbook-json.md`** before building or editing one.

### 3. Run a whole playbook

A playbook runs when a trigger fires. For a **Manual Trigger**: activate the
playbook, emit an event to its trigger configuration, then find and poll the run.
Full recipe with the exact endpoints is in `references/api.md`.

### 4. Debug a playbook or node

Read the run details (`.../details`) and each node-run's `status` / `error` /
`logs` / `results`. A node whose action script fails shows `status: error` and
emits an `error` output branch. See `references/api.md` → Debugging.

### 5. Use the Starlark Script integration

The flagship custom integration: run a Python-like script inside a playbook to
transform data and route the flow, replacing a graph of small nodes. It has two
actions (1 output; or `left`/`main`/`right`). The script API (`return <data>`,
`return output(name, data)`, `return stop(reason)`, `log(...)`) and the deployed
UUIDs are in **`references/starlark-integration.md`** — read it whenever the task
involves a Starlark script.

## Working style that avoids dead ends

- **Verify, don't assume.** After a run, read the node-run and confirm
  `results`/`outputs` are what you intended — a node can "finish" while having
  routed nowhere.
- **Iterate an action standalone first** (workflow 1), then wire it into a playbook
  once the script is right. It's much faster than re-running a whole playbook.
- **Poll in the background** for slow runs (cold starts) rather than blocking, and
  capture the returned run uuid immediately — a buffered foreground script can hide
  progress.
- **Clean up** test playbooks you create if the user didn't ask for them to persist
  (`DELETE /v1/symphony/playbooks/<uuid>`), or name them clearly (e.g. prefix with
  your purpose) so they're easy to find.

## Reference files

- `references/api.md` — every endpoint used here (run polling, standalone run,
  manual-trigger run, run details, node-runs, playbook CRUD, finding
  modules/actions), with request/response shapes and gotchas.
- `references/playbook-json.md` — playbook/node JSON structure, output branches,
  inter-node `{{ node.<id>.<field> }}` templating, and editor layout coordinates.
- `references/starlark-integration.md` — the Starlark Script integration: actions,
  script contract, return-based routing API, sandbox limits, worked examples.
- `scripts/sekoia.py` — the API helper described in Setup.
