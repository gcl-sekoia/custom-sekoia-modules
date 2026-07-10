from typing import Any

from pydantic.v1 import BaseModel, Field
from sekoia_automation.action import Action

from .base import StarlarkModule
from .runtime import ScriptError, StarlarkScript


class RunScriptArguments(BaseModel):
    script: str = Field(
        ...,
        description="Starlark script defining `def main(arguments): ...` that returns "
        "the result. `arguments` is the input object below.",
    )
    arguments: dict[str, Any] = Field(
        default_factory=dict,
        description="Input object passed to the script as `arguments` (typically wired "
        "from previous playbook nodes).",
    )


class RunScriptAction(Action):
    name = "Run Starlark Script"
    description = (
        "Execute a Starlark (Python-like) script to transform data and route playbook "
        "branches, replacing a graph of nodes with a single script."
    )
    module: StarlarkModule

    def run(self, params: RunScriptArguments) -> dict | None:
        try:
            script = StarlarkScript(params.script, primitives=self._primitives())
            result = script.run(params.arguments)
        except ScriptError as error:
            self.error(str(error))
            return None

        return self._as_results(result)

    def _primitives(self) -> dict[str, Any]:
        """Host callables exposed to the script. `log` surfaces a message in the
        action logs; `set_output` activates a playbook output branch by name so a
        script can drive conditional routing."""

        def log(message: Any) -> None:
            self.log(str(message), level="info")

        def set_output(name: Any) -> None:
            self.set_output(str(name))

        return {"log": log, "set_output": set_output}

    @staticmethod
    def _as_results(value: Any) -> dict:
        # Action results must be a JSON object; wrap a scalar/list return so a
        # script can still return e.g. a list without tripping result validation.
        if isinstance(value, dict):
            return value
        return {"result": value}
