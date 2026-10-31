"""Tests for skills: the format, the library, the writer, imports, usage, the curator and /<skill-name>."""

import asyncio
import datetime
import json
import os
import zipfile
from pathlib import Path

import pytest

from trading_agent.memory import checkpoints as checkpoints_module
from trading_agent.runtime import event as event_module
from trading_agent.runtime import event_bus as event_bus_module
from trading_agent.runtime import slash_commands
from trading_agent.skills import skill as skill_module
from trading_agent.skills import skill_curator
from trading_agent.skills import skill_importer
from trading_agent.skills import skill_library
from trading_agent.skills import skill_usage
from trading_agent.skills import skill_writer
from trading_agent.tools import bash_sandbox
from trading_agent.tools import load_skill_tool
from trading_agent.workspace import workspace_layout


def _write_skill(
    directory: Path,
    name: str,
    description: str = 'Does a thing.',
    extra_frontmatter: str = '',
    body: str = '# Steps\n1. Do it.',
) -> Path:
    """Writes a SKILL.md into a new folder.

    Args:
        directory (Path): The parent folder.
        name (str): The skill's name, also its folder name.
        description (str): Its description.
        extra_frontmatter (str): More YAML lines for the frontmatter.
        body (str): The instructions.

    Returns:
        Path: The skill's folder.
    """
    folder = directory / name
    folder.mkdir(parents=True)
    (folder / 'SKILL.md').write_text(
        f'---\nname: {name}\ndescription: {description}\n{extra_frontmatter}---\n{body}\n',
        encoding='utf-8',
    )
    return folder


class _Skills:
    """An installed folder, a trader folder, a library, checkpoints and a writer.

    Attributes:
        installed: The installed skills folder.
        trader_directory: The trader folder.
        library: The library.
        checkpoints: The trader's checkpoints.
        ledger: The ledger file.
        writer: The writer.
    """

    def __init__(self, root: Path):
        """Builds the parts in a scratch folder.

        Args:
            root (Path): The scratch folder.
        """
        self.installed = root / 'shared' / 'skills' / 'installed'
        self.trader_directory = root / 'trader'
        self.installed.mkdir(parents=True)
        self.trader_directory.mkdir()
        self.library = skill_library.SkillLibrary(
            self.installed,
            self.trader_directory / 'skills' / 'agent',
            program_finder=self._find_program,
            environment={
                'PRESENT_KEY': 'x',
            },
        )
        self.checkpoints = checkpoints_module.Checkpoints(
            root / 'trader.git',
            self.trader_directory,
        )
        self.ledger = self.trader_directory / 'skills' / 'ledger.jsonl'
        self.writer = skill_writer.SkillWriter(
            self.library,
            self.checkpoints,
            self.ledger,
        )

    def _find_program(self, program: str) -> str | None:
        """Pretends only python3 is installed.

        Args:
            program (str): The program.

        Returns:
            str | None: A path for python3, None otherwise.
        """
        if program == 'python3':
            return '/usr/bin/python3'
        return None


class TestSkillFormat:
    """SKILL.md files are read and checked."""

    def test_hermes_prerequisites_are_read_as_requirements(
        self,
        tmp_path: Path,
    ) -> None:
        """commands and env_vars count like programs and environment.

        Args:
            tmp_path (Path): A scratch folder.
        """
        folder = _write_skill(
            tmp_path,
            'inbox',
            extra_frontmatter='prerequisites:\n  commands: [himalaya]\n  env_vars: [MAIL_PASSWORD]\n',
        )
        skill = skill_module.SkillParser().parse(folder, 'installed')
        assert skill.required_programs == ('himalaya',)
        assert skill.required_environment == ('MAIL_PASSWORD',)
        assert skill.body == '# Steps\n1. Do it.'

    def test_bad_name_and_missing_frontmatter_are_refused(
        self,
        tmp_path: Path,
    ) -> None:
        """An upper-case name and a file without --- lines are both errors.

        Args:
            tmp_path (Path): A scratch folder.
        """
        parser = skill_module.SkillParser()
        with pytest.raises(skill_module.SkillFormatError):
            parser.parse(_write_skill(tmp_path, 'Bad_Name'), 'installed')
        plain = tmp_path / 'plain'
        plain.mkdir()
        (plain / 'SKILL.md').write_text('# no frontmatter', encoding='utf-8')
        with pytest.raises(skill_module.SkillFormatError):
            parser.parse(plain, 'installed')


