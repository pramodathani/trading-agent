"""A package's app.toml: the web app it brings and the systemd unit that runs it.

An app is a separate program with its own web page, such as sridhara. trading-agent never runs it inside the gateway; it shows the page in its sidebar, checks that the page answers, and can start, stop or restart the app's systemd user unit.

  [app]
  title = "Sridhara"
  description = "A Kite-style trading terminal on UBI"
  url = "http://127.0.0.1:8095/"
  health_url = "http://127.0.0.1:8095/"   optional; the url itself when left out
  open_in = "frame"                        "frame" shows it inside trading-agent, "tab" opens a new tab

  [service]                                optional
  unit = "sridhara.service"                the systemd user unit that runs the app
  unit_file = "%h/Projects/sridhara/services/sridhara.service"   optional; linked by `trading-agent apps enable`

Typical usage example:

  manifest = AppManifestReader().read(package_folder / 'app.toml')
"""

import tomllib
from pathlib import Path
from typing import Literal

import pydantic

APP_FILE_NAME = 'app.toml'
_UNIT_PATTERN = r'^[A-Za-z0-9@._-]+\.service$'
_HOME_PLACEHOLDER = '%h'


class AppManifestError(ValueError):
    """An app.toml that cannot be read or holds invalid values."""


class AppSettings(pydantic.BaseModel):
    """The [app] table.

    Attributes:
        title: The name shown in the sidebar.
        description: One sentence about the app.
        url: The app's own web page.
        health_url: The address checked to say the app is up, or None to check the url.
        open_in: "frame" to show the page inside trading-agent, "tab" to open it in a new tab.
    """

    model_config = pydantic.ConfigDict(extra='forbid')

    title: str = pydantic.Field(min_length=1, max_length=40)
    description: str = ''
    url: pydantic.AnyHttpUrl
    health_url: pydantic.AnyHttpUrl | None = None
    open_in: Literal['frame', 'tab'] = 'frame'


class ServiceSettings(pydantic.BaseModel):
    """The [service] table.

    Attributes:
        unit: The systemd user unit, such as sridhara.service.
        unit_file: The unit file `trading-agent apps enable` links, or None when the unit is installed already; %h stands for the home folder, and a relative path is inside the package.
    """

    model_config = pydantic.ConfigDict(extra='forbid')

    unit: str = pydantic.Field(pattern=_UNIT_PATTERN)
    unit_file: str | None = None


class AppManifest(pydantic.BaseModel):
    """A whole app.toml.

    Attributes:
        app: The web app.
        service: Its systemd unit, or None for an app trading-agent cannot start or stop.
    """

    model_config = pydantic.ConfigDict(extra='forbid')

    app: AppSettings
    service: ServiceSettings | None = None

    def health_address(self) -> str:
        """The address checked to say the app is up.

        Returns:
            str: The health_url, or the url when there is none.
        """
        return str(self.app.health_url or self.app.url)

    def unit_file_path(self, package_folder: Path) -> Path | None:
        """Where the unit file is.

        Args:
            package_folder (Path): The installed package's folder.

        Returns:
            Path | None: The unit file's path, or None when the manifest names none.
        """
        if self.service is None or self.service.unit_file is None:
            return None
        text = self.service.unit_file.replace(
            _HOME_PLACEHOLDER, str(Path.home())
        )
        path = Path(text)
        if not path.is_absolute():
            path = package_folder / path
        return path


class AppManifestReader:
    """Reads and checks app.toml files."""

    def read(self, path: Path) -> AppManifest:
        """Reads one app.toml.

        Args:
            path (Path): The file.

        Returns:
            AppManifest: Its settings.

        Raises:
            AppManifestError: The file is not valid TOML, or a value is missing or wrong.
        """
        try:
            data = tomllib.loads(path.read_text(encoding='utf-8'))
        except (OSError, tomllib.TOMLDecodeError) as error:
            raise AppManifestError(f'{path}: {error}') from error
        try:
            return AppManifest.model_validate(data)
        except pydantic.ValidationError as error:
            problems = []
            for problem in error.errors():
                location = '.'.join(str(part) for part in problem['loc'])
                problems.append(f'{location}: {problem["msg"]}')
            raise AppManifestError(f'{path}: {"; ".join(problems)}') from error
