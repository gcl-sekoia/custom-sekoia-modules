import json

import pytest

from starlark_script.base import StarlarkModule
from starlark_script.run_script import RunScriptAction, format_time, parse_time
from starlark_script.http_action import RunScriptHttpAction


def test_parse_format_roundtrip():
    t = parse_time("2026-07-10T17:49:28Z")
    assert format_time(t) == "2026-07-10T17:49:28Z"
    assert format_time(t + 3600) == "2026-07-10T18:49:28Z"


def test_parse_relative_and_epoch():
    assert abs(parse_time("+1h") - parse_time("now") - 3600) < 5
    assert abs(parse_time("-30m") - parse_time("now") + 1800) < 5
    assert parse_time(1783705768) == 1783705768.0


def test_parse_time_bad_value_errors():
    with pytest.raises(ValueError):
        parse_time("not-a-time")


def test_time_primitives_in_script():
    a = RunScriptAction(StarlarkModule())
    r = a.run({"script": "def main(arguments):\n    t = parse_time('2026-01-01T00:00:00Z')\n"
                         "    return {'iso': format_time(t + 60), 'is_now_greater': now() > t}\n",
               "arguments": {}})
    assert r == {"iso": "2026-01-01T00:01:00Z", "is_now_greater": True}


def test_search_events_requires_credential():
    # no module config -> no 'sekoia_api' credential -> clear error, offline
    h = RunScriptHttpAction(StarlarkModule())
    h._config_dict = lambda: {}
    assert h.run({"script": "def main(arguments):\n    return {'n': len(search_events('x'))}\n",
                  "arguments": {}}) is None
    assert "sekoia_api" in h.error_message or "credential" in h.error_message


def test_sol_requires_credential():
    h = RunScriptHttpAction(StarlarkModule())
    h._config_dict = lambda: {}
    assert h.run({"script": "def main(arguments):\n    return {'rows': sol('events | count')}\n",
                  "arguments": {}}) is None
    assert "sekoia_api" in h.error_message or "credential" in h.error_message
