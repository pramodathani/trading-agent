"""Tests for the desk command catalogue and GET /api/desks/{desk}/commands."""

import asyncio

import fastapi.testclient

from trading_agent.configuration import agent_configuration
from trading_agent.gateway import access_guard
from trading_agent.gateway import gateway_application
from trading_agent.runtime import desk_runtime
from trading_agent.runtime import event_bus as event_bus_module
from trading_agent.runtime import no_model_turn_runner
from trading_agent.runtime import slash_commands

_TOKEN = 'test-token-that-is-long-enough-1234567890'


class _StandInSkill:
    """A skill with only a name and a description.

    Attributes:
        name: The skill's name.
        description: What it is for.
    """

    def __init__(self, name: str, description: str):
        """Creates the skill.

        Args:
            name (str): The skill's name.
            description (str): What it is for.
        """
        self.name = name
        self.description = description


class _StandInSkillLibrary:
    """A skill library with a fixed list of skills."""

    def available(self) -> list[_StandInSkill]:
        """The usable skills.

        Returns:
            list[_StandInSkill]: One skill, and one that shares a built-in command's name.
        """
        return [
            _StandInSkill('opening-range', 'Trade the first range.'),
            _StandInSkill('status', 'Shadows /status.'),
        ]


class TestCommandCatalogue:
    """Tests for the list behind the command menus."""

    def test_skills_follow_the_commands(self) -> None:
        """Usable skills are listed after the commands, except one that a command shadows."""
        commands = slash_commands.SlashCommands(
            None,
            'dry_run',
            skill_library=_StandInSkillLibrary(),
        )

        catalogue = commands.catalogue()

        skills = []
        for entry in catalogue:
            if entry['kind'] == 'skill':
                skills.append(entry['name'])
        assert skills == [
            '/opening-range',
        ]
        assert catalogue[0]['name'] == '/status'

    def test_help_still_lists_every_line(self) -> None:
        """/help prints each catalogue line with its usage padded to 20 characters."""
        commands = slash_commands.SlashCommands(None, 'dry_run')

        help_text = asyncio.run(commands.handle('/help'))

        assert help_text.startswith(
            '/status              what the desk is doing'
        )
        assert '/<skill-name> ...    ask the desk' in help_text


class TestCommandsRoute:
    """Tests for the route the command menus read."""

    def test_route_lists_commands_with_how_they_run(self) -> None:
        """The route lists the built-in commands with how each one runs."""
        event_bus = event_bus_module.EventBus()
        desks = {
            'general': desk_runtime.DeskRuntime(
                agent_configuration.DeskConfiguration(name='general'),
                event_bus,
                no_model_turn_runner.NoModelTurnRunner(),
            ),
        }
        gateway = gateway_application.GatewayApplication(
            event_bus,
            desks,
            access_guard.AccessGuard(_TOKEN),
        )
        with fastapi.testclient.TestClient(gateway.build()) as client:
            response = client.get(
                '/api/desks/general/commands',
                headers={
                    'Authorization': f'Bearer {_TOKEN}',
                },
            )

        assert response.status_code == 200
        commands = {}
        for entry in response.json()['commands']:
            commands[entry['usage']] = entry
        assert commands['/status']['runs'] == 'at_once'
        assert commands['/btw <question>']['runs'] == 'beside'
        assert commands['/new']['runs'] == 'queued'
        assert commands['/stop']['runs'] == 'at_once'
        assert '/<skill-name> ...' not in commands