class TestSkillLibrary:
    """The library lists usable skills and hides the rest."""

    def test_missing_needs_hide_a_skill(self, tmp_path: Path) -> None:
        """A missing program or variable hides the skill and says why.

        Args:
            tmp_path (Path): A scratch folder.
        """
        skills = _Skills(tmp_path)
        _write_skill(
            skills.installed,
            'uses-python',
            extra_frontmatter='requires:\n  programs: [python3]\n  environment: [PRESENT_KEY]\n',
        )
        _write_skill(
            skills.installed,
            'uses-r',
            extra_frontmatter='requires:\n  programs: [Rscript]\n  environment: [ABSENT_KEY]\n',
        )
        names = [skill.name for skill in skills.library.available()]
        assert names == [
            'uses-python',
        ]
        hidden = skills.library.hidden()
        assert hidden[0].skill.name == 'uses-r'
        assert hidden[0].missing == (
            'program Rscript',
            'environment variable ABSENT_KEY',
        )

    def test_installed_skill_wins_a_name_clash_and_broken_ones_are_skipped(
        self,
        tmp_path: Path,
    ) -> None:
        """The index shows the installed skill once, the trader's own marked, and no broken skill.

        Args:
            tmp_path (Path): A scratch folder.
        """
        skills = _Skills(tmp_path)
        _write_skill(skills.installed, 'gap-playbook', 'Installed version.')
        _write_skill(
            skills.library.agent_directory, 'gap-playbook', 'Trader copy.'
        )
        _write_skill(skills.library.agent_directory, 'my-routine', 'Mine.')
        (skills.library.agent_directory / 'broken').mkdir()
        index = skills.library.index_text()
        assert '- gap-playbook: Installed version.' in index
        assert 'Trader copy.' not in index
        assert '- my-routine (your own): Mine.' in index
        assert 'broken' not in index


class TestSkillWriter:
    """The trader creates, patches and archives its own skills."""

    def test_create_patch_and_archive_are_snapshotted_and_recorded(
        self,
        tmp_path: Path,
    ) -> None:
        """Each change has a checkpoint and a ledger line; the archived skill leaves the index.

        Args:
            tmp_path (Path): A scratch folder.
        """
        skills = _Skills(tmp_path)
        skills.writer.create(
            'gap-down',
            'What to do when NIFTY gaps down.',
            '1. Wait 15 minutes.',
            [],
            [],
            'learned today',
        )
        skills.writer.patch(
            'gap-down',
            'Wait 15 minutes.',
            'Wait 30 minutes.',
            '15 was too short',
        )
        assert '1. Wait 30 minutes.' in skills.library.find('gap-down').body
        skills.writer.archive('gap-down', 'merged elsewhere')
        assert skills.library.find('gap-down') is None
        assert (
            skills.library.agent_directory
            / '.archive'
            / 'gap-down'
            / 'SKILL.md'
        ).is_file()
        actions = [
            json.loads(line)['action']
            for line in skills.ledger.read_text(encoding='utf-8').splitlines()
        ]
        assert actions == [
            'create',
            'patch',
            'archive',
        ]
        reasons = [
            checkpoint.reason for checkpoint in skills.checkpoints.list()
        ]
        assert 'before skill_archive gap-down' in reasons
        assert 'before skill_patch gap-down' in reasons

    def test_installed_skills_cannot_be_overwritten_or_patched(
        self,
        tmp_path: Path,
    ) -> None:
        """Creating or patching an installed skill's name is refused.

        Args:
            tmp_path (Path): A scratch folder.
        """
        skills = _Skills(tmp_path)
        _write_skill(skills.installed, 'gap-playbook')
        with pytest.raises(skill_writer.SkillWriteError):
            skills.writer.create('gap-playbook', 'x', 'y', [], [], 'z')
        with pytest.raises(skill_writer.SkillWriteError, match='installed'):
            skills.writer.patch('gap-playbook', 'Do it.', 'Do more.', 'z')

    def test_patch_that_breaks_or_renames_the_skill_is_refused(
        self,
        tmp_path: Path,
    ) -> None:
        """Removing the description or changing the name leaves the file as it was.

        Args:
            tmp_path (Path): A scratch folder.
        """
        skills = _Skills(tmp_path)
        skills.writer.create('routine', 'A routine.', '1. Go.', [], [], 'r')
        path = skills.library.agent_directory / 'routine' / 'SKILL.md'
        before = path.read_text(encoding='utf-8')
        with pytest.raises(skill_writer.SkillWriteError, match='break'):
            skills.writer.patch('routine', 'description: A routine.', '', 'r')
        with pytest.raises(skill_writer.SkillWriteError, match='rename'):
            skills.writer.patch('routine', 'name: routine', 'name: other', 'r')
        assert path.read_text(encoding='utf-8') == before


