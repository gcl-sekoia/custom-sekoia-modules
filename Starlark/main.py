from starlark_script.base import StarlarkModule
from starlark_script.run_script import RunScriptAction

if __name__ == "__main__":
    module = StarlarkModule()
    module.register(RunScriptAction, "RunScriptAction")
    module.run()
