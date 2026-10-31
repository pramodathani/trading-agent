"""Tests for the file tools and the rules they follow."""

import asyncio
from pathlib import Path

from trading_agent.tools import edit_file_tool
from trading_agent.tools import path_policy
from trading_agent.tools import read_file_tool
from trading_agent.tools import write_file_tool


class _Trader:
    """A trader folder, a user file outside it and a hidden secret.

    Attributes:
        directory: The trader's folder.
        user_file: A file belonging to the user.
        secret: A hidden secret file.
        policy: The trader's read and write rules.
    """

    def __init__(self, tmp_path: Path):
        """Creates the folders, files and policy.

        Args:
            tmp_path (Path): A temporary folder from pytest.
        """
        self.directory = tmp_path / 'traders' / 'main'
        (self.directory / 'notes').mkdir(parents=True)
        (self.directory / 'Memory.md').write_text(
            '# Memory\n', encoding='utf-8'
        )
        self.user_file = tmp_path / 'TradingRules.md'
        self.user_file.write_text('limits\n', encoding='utf-8')
        self.secret = tmp_path / '.env'
        self.secret.write_text('API_KEY=x\n', encoding='utf-8')
        self.policy = path_policy.PathPolicy(
            self.directory,
            [
                self.secret,
            ],
        )

    def read(self, path: str, start_line: int = 1, maximum_lines: int = 400):
        """Runs read_file.

        Args:
            path (str): The path to read.
            start_line (int): The first line.
            maximum_lines (int): How many lines.

        Returns:
            object: The tool result.
        """
        tool = read_file_tool.ReadFileTool(self.policy)
        arguments = read_file_tool.ReadFileArguments(
            path=path,
            start_line=start_line,
            maximum_lines=maximum_lines,
        )
        return asyncio.run(tool.run(arguments))

    def write(self, path: str, content: str):
        """Runs write_file.

        Args:
            path (str): The path to write.
            content (str): The text.

        Returns:
            object: The tool result.
        """
        tool = write_file_tool.WriteFileTool(self.policy)
        arguments = write_file_tool.WriteFileArguments(
            path=path, content=content
        )
        return asyncio.run(tool.run(arguments))

    def edit(
        self, path: str, old_text: str, new_text: str, replace_all: bool = False
    ):
        """Runs edit_file.

        Args:
            path (str): The path to edit.
            old_text (str): The text to find.
            new_text (str): Its replacement.
            replace_all (bool): Whether to replace every occurrence.

        Returns:
            object: The tool result.
        """
        tool = edit_file_tool.EditFileTool(self.policy)
        arguments = edit_file_tool.EditFileArguments(
            path=path,
            old_text=old_text,
            new_text=new_text,
            replace_all=replace_all,
        )
        return asyncio.run(tool.run(arguments))


class TestFileTools:
    """Tests for read_file, write_file and edit_file."""

    def test_write_then_read_in_the_trader_folders(
        self, tmp_path: Path
    ) -> None:
        """A note written by the trader reads back with line numbers.

        Args:
            tmp_path (Path): A temporary folder from pytest.
        """
        trader = _Trader(tmp_path)

        written = trader.write('notes/today.md', 'first\nsecond\n')
        read = trader.read('notes/today.md')

        assert not written.is_error
        assert read.text == '     1  first\n     2  second'

    def test_read_shows_where_to_continue(self, tmp_path: Path) -> None:
        """Reading part of a file says how many lines remain and where to start next.

        Args:
            tmp_path (Path): A temporary folder from pytest.
        """
        trader = _Trader(tmp_path)
        trader.write(
            'notes/long.md', '\n'.join(str(number) for number in range(1, 11))
        )

        result = trader.read('notes/long.md', start_line=3, maximum_lines=2)

        assert (
            result.text
            == '     3  3\n     4  4\n[6 more lines; read again with start_line=5]'
        )

    def test_user_files_can_be_read_but_not_written(
        self, tmp_path: Path
    ) -> None:
        """The trader can read the user's file but writing it is refused.

        Args:
            tmp_path (Path): A temporary folder from pytest.
        """
        trader = _Trader(tmp_path)

        read = trader.read(str(trader.user_file))
        written = trader.write(str(trader.user_file), 'no limits')

        assert 'limits' in read.text
        assert written.is_error
        assert 'propose_file_change' in written.text
        assert trader.user_file.read_text() == 'limits\n'

    def test_dot_dot_cannot_escape_the_trader_folders(
        self, tmp_path: Path
    ) -> None:
        """A path that climbs out with .. is refused.

        Args:
            tmp_path (Path): A temporary folder from pytest.
        """
        trader = _Trader(tmp_path)

        result = trader.write('notes/../../../TradingRules.md', 'no limits')

        assert result.is_error
        assert trader.user_file.read_text() == 'limits\n'

    def test_link_cannot_escape_the_trader_folders(
        self, tmp_path: Path
    ) -> None:
        """A link inside notes/ pointing at the user's file is refused.

        Args:
            tmp_path (Path): A temporary folder from pytest.
        """
        trader = _Trader(tmp_path)
        (trader.directory / 'notes' / 'rules.md').symlink_to(trader.user_file)

        result = trader.write('notes/rules.md', 'no limits')

        assert result.is_error
        assert trader.user_file.read_text() == 'limits\n'

    def test_secret_cannot_be_read(self, tmp_path: Path) -> None:
        """A hidden secret file is refused.

        Args:
            tmp_path (Path): A temporary folder from pytest.
        """
        trader = _Trader(tmp_path)

        result = trader.read(str(trader.secret))

        assert result.is_error
        assert 'API_KEY' not in result.text

    def test_memory_file_can_be_edited(self, tmp_path: Path) -> None:
        """The trader's Memory.md is writable, and an exact edit replaces one place.

        Args:
            tmp_path (Path): A temporary folder from pytest.
        """
        trader = _Trader(tmp_path)

        result = trader.edit(
            'Memory.md', '# Memory\n', '# Memory\n- Lesson one.\n'
        )

        assert not result.is_error
        assert (
            trader.directory / 'Memory.md'
        ).read_text() == '# Memory\n- Lesson one.\n'

    def test_edit_needs_a_unique_match(self, tmp_path: Path) -> None:
        """An edit whose text appears twice is refused unless replace_all is set.

        Args:
            tmp_path (Path): A temporary folder from pytest.
        """
        trader = _Trader(tmp_path)
        trader.write('notes/a.md', 'buy\nbuy\n')

        refused = trader.edit('notes/a.md', 'buy', 'sell')
        replaced = trader.edit('notes/a.md', 'buy', 'sell', replace_all=True)

        assert refused.is_error
        assert 'appears 2 times' in refused.text
        assert not replaced.is_error
        assert (
            trader.directory / 'notes' / 'a.md'
        ).read_text() == 'sell\nsell\n'
