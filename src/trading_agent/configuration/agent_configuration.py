"""The shape of trading_agent.toml, checked when it is read.

Each class describes one table of the file. Pydantic checks every value against its type and range, so a typing mistake in the file is reported by name when the program starts.

Typical usage example:

  configuration = AgentConfiguration.model_validate(parsed_toml)
  port = configuration.gateway.port
"""

from pathlib import Path
from typing import Annotated, Literal

import pydantic


class GatewayConfiguration(pydantic.BaseModel):
    """Where the gateway's web server listens.

    Attributes:
        host: The address to listen on. 127.0.0.1 keeps the gateway reachable from this machine only.
        port: The TCP port to listen on.
        frontend_directory: The built web page, served at every address that is not part of the API.
        allowed_origins: The other web origins whose pages may call the API, such as "https://localhost" for the Android app; empty allows none.
    """

    model_config = pydantic.ConfigDict(extra='forbid')

    host: str = '127.0.0.1'
    port: int = pydantic.Field(default=8120, gt=0, lt=65536)
    frontend_directory: Path = Path('frontend/dist')
    allowed_origins: list[str] = []


_CLOCK_PATTERN = r'^([01][0-9]|2[0-3]):[0-5][0-9]$'
TRADER_NAME_PATTERN = r'^[a-z][a-z0-9_-]{0,199}$'


class TraderConfiguration(pydantic.BaseModel):
    """One trader, which is one independent agent, as kept in its trader.toml.

    Attributes:
        name: The trader's name, used in folder names, order tags and the web interface: lower-case letters, digits, hyphens and underscores, starting with a letter, at most 200 characters.
        mandate: What the trader trades and how, in a sentence or two, or an empty string for a trader made before records kept it.
        created_at: When the trader was created, as an ISO 8601 string, or an empty string for a trader made before records kept it.
        retired: Whether the trader has been retired; a retired trader keeps its files but does not run.
        backend_order: The backends the trader may use, most preferred first, by their names in [backends].
        heartbeat_minutes: Minutes between heartbeats while NSE equities trade, or None for no heartbeat; each heartbeat is a model turn.
        rollover_time: The India time on trading days, as HH:MM, when the trader's session rolls over with a summary.
        scheduled_checks: India times on trading days, as HH:MM, when the trader is woken to do what its Persona.md says for that time of day.
    """

    model_config = pydantic.ConfigDict(extra='forbid')

    name: str = pydantic.Field(pattern=TRADER_NAME_PATTERN)
    mandate: str = ''
    created_at: str = ''
    retired: bool = False
    backend_order: list[str] = []
    heartbeat_minutes: int | None = pydantic.Field(default=None, ge=1, le=240)
    rollover_time: str = pydantic.Field(
        default='15:45',
        pattern=_CLOCK_PATTERN,
    )
    scheduled_checks: list[
        Annotated[
            str,
            pydantic.StringConstraints(pattern=_CLOCK_PATTERN),
        ]
    ] = []


class TradersConfiguration(pydantic.BaseModel):
    """How traders are made; the traders themselves are kept in workspace/traders/<name>/trader.toml.

    Attributes:
        backend_order: The backends a new trader may use, most preferred first.
        heartbeat_minutes: A new trader's minutes between heartbeats, or None for no heartbeat.
        rollover_time: A new trader's daily rollover time in India time, as HH:MM.
        first_trader: The trader created when the workspace has none.
    """

    model_config = pydantic.ConfigDict(extra='forbid')

    backend_order: list[str] = []
    heartbeat_minutes: int | None = pydantic.Field(default=None, ge=1, le=240)
    rollover_time: str = pydantic.Field(
        default='15:45',
        pattern=_CLOCK_PATTERN,
    )
    first_trader: str = pydantic.Field(
        default='general',
        pattern=TRADER_NAME_PATTERN,
    )