class TestSkillImporter:
    """Skills are imported from folders and zip files."""

    def test_collection_is_imported_and_existing_skills_kept(
        self,
        tmp_path: Path,
    ) -> None:
        """Every SKILL.md folder is imported once; a second import skips unless replacing.

        Args:
            tmp_path (Path): A scratch folder.
        """
        source = tmp_path / 'collection'
        _write_skill(source / 'research', 'arxiv')
        _write_skill(source / 'email', 'inbox')
        _write_skill(source, 'Broken_Name')
        installed = tmp_path / 'installed'
        importer = skill_importer.SkillImporter(installed)
        outcomes = {}
        for result in importer.import_source(str(source), replace=False):
            outcomes[result.name or result.source.name] = result.outcome
        assert outcomes == {
            'arxiv': 'imported',
            'inbox': 'imported',
            'Broken_Name': 'invalid',
        }
        again = importer.import_source(str(source / 'research'), replace=False)
        assert again[0].outcome == 'skipped'
        replaced = importer.import_source(
            str(source / 'research'), replace=True
        )
        assert replaced[0].outcome == 'replaced'
        assert (installed / 'arxiv' / 'SKILL.md').is_file()

    def test_zip_entry_escaping_the_folder_is_refused(
        self,
        tmp_path: Path,
    ) -> None:
        """A zip file with a ../ entry is not unpacked.

        Args:
            tmp_path (Path): A scratch folder.
        """
        archive = tmp_path / 'evil.zip'
        with zipfile.ZipFile(archive, 'w') as zip_file:
            zip_file.writestr('../outside.txt', 'x')
            zip_file.writestr(
                'skill/SKILL.md',
                '---\nname: skill\ndescription: d\n---\nbody\n',
            )
        importer = skill_importer.SkillImporter(tmp_path / 'installed')
        with pytest.raises(skill_importer.SkillImportError, match='outside'):
            importer.import_source(str(archive), replace=False)
        assert not (tmp_path / 'outside.txt').exists()


class TestSkillUsage:
    """Uses are recorded from the event stream."""

    def test_use_is_recorded_with_later_tool_errors(
        self, tmp_path: Path
    ) -> None:
        """A load, one failed call after it, and a failed load that is dropped.

        Args:
            tmp_path (Path): A scratch folder.
        """
        layout = workspace_layout.WorkspaceLayout(tmp_path)
        tracker = skill_usage.SkillUsageTracker(
            event_bus_module.EventBus(),
            layout,
        )
        events = [
            (
                event_module.EventKind.TOOL_CALL,
                {
                    'trigger_id': 't1',
                    'call_id': 'c1',
                    'name': 'load_skill',
                    'arguments': {
                        'name': 'gap-down',
                    },
                },
            ),
            (
                event_module.EventKind.TOOL_CALL,
                {
                    'trigger_id': 't1',
                    'call_id': 'c2',
                    'name': 'load_skill',
                    'arguments': {
                        'name': 'missing',
                    },
                },
            ),
            (
                event_module.EventKind.TOOL_RESULT,
                {
                    'call_id': 'c2',
                    'is_error': True,
                },
            ),
            (
                event_module.EventKind.TOOL_RESULT,
                {
                    'call_id': 'c3',
                    'is_error': True,
                },
            ),
            (
                event_module.EventKind.TURN_FINISHED,
                {
                    'trigger_id': 't1',
                },
            ),
        ]
        for kind, payload in events:
            tracker.handle(event_module.Event.now(kind, 'main', payload))
        statistics = skill_usage.SkillUsageReader(
            layout.skill_usage_file('main')
        ).statistics()
        assert list(statistics) == [
            'gap-down',
        ]
        assert statistics['gap-down'].uses == 1
        assert statistics['gap-down'].troubled_uses == 1


