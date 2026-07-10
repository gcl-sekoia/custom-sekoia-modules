import time

import pytest

from starlark_script.base import StarlarkModule
from starlark_script.run_script import BaseRunScriptAction, RunScriptAction


@pytest.fixture
def action() -> RunScriptAction:
    return RunScriptAction(StarlarkModule())


def test_sleep_pauses_and_returns(action):
    t0 = time.time()
    results = action.run(
        {"script": "def main(arguments):\n    sleep(0.3)\n    return {'ok': True}\n", "arguments": {}}
    )
    assert results == {"ok": True}
    assert time.time() - t0 >= 0.3
    assert action.error_message is None


def test_sleep_rejects_negative(action):
    assert action.run({"script": "def main(arguments):\n    sleep(-1)\n    return 1\n", "arguments": {}}) is None
    assert "must be >= 0" in action.error_message


def test_sleep_rejects_non_number(action):
    assert action.run({"script": "def main(arguments):\n    sleep('x')\n    return 1\n", "arguments": {}}) is None
    assert "must be a number" in action.error_message


def test_sleep_budget_exhausted(monkeypatch, action):
    monkeypatch.setattr(BaseRunScriptAction, "SLEEP_MAX_TOTAL", 1.0)
    result = action.run(
        {"script": "def main(arguments):\n    for i in range(10):\n        sleep(0.4)\n    return {'ok': True}\n", "arguments": {}}
    )
    assert result is None
    assert "budget exhausted" in action.error_message


def test_percall_cap_does_not_exceed(monkeypatch, action):
    # a single sleep is capped per call, so it never sleeps longer than SLEEP_MAX_CALL
    monkeypatch.setattr(BaseRunScriptAction, "SLEEP_MAX_CALL", 0.2)
    t0 = time.time()
    action.run({"script": "def main(arguments):\n    sleep(5)\n    return 1\n", "arguments": {}})
    assert time.time() - t0 < 1.0