class AgentLoopConfiguration(pydantic.BaseModel):
    """Limits that keep one turn of the agent loop under control.

    Attributes:
        maximum_rounds: The most model calls one turn may make before it is stopped.
        maximum_identical_tool_calls: How many times one tool may be called with the same arguments in a turn.
        tool_timeout_seconds: How long one tool call may run before it is stopped.
        compression_threshold: The share of a model's context window at which, before the next turn, the trader saves what matters and its conversation is compressed into a summary.
        emergency_compression_threshold: The higher share at which a conversation is compressed in the middle of a long turn, without the memory flush.
    """

    model_config = pydantic.ConfigDict(extra='forbid')

    maximum_rounds: int = pydantic.Field(default=20, gt=0)
    maximum_identical_tool_calls: int = pydantic.Field(default=3, gt=0)
    tool_timeout_seconds: float = pydantic.Field(default=60.0, gt=0)
    compression_threshold: float = pydantic.Field(default=0.70, gt=0, lt=1)
    emergency_compression_threshold: float = pydantic.Field(
        default=0.85, gt=0, lt=1
    )

    @pydantic.model_validator(mode='after')
    def _require_emergency_above_normal(self) -> AgentLoopConfiguration:
        """Checks that mid-turn compression only happens above the normal threshold.

        Returns:
            AgentLoopConfiguration: This configuration, unchanged.

        Raises:
            ValueError: The emergency threshold is not above the normal one.
        """
        if self.emergency_compression_threshold <= self.compression_threshold:
            raise ValueError(
                'emergency_compression_threshold must be above compression_threshold'
            )
        return self


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
        passed_environment: Names of environment variables passed from the gateway into the sandbox, which otherwise starts with an empty environment. A skill that needs a variable is shown only when it is passed here.
    """

    model_config = pydantic.ConfigDict(extra='forbid')

    command_timeout_seconds: float = pydantic.Field(default=120.0, gt=0)
    maximum_output_characters: int = pydantic.Field(default=20000, gt=0)
    hidden_paths: list[str] = _DEFAULT_HIDDEN_PATHS
    passed_environment: list[str] = []


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
        ownership_grace_minutes: How long a trader keeps its claim on an instrument it ordered but does not yet hold, before the claim lapses.
        margin_rates: The rates used to estimate an order's margin.
    """

    model_config = pydantic.ConfigDict(extra='forbid')

    ownership_grace_minutes: float = pydantic.Field(default=30.0, gt=0)
    margin_rates: MarginRatesConfiguration = MarginRatesConfiguration()


class SkillsConfiguration(pydantic.BaseModel):
    """How the traders' skills are kept.

    Attributes:
        archive_after_days: How many days a trader's own skill may go unused before the daily curator archives it.
    """

    model_config = pydantic.ConfigDict(extra='forbid')

    archive_after_days: int = pydantic.Field(default=30, gt=0)


