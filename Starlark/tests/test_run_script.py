import pytest

from starlark_script.base import StarlarkModule
from starlark_script.run_script import RunScriptAction


@pytest.fixture
def action() -> RunScriptAction:
    return RunScriptAction(StarlarkModule())


def test_transform_returns_results_dict(action):
    results = action.run(
        {
            "script": "def main(arguments):\n    return {'sum': arguments['a'] + arguments['b']}\n",
            "arguments": {"a": 2, "b": 3},
        }
    )
    assert results == {"sum": 5}
    assert action.error_message is None


def test_scalar_return_is_wrapped(action):
    results = action.run({"script": "def main(arguments):\n    return 42\n"})
    assert results == {"result": 42}


def test_default_branch_fires_when_nothing_selected(action):
    action.run({"script": "def main(arguments):\n    return {}\n"})
    assert action.outputs == {}


@pytest.mark.parametrize("branch", ["left", "right", "default"])
def test_output_selects_single_branch(action, branch):
    action.run({"script": f"def main(arguments):\n    output('{branch}')\n    return {{}}\n"})
    assert action.outputs == {branch: True}


def test_last_output_wins(action):
    action.run(
        {"script": "def main(arguments):\n    output('left')\n    output('right')\n    return {}\n"}
    )
    assert action.outputs == {"right": True}


def test_unknown_output_raises(action):
    results = action.run({"script": "def main(arguments):\n    output('middle')\n    return {}\n"})
    assert results is None
    assert "unknown output 'middle'" in action.error_message


def test_stop_withholds_all_branches(action):
    script = (
        "def main(arguments):\n"
        "    if arguments['score'] < 50:\n"
        "        stop('score too low')\n"
        "    return {}\n"
    )
    action.run({"script": script, "arguments": {"score": 10}})
    assert action.outputs == {"default": False}
    assert any("flow stopped: score too low" in e["message"] for e in action.logs)


def test_stop_without_reason(action):
    action.run({"script": "def main(arguments):\n    stop()\n    return {}\n"})
    assert action.outputs == {"default": False}


def test_log_is_recorded(action):
    action.run({"script": "def main(arguments):\n    log('hello')\n    return {}\n"})
    assert any(entry["message"] == "hello" for entry in action.logs)


def test_bad_script_sets_error_and_returns_none(action):
    results = action.run({"script": "def main(arguments):\n    fail('boom')\n"})
    assert results is None
    assert "script raised an error" in action.error_message
