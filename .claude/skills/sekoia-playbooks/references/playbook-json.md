# Playbook & node JSON structure

A playbook's graph lives in its `content.nodes` object: a map of **node id → node**.
Node ids are strings (`"0"`, `"1"`, `"2"`, …); assign your own when building.

## Node shape

```json
"0": {
  "name": "Run Starlark Script",
  "type": "action",
  "action_uuid": "c4ada6f6-0855-4e07-876e-f1a051cfa920",
  "module_uuid": "b94ba300-bd6d-41d5-924a-57ebddaa054a",
  "arguments": { "script": "...", "arguments": {} },
  "outputs": { "default": ["2"] },
  "position": { "x": 1500, "y": 1500 }
}
```

- **type**: `"trigger"` (entry point), `"action"` (calls an integration action), or
  `"operator"` (built-in condition/filter with a `cases` array).
- **action_uuid / module_uuid**: which action to run (from the action's manifest).
- **arguments**: the action's input arguments (matches the action's argument schema).
  String values here support templating (below).
- **outputs**: which downstream nodes each branch feeds — see next section.
- **position / icon**: layout only. Easiest to build a node by deep-copying an
  existing node of the same action and overwriting name/arguments/outputs/position.

## Trigger nodes & creating a trigger configuration

Every runnable playbook needs a trigger node, and that node needs a **trigger
configuration** resource. A blank new playbook has `trigger_configurations: []`, so
you must create one — this is the step that trips people up, because it must be
wired in **two places**.

The standard hand-run trigger is **Manual Trigger** (stable, platform-wide):
- `trigger_uuid`: `fc26eb9f-b272-4c15-b3bf-ace397c0dc57`
- `module_uuid`: `92d8bb47-7c51-445d-81de-ae04edbb6f0a`

(Under the hood it's `alert_webhook_trigger`, so its declared result schema mentions
`alert_uuid` — ignore that; you can emit any `event` object and read it downstream.)

Recipe:

```bash
# 1. Create the trigger configuration
./sekoia.py POST /v1/symphony/trigger-configurations \
  '{"name": "Manual Trigger", "trigger_uuid": "fc26eb9f-b272-4c15-b3bf-ace397c0dc57", "value": {}}'
# -> {"uuid": "<config_uuid>", ...}
```

Then wire it in **both** places when you PATCH the playbook:

```json
// (a) the trigger node in content.nodes
"0": {
  "name": "Manual Trigger",
  "type": "trigger",
  "trigger_uuid": "fc26eb9f-b272-4c15-b3bf-ace397c0dc57",
  "module_uuid": "92d8bb47-7c51-445d-81de-ae04edbb6f0a",
  "trigger_configuration_uuid": "<config_uuid>",
  "outputs": { "default": ["1"] }
}

// (b) the playbook's TOP-LEVEL trigger_configurations array
"trigger_configurations": [
  { "uuid": "<config_uuid>", "trigger_uuid": "fc26eb9f-b272-4c15-b3bf-ace397c0dc57" }
]
```

A freshly-created, trigger-wired but not-yet-activated playbook reports
`status_tags: ["configuration_issues"]` — this is expected and clears on
`activate`; don't waste time debugging it. Once activated, run it by emitting to
`<config_uuid>` (see `api.md` → Manual Trigger).

## Output branches (wiring)

A node's `outputs` maps **branch name → list of downstream node ids**:

```json
"outputs": { "default": ["2"], "error": ["3"] }
```

Key facts (verified):
- The engine routes **purely by name-match**: when a node's run activates a branch
  called `X`, the nodes listed under `outputs["X"]` run next. One branch can feed
  several nodes; several branches can be active (fan-out).
- Branch names are **not validated against the action's manifest**. You can wire any
  name you like (e.g. `error`, `quarantine`) as long as the action activates it at
  runtime. The manifest `outputs` only tells the *editor* which sockets to pre-draw.
- A branch literally named `default` is special-cased by the editor to a fixed edge
  position (and rendered without a label) — don't use `default` if you want a
  centered/labelled branch.
- A node whose action fails activates an `error` branch automatically; wire it to
  build error-handling paths.

## Passing data between nodes (templating)

Data and routing are independent channels. A node produces **one** `results` object
(the action's return), addressable from any downstream node by the node's id:

```
{{ node.0.count }}            # a field of node 0's results
{{ node.0.items }}            # a nested value; whole objects/lists work too
```

- Put these templates inside the downstream node's `arguments`. They resolve at run
  time against upstream `results`.
- A single, whole-value `{{ node.0.n }}` **preserves the JSON type** (an int stays an
  int, a list stays a list) — you don't have to re-parse strings.
- Data persists for the whole run keyed by node id, so a node several hops later can
  still reference an earlier node's output, not just its immediate parent.

## Editor layout coordinates

Nodes render as **350×86** blocks. The graph flows **vertically**:
- The next sequential node sits at the **same `x`**, `y + 200` (e.g. 1500,1500 →
  1500,1700).
- Branch fan-out spreads **horizontally** in `x` at the next `y` level; use ≥ ~400px
  x-spacing so the 350-wide blocks don't overlap (e.g. center on the parent's x,
  sides at `x - 400` and `x + 400`).

Positions are cosmetic (they don't affect execution) but good spacing makes a
playbook readable when the user opens it.

## Minimal build recipe

1. Create the playbook: `POST /v1/symphony/playbooks` with
   `{"playbook": {"name": "...", "description": ""}}` → returns its `uuid`.
2. Create a trigger configuration (see the trigger section above) → `<config_uuid>`.
3. Build `content.nodes`: a trigger node (wired with `trigger_configuration_uuid`),
   your action nodes, and each node's `outputs`. Use `{{ node.<id>.<field> }}` in
   later nodes' `arguments` to consume earlier results.
4. `PATCH /v1/symphony/playbooks/<uuid>` with `{"playbook": {..., "nodes": {...},
   "trigger_configurations": [{"uuid": "<config_uuid>", "trigger_uuid": "..."}]}}`.
5. Activate, then emit to `<config_uuid>` (see `api.md`), find the run, and read each
   node's status, outputs and results to confirm.

Tip: fetching an existing playbook that already uses the action/trigger you want
gives you a correct node to deep-copy — faster than assembling one field by field.