class BrowserConfiguration(pydantic.BaseModel):
    """How each trader's Chrome browser runs.

    Attributes:
        headless: Whether Chrome runs without a window. Turn it off to watch a trader browse.
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
    """One model backend that a trader can use.

    Attributes:
        kind: How the model is reached: "ollama", "openai_compatible", "deepseek" or "claude_code".
        base_url: The server address, needed by the ollama, openai_compatible and deepseek kinds.
        model: The model name the server knows the model by.
        context_window: How many tokens of context the model is given.
        thinking: Whether the model reasons before answering, for models that support it.
        effort: How hard Claude thinks ("low", "medium", "high", "xhigh" or "max") for the claude_code kind, or None for Claude Code's default.
        api_key_variable: The environment variable, or .env entry, holding this backend's API key, such as "DEEPSEEK_API_KEY"; None uses TRADING_AGENT_OPENAI_API_KEY.
        vision: Whether the model can read pictures; when False, pictures are left out of what it is sent and it is told so.
        other_models: Other models of the same provider that the chat page's model menu offers for this backend, such as "claude-haiku-5-5".
        rupees_per_million_prompt_tokens: The price of a million prompt tokens, for /usage to show costs, or None.
        rupees_per_million_completion_tokens: The price of a million completion tokens, or None.
        usd_per_million_cache_hit_tokens: For the deepseek kind, the peak-hour price of a million prompt tokens read from the cache, or None.
        usd_per_million_cache_miss_tokens: For the deepseek kind, the peak-hour price of a million other prompt tokens, or None.
        usd_per_million_completion_tokens: For the deepseek kind, the peak-hour price of a million completion tokens, or None.
        peak_hours_utc: The peak-price periods on weekdays, such as "01:00-04:00", in UTC; outside them the off-peak factor applies.
        off_peak_price_factor: What off-peak prices are as a share of peak prices, such as 0.5.
    """

    model_config = pydantic.ConfigDict(extra='forbid')

    kind: Literal['ollama', 'openai_compatible', 'deepseek', 'claude_code']
    base_url: str | None = None
    model: str
    context_window: int = pydantic.Field(gt=0)
    thinking: bool = True
    effort: Literal['low', 'medium', 'high', 'xhigh', 'max'] | None = None
    api_key_variable: str | None = None
    vision: bool = True
    other_models: list[str] = []
    usd_per_million_cache_hit_tokens: float | None = pydantic.Field(
        default=None, ge=0
    )
    usd_per_million_cache_miss_tokens: float | None = pydantic.Field(
        default=None, ge=0
    )
    usd_per_million_completion_tokens: float | None = pydantic.Field(
        default=None, ge=0
    )
    peak_hours_utc: list[str] = []
    off_peak_price_factor: float = pydantic.Field(default=1.0, gt=0, le=1)
    rupees_per_million_prompt_tokens: float | None = pydantic.Field(
        default=None, ge=0
    )
    rupees_per_million_completion_tokens: float | None = pydantic.Field(
        default=None, ge=0
    )

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


TELEGRAM_NOTIFICATIONS = (
    'fills',
    'rejections',
    'model_switches',
    'job_results',
    'trader_reports',
    'messages',
    'alerts',
    'halts',
    'errors',
    'daily_summaries',
)

PUSH_NOTIFICATIONS = (
    'fills',
    'rejections',
    'model_switches',
    'job_results',
    'trader_reports',
    'messages',
    'alerts',
    'halts',
    'errors',
    'requests',
)


class ApprovalConfiguration(pydantic.BaseModel):
    """Which of the traders' actions wait for the user's permission.

    Attributes:
        tools: The tools whose every call by a trader or subagent waits for the user's permission, such as "flatten_trader"; empty for none.
        expiry_minutes: How long a permission request stays open before it lapses and the action is not run.
    """

    model_config = pydantic.ConfigDict(extra='forbid')

    tools: list[str] = []
    expiry_minutes: int = pydantic.Field(default=5, ge=1, le=1440)


class TelegramConfiguration(pydantic.BaseModel):
    """The Telegram channel.

    Attributes:
        enabled: Whether the gateway talks to Telegram; it also needs TRADING_AGENT_TELEGRAM_BOT_TOKEN in .env.
        default_trader: The trader a paired chat talks to until it chooses another with /trader.
        notifications: What is pushed to every paired chat without being asked: fills, rejections, model_switches, job_results, trader_reports, messages, alerts, halts, errors and daily_summaries.
        poll_seconds: How long one long-poll request to Telegram waits for new messages before asking again.
    """

    model_config = pydantic.ConfigDict(extra='forbid')

    enabled: bool = False
    default_trader: str = pydantic.Field(
        default='general',
        pattern=TRADER_NAME_PATTERN,
    )
    notifications: list[str] = list(TELEGRAM_NOTIFICATIONS)
    poll_seconds: int = pydantic.Field(default=30, ge=1, le=50)

    @pydantic.field_validator('notifications')
    @classmethod
    def _require_known_notifications(
        cls, notifications: list[str]
    ) -> list[str]:
        """Checks that every notification name is known.

        Args:
            notifications (list[str]): The names.

        Returns:
            list[str]: The names, unchanged.

        Raises:
            ValueError: A name is not one of TELEGRAM_NOTIFICATIONS.
        """
        for name in notifications:
            if name not in TELEGRAM_NOTIFICATIONS:
                raise ValueError(
                    f'Unknown Telegram notification {name!r}; known ones are {", ".join(TELEGRAM_NOTIFICATIONS)}'
                )
        return notifications


class PushConfiguration(pydantic.BaseModel):
    """Push notifications to the Android app through Firebase Cloud Messaging.

    Attributes:
        enabled: Whether the gateway sends notifications; it also needs TRADING_AGENT_FIREBASE_SERVICE_ACCOUNT_FILE in .env.
        notifications: What is pushed to every registered phone: fills, rejections, model_switches, job_results, trader_reports, messages, alerts, halts, errors and requests (permissions, questions and plans waiting for the user).
    """

    model_config = pydantic.ConfigDict(extra='forbid')

    enabled: bool = False
    notifications: list[str] = list(PUSH_NOTIFICATIONS)

    @pydantic.field_validator('notifications')
    @classmethod
    def _require_known_notifications(
        cls, notifications: list[str]
    ) -> list[str]:
        """Checks that every notification name is known.

        Args:
            notifications (list[str]): The names.

        Returns:
            list[str]: The names, unchanged.

        Raises:
            ValueError: A name is not one of PUSH_NOTIFICATIONS.
        """
        for name in notifications:
            if name not in PUSH_NOTIFICATIONS:
                raise ValueError(
                    f'Unknown push notification {name!r}; known ones are {", ".join(PUSH_NOTIFICATIONS)}'
                )
        return notifications


class AgentConfiguration(pydantic.BaseModel):
    """Everything in trading_agent.toml.

    Attributes:
        mode: "dry_run" sends every order to UBI as a dry run, and "live" sends real orders.
        workspace_directory: The folder holding the traders' files, memory and journals.
        tradingmachine_environment_file: The .env file that tradingmachine reads its UBI and MongoDB settings from.
        mcp_servers_file: The JSON file listing the MCP servers every trader can use.
        market_calendar_directory: UBI's folder of yearly exchange calendars, or None to know weekends only.
        gateway: Where the web server listens.
        traders: How traders are made; each trader's own settings are in its trader.toml.
        backends: The model backends, keyed by the name traders refer to them by.
        agent: The limits of the agent loop.
        sandbox: How the bash terminal's sandbox is built.
        web: Where web search goes and how pages are fetched.
        browser: How each trader's Chrome browser runs.
        risk: How the risk engine works, apart from the limits in TradingRules.md.
        skills: How the traders' skills are kept.
        telegram: The Telegram channel.
        push: Push notifications to the Android app.
        approvals: Which actions wait for the user's permission.
    """

    model_config = pydantic.ConfigDict(extra='forbid')

    mode: Literal['dry_run', 'live'] = 'dry_run'
    workspace_directory: Path = Path('workspace')
    tradingmachine_environment_file: Path
    mcp_servers_file: Path = Path('mcp_servers.json')
    market_calendar_directory: Path | None = None
    gateway: GatewayConfiguration = GatewayConfiguration()
    traders: TradersConfiguration = TradersConfiguration()
    backends: dict[str, BackendConfiguration] = {}
    agent: AgentLoopConfiguration = AgentLoopConfiguration()
    sandbox: SandboxConfiguration = SandboxConfiguration()
    web: WebConfiguration = WebConfiguration()
    browser: BrowserConfiguration = BrowserConfiguration()
    risk: RiskConfiguration = RiskConfiguration()
    skills: SkillsConfiguration = SkillsConfiguration()
    telegram: TelegramConfiguration = TelegramConfiguration()
    push: PushConfiguration = PushConfiguration()
    approvals: ApprovalConfiguration = ApprovalConfiguration()

    @pydantic.model_validator(mode='after')
    def _require_known_backends(self) -> AgentConfiguration:
        """Checks that every backend in [traders] backend_order is defined in [backends].

        Returns:
            AgentConfiguration: This configuration, unchanged.

        Raises:
            ValueError: The order names a backend that does not exist.
        """
        for backend_name in self.traders.backend_order:
            if backend_name not in self.backends:
                raise ValueError(
                    f'[traders] backend_order names unknown backend {backend_name!r}'
                )
        return self
