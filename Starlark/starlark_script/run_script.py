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


# The action's output branches, in left-to-right layout order for the playbook
# editor (`default` centered). Must stay in sync with the `outputs` map in
# action_run_script.json.
OUTPUTS = ("left", "default", "right")


class RunScriptAction(Action):
    name = "Run Starlark Script"
    description = (
        "Execute a Starlark (Python-like) script to transform data and route the flow, "
        "replacing a graph of nodes with a single script."
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
        """Host callables exposed to the script. `output` picks which of the three
        branches fires (pick-one; a later call replaces an earlier one); `stop`
        fires none, halting the flow; `log` records a message. If the script calls
        neither `output` nor `stop`, the centered `default` branch fires."""

        def log(message: Any) -> None:
            self.log(str(message), level="info")

        def output(name: Any) -> None:
            branch = str(name)
            if branch not in OUTPUTS:
                raise ValueError(
                    f"unknown output {branch!r}; valid outputs are: {', '.join(OUTPUTS)}"
                )
            # `default` fires implicitly only when no output is set, so a selection
            # must replace any prior one rather than accumulate (else two branches
            # fan out).
            self._outputs.clear()
            self.set_output(branch, True)

        def stop(reason: Any = None) -> None:
            if reason is not None:
                self.log(f"flow stopped: {reason}", level="info")
            # Suppress `default` without activating a side branch: nothing fires.
            self._outputs.clear()
            self.set_output("default", False)

        return {"log": log, "output": output, "stop": stop}

    @staticmethod
    def _as_results(value: Any) -> dict:
        # Action results must be a JSON object; wrap a scalar/list return so a
        # script can still return e.g. a list without tripping result validation.
        if isinstance(value, dict):
            return value
        return {"result": value}
