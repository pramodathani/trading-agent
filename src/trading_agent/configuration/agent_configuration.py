"""The shape of trading_agent.toml, checked when it is read.

Each class describes one table of the file. Pydantic checks every value against its type and range, so a typing mistake in the file is reported by name when the program starts.

Typical usage example:

  configuration = AgentConfiguration.model_validate(parsed_toml)
  port = configuration.gateway.port
"""

from pathlib import Path
from typing import Literal

import pydantic


class GatewayConfiguration(pydantic.BaseModel):
    """Where the gateway's web server listens.

    Attributes:
        host: The address to listen on. 127.0.0.1 keeps the gateway reachable from this machine only.
        port: The TCP port to listen on.
    """

    model_config = pydantic.ConfigDict(extra='forbid')

    host: str = '127.0.0.1'
    port: int = pydantic.Field(default=8120, gt=0, lt=65536)


class DeskConfiguration(pydantic.BaseModel):
    """One trading desk, which is one independent agent.

    Attributes:
        name: The desk's name, used in folder names, order tags and the web interface.
        enabled: Whether the desk starts with the gateway.
        backend_order: The backends the desk may use, most preferred first, by their names in [backends].
    """

    model_config = pydantic.ConfigDict(extra='forbid')

    name: str = pydantic.Field(pattern=r'^[a-z][a-z0-9_]*$')
    enabled: bool = True
    backend_order: list[str] = []


class AgentLoopConfiguration(pydantic.BaseModel):
    """Limits that keep one turn of the agent loop under control.

    Attributes:
        maximum_rounds: The most model calls one turn may make before it is stopped.
        maximum_identical_tool_calls: How many times one tool may be called with the same arguments in a turn.
        tool_timeout_seconds: How long one tool call may run before it is stopped.
    """

    model_config = pydantic.ConfigDict(extra='forbid')

    maximum_rounds: int = pydantic.Field(default=20, gt=0)
    maximum_identical_tool_calls: int = pydantic.Field(default=3, gt=0)
    tool_timeout_seconds: float = pydantic.Field(default=60.0, gt=0)


_DEFAULT_HIDDEN_PATHS = [
    '~/.claude',
    '~/.claude.json',
    '~/.config/anthropic',
    '~/.config/gh',
    '~/.git-credentials',
    '~/.ssh',
    '~/.gnupg',
    '~/.docker',
    '~/.hermes',
    '~/.ollama',
    '~/Projects/*/.env',
    '~/Projects/unified_broker_interface',
    '/var/run/docker.sock',
    '/run/docker.sock',
    '/run/user',
]


class SandboxConfiguration(pydantic.BaseModel):
    """How the bash terminal's sandbox is built.

    Attributes:
        command_timeout_seconds: How long one bash command may run before the session is restarted.
        maximum_output_characters: How much of a command's output is returned to the model.
        hidden_paths: Files and folders replaced by empty ones inside the sandbox, so their contents cannot be read. "~" and "*" are expanded.
    """

    model_config = pydantic.ConfigDict(extra='forbid')

    command_timeout_seconds: float = pydantic.Field(default=120.0, gt=0)
    maximum_output_characters: int = pydantic.Field(default=20000, gt=0)
    hidden_paths: list[str] = _DEFAULT_HIDDEN_PATHS


class WebConfiguration(pydantic.BaseModel):
    """Where web search goes and how pages are fetched.

    Attributes:
        searxng_base_url: The local SearXNG server started by docker-compose.yml.
        search_result_limit: The most results one search returns.
        fetch_timeout_seconds: How long fetching one page may take.
        maximum_page_characters: How much of a page's text is returned to the model.
    """

    model_config = pydantic.ConfigDict(extra='forbid')

    searxng_base_url: str = 'http://127.0.0.1:4001'
    search_result_limit: int = pydantic.Field(default=8, gt=0, le=30)
    fetch_timeout_seconds: float = pydantic.Field(default=20.0, gt=0)
    maximum_page_characters: int = pydantic.Field(default=15000, gt=0)


class MarginRatesConfiguration(pydantic.BaseModel):
    """The rates used to estimate the margin an order blocks.

    The defaults are the deliberately high segment-wide rates UBI's broker selector uses.

    Attributes:
        intraday_rate: The share of an intraday (mis) cash order's value blocked as margin.
        index_derivative_rate: The share of an index future's value, or of a sold index option's, blocked as margin.
        stock_derivative_rate: The same for stock futures and options.
        commodity_derivative_rate: The same for commodity futures and options.
        currency_derivative_rate: The same for currency futures and options.
    """

    model_config = pydantic.ConfigDict(extra='forbid')

    intraday_rate: float = pydantic.Field(default=0.20, gt=0, le=1)
    index_derivative_rate: float = pydantic.Field(default=0.15, gt=0, le=1)
    stock_derivative_rate: float = pydantic.Field(default=0.40, gt=0, le=1)
    commodity_derivative_rate: float = pydantic.Field(default=0.47, gt=0, le=1)
    currency_derivative_rate: float = pydantic.Field(default=0.10, gt=0, le=1)


