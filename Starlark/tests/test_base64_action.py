import pytest

from starlark_script.base import StarlarkModule
from starlark_script.base64_action import Base64Action


@pytest.fixture
def action() -> Base64Action:
    return Base64Action(StarlarkModule())


def test_encode_returns_base64_string(action):
    results = action.run({"mode": "encode", "text": "hello world"})
    assert results == {"result": "aGVsbG8gd29ybGQ="}
    assert action.error_message is None


def test_decode_returns_original_string(action):
    results = action.run({"mode": "decode", "text": "aGVsbG8gd29ybGQ="})
    assert results == {"result": "hello world"}
    assert action.error_message is None


def test_decode_invalid_base64_sets_error_and_returns_none(action):
    results = action.run({"mode": "decode", "text": "not-valid-base64!!"})
    assert results is None
    assert "could not decode input as base64" in action.error_message


@pytest.mark.parametrize("mode", ["ENCODE", "invalid", ""])
def test_invalid_mode_is_rejected_by_argument_validation(action, mode):
    with pytest.raises(Exception):
        action.run({"mode": mode, "text": "hello"})