class TestSkillCurator:
    """The curator archives idle skills and writes the review request."""

    def test_idle_skill_is_archived_and_review_lists_the_rest(
        self,
        tmp_path: Path,
    ) -> None:
        """A skill untouched for 40 days goes; a recent one is listed with its use.

        Args:
            tmp_path (Path): A scratch folder.
        """
        skills = _Skills(tmp_path)
        old = _write_skill(skills.library.agent_directory, 'old-routine')
        _write_skill(skills.library.agent_directory, 'fresh-routine')
        forty_days_ago = datetime.datetime(2026, 9, 9, tzinfo=datetime.UTC)
        os.utime(
            old / 'SKILL.md',
            (
                forty_days_ago.timestamp(),
                forty_days_ago.timestamp(),
            ),
        )
        usage_file = tmp_path / 'usage.jsonl'
        usage_file.write_text(
            json.dumps(
                {
                    'at': '2026-10-19T05:00:00+00:00',
                    'skill': 'fresh-routine',
                    'tool_errors_after': 2,
                    'turn_failed': False,
                }
            )
            + '\n',
            encoding='utf-8',
        )
        curator = skill_curator.SkillCurator(
            skills.library,
            skill_usage.SkillUsageReader(usage_file),
            skills.writer,
            30,
        )
        archived = curator.archive_unused(datetime.date(2026, 10, 19))
        assert archived == [
            'old-routine',
        ]
        request = curator.review_request(datetime.date(2026, 10, 19), archived)
        assert (
            '- fresh-routine: used 1 times, 1 troubled, last on 2026-10-19'
            in request
        )
        assert 'Archived just now' in request
        assert 'old-routine' in request


class TestSkillInvocation:
    """Skills are loaded by tool and invoked as /<skill-name>."""

    def test_load_skill_returns_the_body_and_bundled_files(
        self,
        tmp_path: Path,
    ) -> None:
        """The result has the instructions and absolute script paths.

        Args:
            tmp_path (Path): A scratch folder.
        """
        skills = _Skills(tmp_path)
        folder = _write_skill(skills.installed, 'breakout')
        (folder / 'scripts').mkdir()
        (folder / 'scripts' / 'scan.py').write_text(
            'print(1)', encoding='utf-8'
        )
        tool = load_skill_tool.LoadSkillTool(skills.library)
        result = asyncio.run(
            tool.run(load_skill_tool.LoadSkillArguments(name='breakout'))
        )
        assert '1. Do it.' in result.text
        assert str((folder / 'scripts' / 'scan.py').resolve()) in result.text
        missing = asyncio.run(
            tool.run(load_skill_tool.LoadSkillArguments(name='nope'))
        )
        assert missing.is_error
        assert 'breakout' in missing.text

    def test_slash_skill_becomes_a_request_and_built_ins_win(
        self,
        tmp_path: Path,
    ) -> None:
        """/breakout NIFTY asks the model to follow it; /status stays a command.

        Args:
            tmp_path (Path): A scratch folder.
        """
        skills = _Skills(tmp_path)
        _write_skill(skills.installed, 'breakout')
        _write_skill(skills.installed, 'status')
        commands = slash_commands.SlashCommands(None, 'dry_run', skills.library)
        request = commands.skill_request('/breakout NIFTY')
        assert request == (
            '[The user invoked your skill breakout with /breakout. Load it with load_skill and follow it.]\n'
            'NIFTY'
        )
        assert commands.skill_request('/status') is None
        assert commands.skill_request('/unknown') is None


class TestSandboxEnvironment:
    """Only the variables the user names reach the sandbox."""

    def test_named_variable_is_passed_and_others_are_not(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A named, set variable is added with --setenv; an unnamed one is not.

        Args:
            tmp_path (Path): A scratch folder.
            monkeypatch (pytest.MonkeyPatch): Sets variables for this test only.
        """
        monkeypatch.setenv('SKILL_API_KEY', 'abc')
        monkeypatch.setenv('OTHER_SECRET', 'zzz')
        sandbox = bash_sandbox.BashSandbox(
            tmp_path,
            [],
            [
                'SKILL_API_KEY',
                'NOT_SET_ANYWHERE',
            ],
        )
        assert sandbox.passed_environment() == {
            'SKILL_API_KEY': 'abc',
        }
        command = sandbox.command(
            [
                'true',
            ]
        )
        joined = ' '.join(command)
        assert '--setenv SKILL_API_KEY abc' in joined
        assert 'OTHER_SECRET' not in joined
