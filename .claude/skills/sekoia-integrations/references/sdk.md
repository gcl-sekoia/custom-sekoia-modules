# sekoia-automation-sdk contract

The SDK (`from sekoia_automation ...`) gives you `Module` and `Action` base classes.
An action is a Python class with a `run` method; the platform runs your image with
the action's `docker_parameters` as the command, the SDK dispatches to your class,
feeds it the arguments, and ships back your return value + logs + output branches.

## The pydantic version pin (read this first)

- **SDK `1.22.3`** validates action arguments with `pydantic.v1`. Argument/result
  models are written `from pydantic.v1 import BaseModel, Field`.
- **SDK `1.23+`** migrated to pydantic **v2** (`validate_call`), which raises on a
  pydantic.v1 model (`BaseModel.validate() takes 2 positional arguments but 3 were
  given`).

Pin `sekoia-automation-sdk==1.22.3` and `pydantic==2.10`, and write models with
`pydantic.v1`, to match the existing modules in this repo. (If you deliberately
target the newer SDK, write v2-native models instead — but keep the whole module on
one generation.)

## Module

```python
from pydantic.v1 import BaseModel, Field
from sekoia_automation.module import Module

class MyConfiguration(BaseModel):
    api_key: str = Field(secret=True, description="...")

class MyModule(Module):
    configuration: MyConfiguration      # omit entirely if the module needs no config
```

`self.module.configuration` is the parsed config at run time. Config fields listed
under `configuration.secrets` in `manifest.json` are fetched securely when the action
starts (`Field(secret=True)` marks them in the model).

## Action

```python
from typing import Any
from pydantic.v1 import BaseModel, Field
from sekoia_automation.action import Action
from .base import MyModule

class DoTheThingArguments(BaseModel):
    target: str = Field(..., description="...")

class DoTheThingAction(Action):
    name = "Do The Thing"                 # class attrs; mirror the action JSON
    description = "..."
    module: MyModule

    def run(self, arguments: DoTheThingArguments) -> dict | None:
        # arguments is the validated model (the SDK coerces the incoming dict)
        result = {"echo": arguments.target}
        return result                     # must be a JSON object (dict) or list
```

Key behaviours:
- **`run(self, arguments: Model)`** — the SDK wraps `run` so the incoming dict is
  validated/coerced into your annotated pydantic model. Return a **dict** (or list);
  a scalar/None return is treated as invalid results and dropped, so wrap it
  (`{"result": value}`) if a script/computation might yield one.
- **`self.log(message, level="info")`** — records a line surfaced in the node-run
  `logs`. Levels: `debug`/`info`/`warning`/`error`/`critical`.
- **`self.error(message)`** — ends the action with an error (the node-run shows
  `status: error`). Prefer a clear, self-contained message; it's read without the
  source.
- **`self.set_output(name, activate=True)`** — activates an output branch `name`
  (sent as the node-run's `outputs`). If you never call it, the platform fires the
  implicit `default` branch. Activating any named branch suppresses the implicit
  default, so a node that sets, say, `set_output("high")` will NOT also fire
  `default`. Routing/branch semantics on the playbook side are documented in the
  sekoia-playbooks skill; here you just need: *set the branch(es) you want fired.*
- **async actions**: for `async def run`, override `execute` to `asyncio.run(...)` it
  (see `AzureActiveDirectory`), or keep `run` synchronous.

## Registration & dispatch

`main.py` does `module.register(ActionClass, "DockerParamName")` then `module.run()`.
The register name **must equal** the action JSON's `docker_parameters`. At run time
the platform invokes the container with that name as the command; `module.run()`
dispatches to the matching class. A mismatch means "Could not find any Action or
Trigger matching command".

## Designing a higher-level script API (optional pattern)

`set_output` is low-level. If an action takes user logic (like the Starlark module),
you can hide it behind a cleaner surface — e.g. the Starlark action lets a script
express routing purely through its `return` (`return output(name, data)` /
`return stop()`), and the action translates that into `set_output` + results
internally. Useful when the action's users shouldn't have to learn the SDK.

## Tests

Instantiate the action with the module and call `run` directly — no platform needed
(network only happens in `execute()`):

```python
def test_it():
    action = DoTheThingAction(MyModule())
    assert action.run({"target": "x"}) == {"echo": "x"}
    assert action.outputs == {}            # or {"branch": True} after set_output
    assert action.error_message is None
```

Follow the argument-model annotation so the SDK validates inputs the same way it will
in production. Keep tests behaviour-focused (one behaviour each) and fast.