class RiskConfiguration(pydantic.BaseModel):
    """How the risk engine works, apart from the limits in TradingRules.md.

    Attributes:
        ownership_grace_minutes: How long a desk keeps its claim on an instrument it ordered but does not yet hold, before the claim lapses.
        margin_rates: The rates used to estimate an order's margin.
    """

    model_config = pydantic.ConfigDict(extra='forbid')

    ownership_grace_minutes: float = pydantic.Field(default=30.0, gt=0)
    margin_rates: MarginRatesConfiguration = MarginRatesConfiguration()


class BrowserConfiguration(pydantic.BaseModel):
    """How each desk's Chrome browser runs.

    Attributes:
        headless: Whether Chrome runs without a window. Turn it off to watch a desk browse.
        navigation_timeout_seconds: How long opening or changing a page may take.
        maximum_elements: The most clickable elements one snapshot lists.
        maximum_text_characters: How much of a page's visible text one snapshot returns.
    """

    model_config = pydantic.ConfigDict(extra='forbid')

    headless: bool = True
    navigation_timeout_seconds: float = pydantic.Field(default=30.0, gt=0)
    maximum_elements: int = pydantic.Field(default=150, gt=0)
    maximum_text_characters: int = pydantic.Field(default=8000, gt=0)


class BackendConfiguration(pydantic.BaseModel):
    """One model backend that a desk can use.

    Attributes:
        kind: How the model is reached: "ollama", "openai_compatible" or "claude_code".
        base_url: The server address, needed by the ollama and openai_compatible kinds.
        model: The model name the server knows the model by.
        context_window: How many tokens of context the model is given.
        thinking: Whether the model reasons before answering, for models that support it.
    """

    model_config = pydantic.ConfigDict(extra='forbid')

    kind: Literal['ollama', 'openai_compatible', 'claude_code']
    base_url: str | None = None
    model: str
    context_window: int = pydantic.Field(gt=0)
    thinking: bool = True

    @pydantic.model_validator(mode='after')
    def _require_base_url_for_servers(self) -> BackendConfiguration:
        """Checks that a backend reached over HTTP has an address.

        Returns:
            BackendConfiguration: This configuration, unchanged.

        Raises:
            ValueError: The kind needs a base_url and none was given.
        """
        if self.kind != 'claude_code' and self.base_url is None:
            raise ValueError(f'base_url is required for kind={self.kind!r}')
        return self


class AgentConfiguration(pydantic.BaseModel):
    """Everything in trading_agent.toml.

    Attributes:
        mode: "dry_run" sends every order to UBI as a dry run, and "live" sends real orders.
        workspace_directory: The folder holding the desks' files, memory and journals.
        tradingmachine_environment_file: The .env file that tradingmachine reads its UBI and MongoDB settings from.
        gateway: Where the web server listens.
        desks: The desks to run.
        backends: The model backends, keyed by the name desks refer to them by.
        agent: The limits of the agent loop.
        sandbox: How the bash terminal's sandbox is built.
        web: Where web search goes and how pages are fetched.
        browser: How each desk's Chrome browser runs.
        risk: How the risk engine works, apart from the limits in TradingRules.md.
    """

    model_config = pydantic.ConfigDict(extra='forbid')

    mode: Literal['dry_run', 'live'] = 'dry_run'
    workspace_directory: Path = Path('workspace')
    tradingmachine_environment_file: Path
    gateway: GatewayConfiguration = GatewayConfiguration()
    desks: list[DeskConfiguration] = pydantic.Field(min_length=1)
    backends: dict[str, BackendConfiguration] = {}
    agent: AgentLoopConfiguration = AgentLoopConfiguration()
    sandbox: SandboxConfiguration = SandboxConfiguration()
    web: WebConfiguration = WebConfiguration()
    browser: BrowserConfiguration = BrowserConfiguration()
    risk: RiskConfiguration = RiskConfiguration()

    @pydantic.model_validator(mode='after')
    def _require_known_backends(self) -> AgentConfiguration:
        """Checks that every backend a desk names is defined in [backends].

        Returns:
            AgentConfiguration: This configuration, unchanged.

        Raises:
            ValueError: A desk names a backend that does not exist.
        """
        for desk in self.desks:
            for backend_name in desk.backend_order:
                if backend_name not in self.backends:
                    raise ValueError(
                        f'Desk {desk.name!r} names unknown backend {backend_name!r}'
                    )
        return self

    @pydantic.model_validator(mode='after')
    def _require_unique_desk_names(self) -> AgentConfiguration:
        """Checks that no two desks share a name.

        Returns:
            AgentConfiguration: This configuration, unchanged.

        Raises:
            ValueError: Two desks have the same name.
        """
        seen_names = set()
        for desk in self.desks:
            if desk.name in seen_names:
                raise ValueError(f'Duplicate desk name: {desk.name!r}')
            seen_names.add(desk.name)
        return self
