# Module structure & manifests

## Directory layout

A module lives in one directory (typically a subdir of a repo, e.g. `Starlark/`):

```
<ModuleDir>/
├── manifest.json                # the module (uuid, name, slug, version, config schema)
├── action_<name>.json           # one per action (arguments/outputs/results schema)
├── main.py                      # registers the Module + its actions; entrypoint
├── <package>/                   # the Python code (an importable package)
│   ├── __init__.py
│   ├── base.py                  # Module subclass (+ configuration model, if any)
│   └── <action>.py              # Action subclass(es)
├── pyproject.toml               # poetry project; pins sekoia-automation-sdk + deps
├── poetry.lock                  # required by the Dockerfile's `poetry install`
├── Dockerfile                   # builds the image the platform runs
├── logo.png                     # REQUIRED at module root — validation fails without it
├── CHANGELOG.md
└── tests/                       # pytest; not shipped in the image but expected in-repo
```

Copy `Starlark/` and rename rather than creating these from scratch — the
`pyproject.toml`, `Dockerfile`, and package wiring are easy to get subtly wrong.

## manifest.json (the module)

```json
{
  "configuration": {
    "title": "My Module configuration",
    "type": "object",
    "properties": { "api_key": {"title": "API key", "type": "string", "description": "..."} },
    "required": ["api_key"],
    "secrets": ["api_key"]
  },
  "description": "One-line description of the integration.",
  "name": "My Module",
  "uuid": "<unique uuid>",
  "slug": "my-module",
  "version": "1.0.0",
  "categories": ["Generic"],
  "supports_validation": false
}
```

- `configuration` is a JSON-Schema for the module's config; use `{"type":"object",
  "properties":{}}` if the module needs none. `secrets` lists which config fields are
  secret (fetched at run time, not stored in the playbook).
- `slug` matches `[a-z-]+`. `version` is semver and **drives the image tag** — bump
  it on every deployed change. `categories` from the platform's set (e.g. `Generic`,
  `Network`, `Endpoint`, `IAM`, `ThreatIntelligence`).

## action_<name>.json (one per action)

```json
{
  "name": "Do The Thing",
  "description": "What it does; note required permissions if any.",
  "uuid": "<unique uuid>",
  "docker_parameters": "DoTheThingAction",
  "arguments": {
    "title": "DoTheThingArguments",
    "type": "object",
    "properties": { "target": {"title": "Target", "type": "string", "description": "..."} },
    "required": ["target"]
  },
  "outputs": { "default": "Carries the results to the next node." },
  "results": {},
  "slug": "do_the_thing"
}
```

- `docker_parameters` is the command the platform runs the container with; it **must
  exactly match** the name the action class is `register()`ed under in `main.py`.
- `arguments` is a JSON-Schema mirroring the action's pydantic argument model.
- `outputs` maps branch name → description (an editor hint; a node can wire other
  names too — see the sekoia-playbooks skill). `results` is the output-data schema,
  or `{}` if dynamic/none.
- Every `uuid` (module and each action) must be globally unique on the platform.

## main.py (entrypoint & registration)

```python
from my_package.base import MyModule
from my_package.do_the_thing import DoTheThingAction

if __name__ == "__main__":
    module = MyModule()
    module.register(DoTheThingAction, "DoTheThingAction")   # name == action's docker_parameters
    module.run()
```

`module.run()` reads the command (argv/`SYMPHONY_RUNTIME` header) and dispatches to
the class registered under that `docker_parameters` name.

## pyproject.toml, Dockerfile, logo

- **pyproject.toml**: poetry-core build; `python = ">=3.11,<3.12"`;
  `sekoia-automation-sdk` (pin `1.22.3`; see `sdk.md` for why) with `extras=["all"]`;
  your runtime deps; dev deps `pytest`, `pytest-cov`. Copy Starlark's and edit.
- **poetry.lock**: generate with `poetry lock` (needs network); the Dockerfile
  `COPY`s it, so it must exist and match `pyproject.toml`.
- **Dockerfile**: `FROM python:3.11`, `pip install poetry`, `COPY poetry.lock
  pyproject.toml`, `poetry install --only main`, `COPY . .`, drop to a non-root user,
  `ENTRYPOINT ["python", "./main.py"]`. Copy Starlark's verbatim.
- **logo.png**: any valid PNG at the module root. A ~256×256 RGBA is fine; generate
  one with Pillow if none exists. Its absence is the single most common validation
  failure.
