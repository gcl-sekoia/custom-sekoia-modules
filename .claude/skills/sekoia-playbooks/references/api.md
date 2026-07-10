# Sekoia Symphony API reference

Base URL `https://app.sekoia.io/api`. Auth header
`Authorization: Bearer $SEKOIA_PURPLE_LAB_API_TOKEN`. These endpoints are mostly
undocumented (not in the public OpenAPI spec); they are verified working.

## Table of contents
- Polling runs to completion
- Running a single action (standalone)
- Playbook CRUD
- Running a playbook via a Manual Trigger
- Reading run results / debugging
- Finding modules & actions

## Polling runs to completion

Action runs and playbook runs are asynchronous: a POST returns a `node_run_uuid`
or a playbook run you must find, then you poll until terminal.

- Node runs: `GET /v1/symphony/node-runs/<uuid>` → terminal `status` `finished` /
  `error` (lowercase).
- Playbook runs: `GET /v1/symphony/playbook-runs/<uuid>` → same lowercase statuses.

`./sekoia.py watch <path>` polls either until terminal. Cold-starting an action
container can take 30–60s the first time; keep polling.

## Running a single action (standalone)

The quickest way to execute one action with no playbook/trigger:

```
POST /v1/symphony/actions/<action_uuid>/run
{"arguments": { ...action arguments... }, "module_configuration_uuid": "<optional>"}
-> 200 {"node_run_uuid": "..."}
```

Then poll the node run:

```
GET /v1/symphony/node-runs/<node_run_uuid>
-> {"status","results","outputs","logs","error", ...}
```

`module_configuration_uuid` is optional for modules with no required config (like
the Starlark integration). Cold start of the action image can take 30–60s.

## Playbook CRUD

```
GET    /v1/symphony/playbooks/<uuid>            # full playbook incl. content.nodes
POST   /v1/symphony/playbooks                    # create
PATCH  /v1/symphony/playbooks/<uuid>             # update  (body: {"playbook": {...}})
DELETE /v1/symphony/playbooks/<uuid>             # delete
POST   /v1/symphony/playbooks/<uuid>/activate
POST   /v1/symphony/playbooks/<uuid>/deactivate
```

Both create and PATCH wrap the definition in `{"playbook": {...}}`. Minimal create:

```
POST /v1/symphony/playbooks
{"playbook": {"name": "My playbook", "description": ""}}   # -> {"uuid": "...", ...}
```

PATCH the same way with the fuller definition: `{"playbook": {"name", "nodes",
"trigger_configurations", ...}}`. The full node structure — and how to create and
wire a **trigger configuration** for a brand-new playbook (a required, easily-missed
step) — is in `playbook-json.md`. A playbook must be **activated** before a trigger
event will run it.

## Running a playbook via a Manual Trigger

A playbook needs a trigger node to run. If it has a **Manual Trigger** node, its
trigger configuration is in the playbook's top-level `trigger_configurations`
(`[{"uuid": "...", "trigger_uuid": "..."}]`). To *create* that configuration for a
new playbook, see `playbook-json.md` → "Trigger nodes & creating a trigger
configuration" (`POST /v1/symphony/trigger-configurations` with `name` +
`trigger_uuid`, then wire it onto the node and the top-level array).

```bash
# 1. activate (once)
./sekoia.py POST /v1/symphony/playbooks/<pb_uuid>/activate         # -> 204

# 2. emit an event to the manual trigger's configuration
./sekoia.py POST /v1/symphony/trigger-configurations/<trigger_config_uuid> \
  '{"event": {}, "playbook_uuid": "<pb_uuid>"}'                    # -> 204
```

`event` (required) is the initial payload; downstream nodes can read it via
`{{ node.<trigger_node_id>.<field> }}`. `playbook_uuid` scopes the emit to this one
playbook.

Then **find the run** (the emit returns 204 with no id):

```
GET /v1/symphony/playbook-runs?match[playbook_uuid]=<pb_uuid>&sort=started_at&direction=desc&limit=5
```

Poll the newest run's uuid until terminal (see next section). Tip: snapshot the set
of run uuids before emitting, then pick the one that appears after.

## Reading run results / debugging

```
GET /v1/symphony/playbook-runs/<run_uuid>            # run summary (has top-level status)
GET /v1/symphony/playbook-runs/<run_uuid>/details    # {playbook_run, playbook, node_runs}
GET /v1/symphony/node-runs/<node_run_uuid>           # one node's full result
```

The node-run body has `status`, `results`, `outputs`, `logs`, `error`. Note its
`arguments` field is the action's **argument schema** (titles/properties), NOT the
resolved values passed to this run — to confirm what a node actually received,
read the **upstream** node's `results`, not this `arguments`.

`details.node_runs` is a **dict keyed by node id**; each value is a list of run
entries, each with a node-run `uuid`, `status`, `outputs`, `error`. Fetch
`/node-runs/<uuid>` for that node's full `results` / `logs`. Only nodes that
actually ran appear in `node_runs` — an absent node id means its branch never fired
(useful for confirming routing).

Shape gotcha: in the `details` response, `details.playbook` is a **runtime snapshot**
with its nodes at the top level (`details.playbook.nodes`), NOT under
`content.nodes` — that `content.nodes` wrapper only exists on the playbook CRUD
endpoints. Don't reach for `details.playbook.content` (it isn't there); use
`details.node_runs` for statuses and `GET /v1/symphony/playbooks/<uuid>` if you need
the editable definition.

Debugging checklist:
- Node `status: error` → read its `error` (stack/message) and `logs`.
- A node that "finished" but downstream didn't run → check its `outputs`: only the
  wired-and-activated branch continues. `{"default": false}` (or any all-false) means
  the flow was deliberately halted.
- A failing action auto-emits an `error` output branch; wire a node to `error` to
  handle failures.
- Data not arriving downstream → verify the `{{ node.<id>.<field> }}` reference
  matches the upstream node's id and a real field in its `results`.

## Finding modules & actions

To wire an action into a playbook you need its uuid, `docker_parameters` and
argument schema. Discover them (read-only):

```
GET /v1/symphony/modules?limit=100      # list installed modules (integrations)
GET /v1/symphony/modules/<uuid>         # one module: name, version, docker image
GET /v1/symphony/actions/<uuid>         # an action: docker_parameters, arguments,
                                        #   declared outputs, module_uuid
```

Installing, building, or updating a custom integration from git is a separate
concern — see the Sekoia integration-authoring skill, not this one.
