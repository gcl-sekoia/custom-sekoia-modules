# Deploying & syncing a module from git

The platform builds a module from a git repo. These endpoints are undocumented (not
in the public OpenAPI spec) but verified. All are **async** → poll `GET /v1/tasks/
<task_uuid>` (path is `/v1/tasks/`, not `/symphony/...`) to terminal `FINISHED` /
`FAILED` (uppercase). `./sekoia.py watch /v1/tasks/<uuid>` does the polling.

## First deploy

```
POST /v1/symphony/modules/from-git
{"git": "https://github.com/<org>/<repo>", "branch": "<branch>",
 "path": "<subdir containing manifest.json>", "ssh_key_id": "<key uuid>"}
-> 202 {"task_uuid": "..."}
```

The task's `attributes.validation_steps` shows progress:

```
Cloning repository → Checking sub-path exists → Validating integration
→ Building docker image → Publish intake formats → Integration creation
```

On success the module is created with the `uuid` from its `manifest.json`.

**Validation ("Validating integration") checks** — the common failure causes:
- **`logo.png` at the module root** — missing is the most frequent failure
  (`"* logo.png: Logo is missing"`). Cloning/sub-path pass, then this fails.
- manifest fields (semver `version`, `slug`), a `main.py`, `pyproject.toml` + lock,
  and **unique UUIDs** (module + every action) across the platform.

If validation fails, the build step never runs — read the failing step's `error`/
`output`, fix in the repo, push, and re-run.

## Sync after pushing new commits

Two steps: check (read-only) then update (applies + rebuilds).

```
POST /v1/symphony/modules/<module_uuid>/check-for-updates
   -> task; attributes.commits lists commits on the branch not yet deployed ([] if none)
POST /v1/symphony/modules/<module_uuid>/update
   -> task; re-clones, re-validates, rebuilds the image ("Integration update")
```

The image tag derives from the manifest `version`, so **bump `version` before
`update`** or you may rebuild the same tag and not see your change.

Re-running `from-git` on an already-created module conflicts at the unique-UUID
check; use `check-for-updates` + `update` to change an existing module, `from-git`
only for the first install.

## Verify

```
GET /v1/symphony/modules/<module_uuid>     # .version and .docker (image tag) should reflect the new build
GET /v1/symphony/actions/<action_uuid>     # confirm new/changed actions + their outputs/arguments
```

Then smoke-test with a standalone action run (see the sekoia-playbooks skill,
"Running a single action") before declaring the change live.

## Progress signal without polling (optional)

A push websocket `wss://app.sekoia.io/live/` (send the `Authorization` header on
connect) emits `{"type":"task","attributes":{"id","status","attributes":{
"validation_steps"}}}`. You must connect **before** creating the task or you miss its
events, so for one-off deploys plain `/v1/tasks/<id>` polling is simpler.

## Known GCL specifics (this environment)

- `ssh_key_id` for `from-git`: `a5774fa4-e348-489b-9de6-6042d9263342`.
- Custom-modules repo: `https://github.com/gcl-sekoia/custom-sekoia-modules`
  (each module is a top-level subdir, e.g. `Starlark/` → `path: "Starlark"`).
- The Starlark module: uuid `b94ba300-bd6d-41d5-924a-57ebddaa054a`.
