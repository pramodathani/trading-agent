"""The delegate_task tool: hands one to four self-contained tasks to subagents, which run side by side.

Typical usage example:

  tool = DelegateTaskTool(subagent_runner)
"""

import pydantic

from trading_agent.extensions import untrusted_text
from trading_agent.subagents import subagent_definition
from trading_agent.subagents import subagent_runner as subagent_runner_module
from trading_agent.tools import tool


class DelegatedTask(pydantic.BaseModel):
    """One task for one subagent.

    Attributes:
        subagent: The subagent's name, from the Subagents section of your instructions.
        task: What it should do, with every fact it needs; it cannot see your conversation.
    """

    model_config = pydantic.ConfigDict(extra='forbid')

    subagent: str = pydantic.Field(min_length=1)
    task: str = pydantic.Field(min_length=1)


class DelegateTaskArguments(pydantic.BaseModel):
    """The arguments of delegate_task.

    Attributes:
        tasks: One to four tasks, run at the same time.
    """

    model_config = pydantic.ConfigDict(extra='forbid')

    tasks: list[DelegatedTask] = pydantic.Field(min_length=1, max_length=4)


class DelegateTaskTool(tool.Tool):
    """Runs subagent tasks and returns their reports."""

    name = 'delegate_task'
    description = "Hands one to four self-contained tasks to your subagents, listed in the Subagents section of your instructions. The tasks run at the same time, each with a fresh conversation that cannot see yours, so put every fact a task needs into its text. Use it for work that can be done separately, such as reading the news on several stocks at once or reviewing a trade. Returns each subagent's report. Subagents read outside sources, so check important claims before acting on them."
    arguments_model = DelegateTaskArguments
    timeout_seconds = subagent_definition.MAXIMUM_TIMEOUT_SECONDS + 60

    def __init__(self, runner: subagent_runner_module.SubagentRunner):
        """Creates the tool.

        Args:
            runner (subagent_runner_module.SubagentRunner): The desk's subagent runner.
        """
        self._runner = runner

    async def run(self, arguments: DelegateTaskArguments) -> tool.ToolResult:
        """Runs the tasks and joins their reports.

        Args:
            arguments (DelegateTaskArguments): The tasks.

        Returns:
            tool.ToolResult: One block per task; an error only when no task produced a report.
        """
        tasks = []
        for delegated in arguments.tasks:
            tasks.append(
                subagent_runner_module.SubagentTask(
                    subagent=delegated.subagent,
                    task=delegated.task,
                )
            )
        reports = await self._runner.run_all(tasks)
        blocks = []
        answered = 0
        for report in reports:
            heading = f'### {report.subagent}: {report.outcome}, {report.seconds:.0f} s'
            if report.backend_name:
                heading = f'{heading}, answered by {report.backend_name}'
            lines = [
                heading,
            ]
            for note in report.notes:
                lines.append(f'(note: {note})')
            if report.outcome == 'answered':
                answered += 1
                lines.append(
                    untrusted_text.UntrustedText().wrap(
                        f'the subagent {report.subagent}, which may have read outside sources',
                        report.text,
                    )
                )
            else:
                lines.append(report.text)
            blocks.append('\n'.join(lines))
        text = '\n\n'.join(blocks)
        if answered == 0:
            return tool.ToolResult.error(text)
        return tool.ToolResult.success(text)
