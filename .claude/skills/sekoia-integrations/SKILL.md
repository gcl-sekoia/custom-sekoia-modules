---
name: sekoia-integrations
description: >-
  Build, install, and iterate on custom Sekoia (Sekoia.io / Symphony) integrations
  (modules) — the Python packages, built from git into Docker images, that provide
  the actions/triggers playbooks call. Use this whenever the user wants to create a
  new Sekoia integration or module, add or change an action/trigger, scaffold or edit
  manifest.json / action_*.json, work with the sekoia-automation-sdk (Module/Action
  classes), deploy a module from a git repo, or push a change live to the platform
  (from-git / check-for-updates / update) — even if they don't name the API. For
  building/running/debugging playbooks that *use* these actions, use the
  sekoia-playbooks skill instead.
---

# Sekoia custom integrations

A Sekoia **integration** is a **module**: a Python package (using
`sekoia-automation-sdk`) plus JSON manifests, kept in a git repo. The platform
clones it, builds a Docker image, and exposes its **actions**/**triggers** for
playbooks to call. This skill covers the whole lifecycle: author the code +
manifests, test locally, then deploy and keep it in sync from git.

`Starlark/` in the `gcl-sekoia/custom-sekoia-modules` repo is a complete, working
module — the best template to copy from and the running example in the references.

## The lifecycle (end to end)

1. **Scaffold** the module directory (fastest: copy an existing module and rename).
   Layout, and every file's purpose, is in `references/module-structure.md`.
2. **Implement** the `Module` and `Action` classes with pydantic argument models,
   using the SDK contract in `references/sdk.md`.
3. **Write the manifests** — `manifest.json` (the module) and one `action_*.json`
   per action — keeping them in sync with the code (`docker_parameters`, UUIDs,
   argument schema). Schemas are in `references/module-structure.md`.
4. **Add the required extras**: a `logo.png` at the module root (validation fails
   without it), `CHANGELOG.md`, `pyproject.toml` + lock, `Dockerfile`.
5. **Test locally** — build a venv and run pytest before deploying (below).
6. **Commit and push** to a branch of the module's repo. (If `git commit` fails
   with an SSH signing error like "failed to write commit object" / "agent has no
   identities", the signing key isn't loaded — ask the user to run
   `ssh-add ~/.ssh/git_signing_key`; don't disable signing.)
7. **Deploy or sync** to the platform (`references/deploy-and-sync.md`): `from-git`
   the first time; `check-for-updates` + `update` after each push (bump the manifest
   `version` to force a new image).
8. **Verify**: GET the module (version/image changed) and smoke-test the action with
   a standalone run. Running/wiring actions in playbooks is the **sekoia-playbooks**
   skill's job — hand off there once the module is live.

## Setup: the API helper

Platform calls use the bundled `scripts/sekoia.py` and the token in
`$SEKOIA_PURPLE_LAB_API_TOKEN` (base `https://app.sekoia.io/api`):

```bash
./sekoia.py POST /v1/symphony/modules/from-git '{"git": "...", "branch": "...", "path": "...", "ssh_key_id": "..."}'
./sekoia.py watch /v1/tasks/<task_uuid>            # poll a module task to FINISHED/FAILED
./sekoia.py GET  /v1/symphony/modules/<uuid>       # verify version + docker image tag
```

It reads the token, prepends the base URL, pretty-prints JSON, and prints the HTTP
status to stderr. Module operations are **async**: they return `{"task_uuid": ...}`;
poll `GET /v1/tasks/<uuid>` (path is `/v1/tasks/`, NOT `/symphony/...`) to terminal
`FINISHED`/`FAILED`, reading `attributes.validation_steps` for progress.

## Testing locally before you deploy

Deploys build a Docker image and run a vulnerability scan — slow, and a bad build
wastes a cycle. Catch problems locally first:

```bash
cd <ModuleDir>
uv venv .venv --python 3.11
uv pip install --python .venv/bin/python "sekoia-automation-sdk==1.22.3" "pydantic==2.10" pytest <module deps>
.venv/bin/python -m pytest -q
.venv/bin/python -c "import main"     # main.py imports + registers cleanly
```

Pin `sekoia-automation-sdk==1.22.3` + `pydantic==2.10` — **SDK 1.23 migrated to
pydantic v2 and breaks the pydantic.v1 argument models this SDK generation uses**
(see `references/sdk.md`). Installing genuinely new dependencies needs network; if
the environment blocks PyPI, ask the user to `uv sync` / `pip install` outside and
then run tests with `--offline`.

## Working style

- **Copy, don't hand-assemble.** Start from `Starlark/` (or another module): the
  package layout, `pyproject.toml`, `Dockerfile`, and manifest shapes are fiddly and
  easy to get subtly wrong. Rename, swap UUIDs, and edit from there.
- **New UUIDs for new things.** Every module and action needs a unique UUID
  (`python3 -c "import uuid; print(uuid.uuid4())"`); reusing one collides at the
  "unicity of UUIDs" validation step. `docker_parameters` in an action JSON must
  exactly match the name it's `register()`ed under in `main.py`.
- **Bump `version` on every change you deploy** — the image tag derives from it, so
  an unchanged version can rebuild the same tag and mask your change.
- **Verify after deploy.** GET the module and confirm `.version` / `.docker` moved,
  then run the action standalone before declaring success.

## Reference files

- `references/module-structure.md` — the module directory, every file's role, and
  the `manifest.json` / `action_*.json` schemas, with the `main.py` registration.
- `references/sdk.md` — the `sekoia-automation-sdk` contract: `Module` / `Action`,
  `run` + pydantic argument/result models, `results`, `set_output`/`outputs`, `log`,
  errors, module configuration + secrets, and the pydantic-version pin.
- `references/deploy-and-sync.md` — `from-git`, `check-for-updates`, `update`, task
  watching, validation steps, requirements (`logo.png`), and verification.
- `scripts/sekoia.py` — the API helper.
