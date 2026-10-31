"""Reads the hard limits from the fenced ```toml limits block of TradingRules.md.

The file is read before every order, so an accepted change to the rules takes effect on the next order. A file without the block, or with a block that is not valid, makes the risk engine refuse every order that is not closing a position: when the limits cannot be known, the safe answer is no.

Typical usage example:

  limits = TradingLimitsReader(Path('workspace/shared/TradingRules.md')).read()
  limits.account.daily_loss_limit_percent
"""

import re
import tomllib
from pathlib import Path

import pydantic

_LIMITS_BLOCK = re.compile(r'```toml limits\s*\n(.*?)\n```', re.DOTALL)
_WINDOW_PATTERN = r'^(exchange_hours|\d{2}:\d{2}-\d{2}:\d{2})$'


class LimitsError(ValueError):
    """TradingRules.md has no readable limits block."""


class AccountLimits(pydantic.BaseModel):
    """The limits for the whole account, shared by every trader.

    Attributes:
        trading_enabled: Whether any trader may open or enlarge a position.
        capital_percent: The share of the total balance the agent may commit as margin.
        daily_loss_limit_percent: Today's loss, as a share of the live total balance, that stops every trader and closes every position.
        weekly_loss_limit_percent: This week's loss, as a share of the live total balance, that stops every trader until Monday.
        maximum_order_value_percent: The largest margin one order may block, as a share of the live total balance.
        maximum_open_positions: The most instruments that may be held at once, or None for no cap.
        trading_window: "exchange_hours" for each exchange's own session, or "HH:MM-HH:MM" in India time for every exchange.
        allow_option_writing: Whether a trader may sell options to open or enlarge a short position.
    """

    model_config = pydantic.ConfigDict(extra='forbid')

    trading_enabled: bool = False
    capital_percent: float = pydantic.Field(default=0, ge=0, le=100)
    daily_loss_limit_percent: float = pydantic.Field(default=0, ge=0, le=100)
    weekly_loss_limit_percent: float = pydantic.Field(default=0, ge=0, le=100)
    maximum_order_value_percent: float = pydantic.Field(default=0, ge=0, le=100)
    maximum_open_positions: int | None = pydantic.Field(default=None, ge=0)
    trading_window: str = pydantic.Field(
        default='exchange_hours',
        pattern=_WINDOW_PATTERN,
    )
    allow_option_writing: bool = False


class TraderLimits(pydantic.BaseModel):
    """The limits for one trader, on top of the account's.

    Attributes:
        capital_share_percent: The trader's share of the agent's capital, or None to draw on the shared pool.
        allowed_products: The products the trader may use, such as mis, cnc or nrml; empty allows all.
        allowed_instruments: The symbols the trader may trade; empty allows all.
        maximum_orders_per_minute: How many orders the trader may send in a minute, or None for no cap.
        daily_loss_limit_percent: Today's loss on the instruments this trader owned, as a share of the live total balance, that stops this trader alone for the rest of the day; None for no trader limit.
    """

    model_config = pydantic.ConfigDict(extra='forbid')

    capital_share_percent: float | None = pydantic.Field(
        default=None, gt=0, le=100
    )
    allowed_products: list[str] = []
    allowed_instruments: list[str] = []
    maximum_orders_per_minute: int | None = pydantic.Field(default=None, gt=0)
    daily_loss_limit_percent: float | None = pydantic.Field(
        default=None, gt=0, le=100
    )


class TradingLimits(pydantic.BaseModel):
    """Everything in the limits block.

    Attributes:
        account: The account-wide limits.
        traders: The per-trader limits, keyed by trader name; a trader without an entry has no extra limits.
    """

    model_config = pydantic.ConfigDict(extra='forbid')

    account: AccountLimits
    traders: dict[str, TraderLimits] = {}

    def trader(self, trader_name: str) -> TraderLimits:
        """The limits of one trader.

        Args:
            trader_name (str): The trader.

        Returns:
            TraderLimits: Its limits, or limits that add nothing when the trader has no entry.
        """
        return self.traders.get(trader_name, TraderLimits())


class TradingLimitsReader:
    """Reads the limits block from one TradingRules.md."""

    def __init__(self, rules_file: Path):
        """Remembers which file to read.

        Args:
            rules_file (Path): The TradingRules.md file.
        """
        self._rules_file = rules_file

    def read(self) -> TradingLimits:
        """Reads and checks the limits block.

        Returns:
            TradingLimits: The limits.

        Raises:
            LimitsError: The file is missing, has no limits block, or the block is not valid TOML with valid values.
        """
        try:
            text = self._rules_file.read_text(encoding='utf-8')
        except FileNotFoundError as error:
            raise LimitsError(f'{self._rules_file} does not exist') from error
        match = _LIMITS_BLOCK.search(text)
        if match is None:
            raise LimitsError(
                f'{self._rules_file.name} has no ```toml limits block'
            )
        try:
            parsed = tomllib.loads(match.group(1))
            return TradingLimits.model_validate(parsed)
        except (tomllib.TOMLDecodeError, pydantic.ValidationError) as error:
            raise LimitsError(
                f'The limits block in {self._rules_file.name} is not valid: {error}'
            ) from error
