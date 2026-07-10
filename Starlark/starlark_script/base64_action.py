import base64
import binascii
from typing import Literal

from pydantic.v1 import BaseModel, Field
from sekoia_automation.action import Action

from .base import StarlarkModule


class Base64Arguments(BaseModel):
    mode: Literal["encode", "decode"] = Field(
        ..., description="Whether to base64-encode or base64-decode `text`."
    )
    text: str = Field(..., description="The input text to encode or decode.")


class Base64Action(Action):
    name = "Base64 Encode/Decode"
    description = "Base64-encode or base64-decode a string."
    module: StarlarkModule

    def run(self, arguments: Base64Arguments) -> dict | None:
        if arguments.mode == "encode":
            result = base64.b64encode(arguments.text.encode()).decode()
        else:
            try:
                result = base64.b64decode(arguments.text).decode()
            except (binascii.Error, UnicodeDecodeError) as error:
                self.error(f"could not decode input as base64: {error}")
                return None

        return {"result": result}
