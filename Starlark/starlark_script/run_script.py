import time
from typing import Any

from pydantic.v1 import BaseModel, Field
from sekoia_automation.action import Action

from .base import StarlarkModule
from .runtime import ScriptError, StarlarkScript

# Reserved key that tags the value a routing builder (`output`/`stop`) returns,
# so the runtime can tell "route to a branch" from "plain result data". A script
# returning a bare dict with this exact single key would collide; the name is
# chosen to make that effectively impossible.
ROUTE_MARKER = "__starlark_result__"


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


class BaseRunScriptAction(Action):
    """Runs a Starlark script and routes its `return` to an output branch.

    A bare `return <data>` fires `CENTER` (set by the subclass); `return
    output(name, data)` fires an arbitrary branch by name; `return stop(reason)`
    fires none (halts). Branch names are not restricted to the manifest-declared
    outputs: the engine routes purely by name against the node's wiring, and node
    outputs are editable in the playbook, so a script can target a hand-wired
    branch. A name wired to nothing simply stops the flow there.
    """

    CENTER: str = "default"
    module: StarlarkModule

    # sleep() budget: host-side pacing for poll loops. Bounded because the
    # Starlark VM has no preemption -- a runaway loop is otherwise capped only
    # by the platform action timeout. Per-call and cumulative-per-run caps.
    SLEEP_MAX_CALL: float = 30.0
    SLEEP_MAX_TOTAL: float = 240.0

    def run(self, params: RunScriptArguments) -> dict | None:
        try:
            script = StarlarkScript(params.script, primitives=self._primitives())
            returned = script.run(params.arguments)
        except ScriptError as error:
            self.error(str(error))
            return None

        return self._route(returned)

    def _primitives(self) -> dict[str, Any]:
        def log(message: Any) -> None:
            self.log(str(message), level="info")

        def output(name: Any, data: Any = None) -> dict:
            return {ROUTE_MARKER: {"branch": str(name), "data": data}}

        def stop(reason: Any = None) -> dict:
            return {ROUTE_MARKER: {"branch": None, "reason": reason, "data": None}}

        slept = [0.0]

        def sleep(seconds: Any = 0) -> None:
            """Pause host-side for `seconds` (float). For pacing poll loops over
            async APIs. Bounded per call and per run; raises if the run's sleep
            budget is exhausted (bound your loop)."""
            try:
                secs = float(seconds)
            except (TypeError, ValueError):
                raise ValueError("sleep(seconds): seconds must be a number")
            if secs < 0:
                raise ValueError("sleep(seconds): seconds must be >= 0")
            secs = min(secs, self.SLEEP_MAX_CALL)
            if slept[0] + secs > self.SLEEP_MAX_TOTAL:
                raise RuntimeError(
                    "sleep budget exhausted: %gs total per run -- bound your poll loop"
                    % self.SLEEP_MAX_TOTAL
                )
            slept[0] += secs
            time.sleep(secs)
            return None

        return {"log": log, "output": output, "stop": stop, "sleep": sleep}

    def _route(self, returned: Any) -> dict | None:
        if isinstance(returned, dict) and len(returned) == 1 and ROUTE_MARKER in returned:
            spec = returned[ROUTE_MARKER]
            branch = spec.get("branch")
            if branch is None:
                reason = spec.get("reason")
                if reason is not None:
                    self.log(f"flow stopped: {reason}", level="info")
                # Suppress the center branch without activating another: nothing
                # fires, so the playbook halts here.
                self.set_output(self.CENTER, False)
                return None
            self.set_output(branch, True)
            return self._as_results(spec.get("data"))

        self.set_output(self.CENTER, True)
        return self._as_results(returned)

    @staticmethod
    def _as_results(value: Any) -> dict:
        # Action results must be a JSON object; wrap a scalar/list/None return so a
        # script can still return e.g. a list without tripping result validation.
        if isinstance(value, dict):
            return value
        return {"result": value}


class RunScriptAction(BaseRunScriptAction):
    name = "Run Starlark Script"
    description = (
        "Execute a Starlark (Python-like) script to transform or filter data, "
        "replacing a graph of nodes with a single script."
    )
    CENTER = "default"


class RunScriptBranchesAction(BaseRunScriptAction):
    name = "Run Starlark Script (branches)"
    description = (
        "Execute a Starlark (Python-like) script that transforms data and routes the "
        "flow to one of three branches (left / center / right)."
    )
    # `main` is the centered primary. Not named "default" on purpose (the platform
    # pins a branch named "default" to the edge, preventing a centered layout).
    CENTER = "main"
