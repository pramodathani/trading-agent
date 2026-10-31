"""Tests for reading and checking trading_agent.toml."""

from pathlib import Path

import pytest

from trading_agent.configuration import configuration_loader

_VALID_CONFIGURATION = '\n'.join(
    [
        'tradingmachine_environment_file = "/tmp/tradingmachine.env"',
        '',
        '[traders]',
        'heartbeat_minutes = 5',
        '',
        '[backends.gemma]',
        'kind = "ollama"',
        'base_url = "http://127.0.0.1:11434"',
        'model = "gemma4:31b"',
        'context_window = 32768',
    ]
)


class TestConfigurationLoader:
    """Tests for ConfigurationLoader."""

    def _write(self, directory: Path, text: str) -> Path:
        """Writes a configuration file into a temporary directory.

        Args:
            directory (Path): The temporary directory.
            text (str): The file's contents.

        Returns:
            Path: The written file.
        """
        path = directory / 'trading_agent.toml'
        path.write_text(text, encoding='utf-8')
        return path

    def test_load_valid_file_fills_defaults(self, tmp_path: Path) -> None:
        """A valid file loads, and unset values take their defaults.

        Args:
            tmp_path (Path): A temporary directory from pytest.
        """
        path = self._write(tmp_path, _VALID_CONFIGURATION)

        configuration = configuration_loader.ConfigurationLoader(path).load()

        assert configuration.mode == 'dry_run'
        assert configuration.gateway.host == '127.0.0.1'
        assert configuration.traders.heartbeat_minutes == 5
        assert configuration.traders.first_trader == 'general'
        assert configuration.telegram.default_trader == 'general'
        assert configuration.backends['gemma'].context_window == 32768

    def test_load_missing_file_raises(self, tmp_path: Path) -> None:
        """A missing file raises ConfigurationError naming the file.

        Args:
            tmp_path (Path): A temporary directory from pytest.
        """
        loader = configuration_loader.ConfigurationLoader(
            tmp_path / 'absent.toml'
        )

        with pytest.raises(
            configuration_loader.ConfigurationError, match='not found'
        ):
            loader.load()

    def test_load_bad_toml_raises(self, tmp_path: Path) -> None:
        """A file that is not TOML raises ConfigurationError.

        Args:
            tmp_path (Path): A temporary directory from pytest.
        """
        path = self._write(tmp_path, 'this is = = not toml')

        with pytest.raises(
            configuration_loader.ConfigurationError, match='not valid TOML'
        ):
            configuration_loader.ConfigurationLoader(path).load()

    def test_load_old_list_of_traders_raises(self, tmp_path: Path) -> None:
        """The old [[traders]] list is rejected, because each trader now has its own trader.toml.

        Args:
            tmp_path (Path): A temporary directory from pytest.
        """
        text = _VALID_CONFIGURATION.replace(
            '[traders]\nheartbeat_minutes = 5',
            '[[traders]]\nname = "main"',
        )
        path = self._write(tmp_path, text)

        with pytest.raises(configuration_loader.ConfigurationError):
            configuration_loader.ConfigurationLoader(path).load()

    def test_load_server_backend_without_base_url_raises(
        self,
        tmp_path: Path,
    ) -> None:
        """An Ollama backend without base_url is rejected.

        Args:
            tmp_path (Path): A temporary directory from pytest.
        """
        text = _VALID_CONFIGURATION.replace(
            'base_url = "http://127.0.0.1:11434"\n',
            '',
        )
        path = self._write(tmp_path, text)

        with pytest.raises(
            configuration_loader.ConfigurationError,
            match='base_url is required',
        ):
            configuration_loader.ConfigurationLoader(path).load()

    def test_load_unknown_key_raises(self, tmp_path: Path) -> None:
        """A misspelt key is rejected rather than silently ignored.

        Args:
            tmp_path (Path): A temporary directory from pytest.
        """
        text = 'modde = "live"\n' + _VALID_CONFIGURATION
        path = self._write(tmp_path, text)

        with pytest.raises(
            configuration_loader.ConfigurationError, match='modde'
        ):
            configuration_loader.ConfigurationLoader(path).load()

    def test_load_trader_with_unknown_backend_raises(
        self, tmp_path: Path
    ) -> None:
        """A [traders] backend order that names a backend missing from [backends] is rejected.

        Args:
            tmp_path (Path): A temporary directory from pytest.
        """
        text = _VALID_CONFIGURATION.replace(
            'heartbeat_minutes = 5',
            'heartbeat_minutes = 5\nbackend_order = ["missing"]',
        )
        path = self._write(tmp_path, text)

        with pytest.raises(
            configuration_loader.ConfigurationError,
            match='unknown backend',
        ):
            configuration_loader.ConfigurationLoader(path).load()
