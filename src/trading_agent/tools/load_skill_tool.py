"""The load_skill tool: reads one skill in full, so the desk can follow it.

Typical usage example:

  tool = LoadSkillTool(library)
"""

import pydantic

from trading_agent.skills import skill_library as skill_library_module
from trading_agent.tools import tool


class LoadSkillArguments(pydantic.BaseModel):
    """The arguments of load_skill.

    Attributes:
        name: The skill's name, as listed in the skills index.
    """

    model_config = pydantic.ConfigDict(extra='forbid')

    name: str = pydantic.Field(min_length=1)


class LoadSkillTool(tool.Tool):
    """Returns a skill's instructions and the paths of its bundled files."""

    name = 'load_skill'
    description = 'Loads one skill from the skills index in your instructions: its full step-by-step instructions and the paths of any scripts and reference files it comes with. Read reference files with read_file and run scripts with bash_run, using the absolute paths given. Load a skill before starting a task it covers.'
    arguments_model = LoadSkillArguments

    def __init__(self, library: skill_library_module.SkillLibrary):
        """Creates the tool.

        Args:
            library (skill_library_module.SkillLibrary): The desk's skills.
        """
        self._library = library

    async def run(self, arguments: LoadSkillArguments) -> tool.ToolResult:
        """Finds the skill and returns its text.

        Args:
            arguments (LoadSkillArguments): The skill's name.

        Returns:
            tool.ToolResult: The skill, or an error listing the skills there are.
        """
        skill = self._library.find(arguments.name)
        if skill is None:
            names = [available.name for available in self._library.available()]
            listing = ', '.join(names) or 'none'
            return tool.ToolResult.error(
                f'No usable skill named {arguments.name}. Skills available: {listing}.'
            )
        origin = (
            'one of your own skills'
            if skill.origin == 'agent'
            else "one of the user's installed skills"
        )
        lines = [
            f'Skill {skill.name} ({origin}), from {skill.directory.resolve()}:',
            '',
            skill.body,
        ]
        files = skill.bundled_files()
        if files:
            lines.append('')
            lines.append('Files that come with it:')
            for path in files:
                lines.append(f'- {path.resolve()}')
        return tool.ToolResult.success('\n'.join(lines))
