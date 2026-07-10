import pytest

from starlark_script.runtime import ScriptError, StarlarkScript


def test_main_returns_dict():
    script = StarlarkScript("def main(arguments):\n    return {'ok': True}\n")
    assert script.run({}) == {"ok": True}


def test_arguments_are_passed_through():
    source = "def main(arguments):\n    return {'greeting': 'hi ' + arguments['name']}\n"
    assert StarlarkScript(source).run({"name": "alice"}) == {"greeting": "hi alice"}


def test_json_and_comprehension_builtins_available():
    source = (
        "def main(arguments):\n"
        "    doubled = [x * 2 for x in arguments['nums']]\n"
        "    return {'encoded': json.encode(doubled)}\n"
    )
    assert StarlarkScript(source).run({"nums": [1, 2, 3]}) == {"encoded": "[2,4,6]"}


def test_list_return_is_preserved():
    assert StarlarkScript("def main(arguments):\n    return [1, 2, 3]\n").run({}) == [1, 2, 3]


def test_injected_primitive_is_callable():
    calls = []
    script = StarlarkScript(
        "def main(arguments):\n    record('seen')\n    return {}\n",
        primitives={"record": calls.append},
    )
    script.run({})
    assert calls == ["seen"]


def test_syntax_error_raises_script_error():
    with pytest.raises(ScriptError, match="failed to compile"):
        StarlarkScript("def main(arguments)\n    return {}\n")


def test_reference_to_unknown_name_fails_at_compile():
    with pytest.raises(ScriptError, match="failed to compile"):
        StarlarkScript("def main(arguments):\n    return undefined_name\n")


def test_runtime_error_raises_script_error():
    with pytest.raises(ScriptError, match="script raised an error"):
        StarlarkScript("def main(arguments):\n    fail('boom')\n").run({})


def test_missing_entrypoint_reports_helpful_message():
    script = StarlarkScript("x = 1\n")
    with pytest.raises(ScriptError, match="must define an entrypoint"):
        script.run({})


def test_load_is_rejected():
    with pytest.raises(ScriptError, match="failed to compile"):
        StarlarkScript("load('other.star', 'x')\ndef main(arguments):\n    return {}\n")
