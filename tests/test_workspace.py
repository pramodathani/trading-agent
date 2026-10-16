"""Tests for the workspace files, the prompt builder and proposals."""

from pathlib import Path

import pytest

from trading_agent.agent import prompt_builder
from trading_agent.workspace import proposal_store
from trading_agent.workspace import workspace_layout


def _layout(tmp_path: Path) -> workspace_layout.WorkspaceLayout:
    """Builds a workspace in a temporary folder, with its templates written.

    Args:
        tmp_path (Path): A temporary folder from pytest.

    Returns:
        workspace_layout.WorkspaceLayout: The workspace.
    """
    layout = workspace_layout.WorkspaceLayout(tmp_path / 'workspace')
    layout.create_missing(['main'])
    return layout


class TestWorkspaceLayout:
    """Tests for creating the workspace."""

    def test_create_missing_writes_every_template_once(
        self, tmp_path: Path
    ) -> None:
        """The first call writes five files; a second call writes none and keeps edits.

        Args:
            tmp_path (Path): A temporary folder from pytest.
        """
        layout = workspace_layout.WorkspaceLayout(tmp_path / 'workspace')

        created = layout.create_missing(['main'])
        layout.user_file.write_text('edited by the user', encoding='utf-8')
        created_again = layout.create_missing(['main'])

        assert len(created) == 5
        assert created_again == []
        assert (
            layout.user_file.read_text(encoding='utf-8') == 'edited by the user'
        )
        assert layout.proposals_directory('main').is_dir()

    def test_template_status_is_detected(self, tmp_path: Path) -> None:
        """A fresh User.md counts as a template; one without the status line does not.

        Args:
            tmp_path (Path): A temporary folder from pytest.
        """
        layout = _layout(tmp_path)

        assert layout.is_template(layout.user_file)
        layout.user_file.write_text(
            '# User.md\nName: Pramod\n', encoding='utf-8'
        )
        assert not layout.is_template(layout.user_file)

    def test_unknown_user_file_is_refused(self, tmp_path: Path) -> None:
        """Only the four user files can be named.

        Args:
            tmp_path (Path): A temporary folder from pytest.
        """
        layout = _layout(tmp_path)

        with pytest.raises(ValueError, match='Not one of the user files'):
            layout.user_owned_file('main', 'Memory.md')


class TestPromptBuilder:
    """Tests for building the system prompt."""

    def test_sections_appear_in_order_with_the_mode(
        self, tmp_path: Path
    ) -> None:
        """The prompt names the desk and mode and holds the files in their order.

        Args:
            tmp_path (Path): A temporary folder from pytest.
        """
        prompt = prompt_builder.PromptBuilder(
            _layout(tmp_path), 'main', 'dry_run'
        ).build()

        positions = [
            prompt.text.index(f'===== {title} =====')
            for title in [
                'Agents.md',
                'Persona.md',
                'User.md',
                'TradingRules.md',
                'Memory.md',
            ]
        ]
        assert positions == sorted(positions)
        assert 'You are the "main" desk' in prompt.text
        assert 'Mode: dry_run' in prompt.text

    def test_interview_is_added_only_while_user_file_is_a_template(
        self,
        tmp_path: Path,
    ) -> None:
        """The first-run interview instructions disappear once User.md is filled in.

        Args:
            tmp_path (Path): A temporary folder from pytest.
        """
        layout = _layout(tmp_path)
        builder = prompt_builder.PromptBuilder(layout, 'main', 'dry_run')

        before = builder.build()
        layout.user_file.write_text(
            '# User.md\nName: Pramod\n', encoding='utf-8'
        )
        after = builder.build()

        assert 'First-run interview' in before.text
        assert 'First-run interview' not in after.text
        assert before.fingerprint != after.fingerprint

    def test_unchanged_files_give_the_same_fingerprint(
        self, tmp_path: Path
    ) -> None:
        """Building twice without edits gives an identical prompt, which keeps the prompt cache warm.

        Args:
            tmp_path (Path): A temporary folder from pytest.
        """
        builder = prompt_builder.PromptBuilder(
            _layout(tmp_path), 'main', 'live'
        )

        assert builder.build() == builder.build()

    def test_long_file_is_cut(self, tmp_path: Path) -> None:
        """A file over 20,000 characters is cut with a note saying so.

        Args:
            tmp_path (Path): A temporary folder from pytest.
        """
        layout = _layout(tmp_path)
        layout.memory_file('main').write_text('x' * 30000, encoding='utf-8')

        prompt = prompt_builder.PromptBuilder(layout, 'main', 'dry_run').build()

        assert 'Memory.md was cut here' in prompt.text
        assert len(prompt.text) < 60000 + 200


