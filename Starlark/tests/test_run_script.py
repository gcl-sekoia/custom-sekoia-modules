import pytest

from starlark_script.base import StarlarkModule
from starlark_script.run_script import RunScriptAction, RunScriptBranchesAction


@pytest.fixture
def action() -> RunScriptAction:
    return RunScriptAction(StarlarkModule())


@pytest.fixture
def branches() -> RunScriptBranchesAction:
    return RunScriptBranchesAction(StarlarkModule())


def test_return_data_fires_center_and_returns_results(action):
    results = action.run(
        {
            "script": "def main(arguments):\n    return {'sum': arguments['a'] + arguments['b']}\n",
            "arguments": {"a": 2, "b": 3},
        }
    )
    assert results == {"sum": 5}
    assert action.outputs == {"default": True}
    assert action.error_message is None


def test_scalar_return_is_wrapped(action):
    results = action.run({"script": "def main(arguments):\n    return 42\n"})
    assert results == {"result": 42}
    assert action.outputs == {"default": True}


def test_output_routes_arbitrary_branch_with_data(action):
    results = action.run(
        {"script": "def main(arguments):\n    return output('escalate', {'v': 7})\n"}
    )
    assert results == {"v": 7}
    assert action.outputs == {"escalate": True}


def test_output_without_data(action):
    results = action.run({"script": "def main(arguments):\n    return output('skip')\n"})
    assert results == {"result": None}
    assert action.outputs == {"skip": True}


def test_stop_halts_without_results(action):
    results = action.run({"script": "def main(arguments):\n    return stop('too low')\n"})
    assert results is None
    assert action.outputs == {"default": False}
    assert any("flow stopped: too low" in e["message"] for e in action.logs)


def test_stop_without_reason(action):
    results = action.run({"script": "def main(arguments):\n    return stop()\n"})
    assert results is None
    assert action.outputs == {"default": False}


def test_log_is_recorded(action):
    action.run({"script": "def main(arguments):\n    log('hello')\n    return {}\n"})
    assert any(e["message"] == "hello" for e in action.logs)


def test_bad_script_sets_error_and_returns_none(action):
    results = action.run({"script": "def main(arguments):\n    fail('boom')\n"})
    assert results is None
    assert "script raised an error" in action.error_message


def test_branches_return_data_fires_center(branches):
    results = branches.run({"script": "def main(arguments):\n    return {'k': 1}\n"})
    assert results == {"k": 1}
    assert branches.outputs == {"main": True}


@pytest.mark.parametrize("side", ["left", "right"])
def test_branches_output_routes_declared_side(branches, side):
    results = branches.run(
        {"script": f"def main(arguments):\n    return output('{side}', {{'v': arguments['v']}})\n", "arguments": {"v": 9}}
    )
    assert results == {"v": 9}
    assert branches.outputs == {side: True}
