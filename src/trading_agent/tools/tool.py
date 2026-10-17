"""The base class for every tool the agent can use, and the result a tool returns.

A tool describes its arguments as a pydantic model. The model gives the JSON schema the AI model sees, and checks the arguments the AI model sends before the tool runs.

Typical usage example:

  class GetTimeTool(Tool):
      name = 'get_time'
      description = 'Returns the current date and time in India.'
      arguments_model = NoArguments

      async def run(self, arguments: NoArguments) -> ToolResult:
          return ToolResult.success('10:15')
"""

import dataclasses
from typing import Any, Self

import pydantic

from trading_agent.agent import messages


@dataclasses.dataclass(frozen=True)
class ToolResult:
    """What a tool returns to the model.

    Attributes:
        text: The output the model reads.
        is_error: Whether the tool failed, so the model knows to change course.
        image: A picture for the model to look at, such as a screenshot, or None.
        picture_desk_path: Where that picture is saved, relative to the desk folder, so the web page can show it in the tool's card; None when it is not saved in the desk folder.
    """

    text: str
    is_error: bool = False
    image: messages.MessageImage | None = None
    picture_desk_path: str | None = None

    @classmethod
    def success(cls, text: str) -> Self:
        """Creates a successful result.

        Args:
            text (str): The output.

        Returns:
            ToolResult: The result.
        """
        return cls(text=text, is_error=False)

    @classmethod
    def error(cls, text: str) -> Self:
        """Creates a failed result.

        Args:
            text (str): What went wrong, written so the model can act on it.

        Returns:
            ToolResult: The result.
        """
        return cls(text=text, is_error=True)


class NoArguments(pydantic.BaseModel):
    """The arguments of a tool that takes none."""

    model_config = pydantic.ConfigDict(extra='forbid')


class Tool:
    """One tool. Subclasses set the class attributes and override run.

    Attributes:
        name: The name the model calls the tool by.
        description: What the tool does, written for the model.
        arguments_model: The pydantic model that describes and checks the arguments.
        timeout_seconds: How long one call may run, or None for the registry's default.
    """

    name = ''
    description = ''
    arguments_model: type[pydantic.BaseModel] = NoArguments
    timeout_seconds: float | None = None

    def input_schema(self) -> dict[str, Any]:
        """The JSON schema of the tool's arguments, as the model sees it.

        Returns:
            dict[str, Any]: A JSON schema object.
        """
        schema = self.arguments_model.model_json_schema()
        schema.pop('title', None)
        schema.setdefault('properties', {})
        schema.setdefault('required', [])
        return schema

    async def run(self, arguments: pydantic.BaseModel) -> ToolResult:
        """Runs the tool.

        Args:
            arguments (pydantic.BaseModel): The checked arguments, an instance of arguments_model.

        Returns:
            ToolResult: The output.

        Raises:
            NotImplementedError: Always, because subclasses must override this method.
        """
        raise NotImplementedError

    async def close(self) -> None:
        """Releases anything the tool started, such as a bash process.

        Tools that start nothing keep this empty default.
        """
