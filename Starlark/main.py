from starlark_script.base import StarlarkModule
from starlark_script.http_action import RunScriptHttpAction
from starlark_script.run_script import RunScriptAction, RunScriptBranchesAction

if __name__ == "__main__":
    module = StarlarkModule()
    module.register(RunScriptAction, "RunScriptAction")
    module.register(RunScriptBranchesAction, "RunScriptBranchesAction")
    module.register(RunScriptHttpAction, "RunScriptHttpAction")
    module.run()