class TestProposalStore:
    """Tests for proposals."""

    def test_accept_replaces_the_file_and_keeps_the_old_one(
        self, tmp_path: Path
    ) -> None:
        """Accepting writes the new text and saves the previous version.

        Args:
            tmp_path (Path): A temporary folder from pytest.
        """
        layout = _layout(tmp_path)
        store = proposal_store.ProposalStore(layout)
        old_text = layout.user_file.read_text(encoding='utf-8')

        proposal = store.create(
            'main', 'User.md', '# User.md\nName: Pramod\n', 'From the interview'
        )
        difference = store.difference(proposal.proposal_id)
        target = store.accept(proposal.proposal_id)

        backups = list(
            (layout.proposals_directory('main') / 'replaced').iterdir()
        )
        assert target == layout.user_file
        assert (
            layout.user_file.read_text(encoding='utf-8')
            == '# User.md\nName: Pramod\n'
        )
        assert backups[0].read_text(encoding='utf-8') == old_text
        assert '+Name: Pramod' in difference
        assert store.get(proposal.proposal_id).status == 'accepted'

    def test_persona_proposal_targets_the_desk_file(
        self, tmp_path: Path
    ) -> None:
        """A Persona.md proposal changes the proposing desk's persona.

        Args:
            tmp_path (Path): A temporary folder from pytest.
        """
        layout = _layout(tmp_path)
        store = proposal_store.ProposalStore(layout)

        proposal = store.create(
            'main', 'Persona.md', 'Scalper.', 'Chosen style'
        )
        store.accept(proposal.proposal_id)

        assert (
            layout.persona_file('main').read_text(encoding='utf-8')
            == 'Scalper.'
        )

    def test_reject_changes_nothing_and_cannot_be_accepted_later(
        self,
        tmp_path: Path,
    ) -> None:
        """A rejected proposal leaves the file alone and can no longer be accepted.

        Args:
            tmp_path (Path): A temporary folder from pytest.
        """
        layout = _layout(tmp_path)
        store = proposal_store.ProposalStore(layout)
        before = layout.trading_rules_file.read_text(encoding='utf-8')

        proposal = store.create(
            'main', 'TradingRules.md', 'no limits', 'Bad idea'
        )
        store.reject(proposal.proposal_id)

        assert layout.trading_rules_file.read_text(encoding='utf-8') == before
        with pytest.raises(
            proposal_store.ProposalError, match='already rejected'
        ):
            store.accept(proposal.proposal_id)

    def test_memory_file_cannot_be_proposed(self, tmp_path: Path) -> None:
        """Proposals are only for the user's files.

        Args:
            tmp_path (Path): A temporary folder from pytest.
        """
        store = proposal_store.ProposalStore(_layout(tmp_path))

        with pytest.raises(ValueError):
            store.create('main', 'Memory.md', 'x', 'y')

    def test_unknown_id_is_an_error(self, tmp_path: Path) -> None:
        """Asking for a proposal that does not exist raises ProposalError.

        Args:
            tmp_path (Path): A temporary folder from pytest.
        """
        store = proposal_store.ProposalStore(_layout(tmp_path))

        with pytest.raises(proposal_store.ProposalError, match='No proposal'):
            store.get('20260101-000000-abcd')
