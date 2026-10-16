"""The arguments shared by bash_run and bash_background.

Typical usage example:

  arguments = CommandArguments(command='ls -la')
"""

import pydantic


class CommandArguments(pydantic.BaseModel):
    """One bash command.

    Attributes:
        command: The command, as typed at a bash prompt.
    """

    model_config = pydantic.ConfigDict(extra='forbid')

    command: str = pydantic.Field(min_length=1)
