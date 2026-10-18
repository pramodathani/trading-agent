"""Tests for the terminal's formatter, tool describer and event describer."""

from trading_agent.terminal import event_describer
from trading_agent.terminal import formatter
from trading_agent.terminal import tool_describer


class TestFormatter:
    """Tests for Indian money, token counts and durations."""

    def test_money_uses_indian_grouping(self) -> None:
        """Lakhs and crores are grouped in twos after the first three digits."""
        money = formatter.Formatter()

        assert money.money(123456.7) == '₹1,23,456.70'
        assert money.money(12345678.0) == '₹1,23,45,678.00'
        assert money.money(999.0) == '₹999.00'
        assert money.money(None) == '—'

    def test_signed_money(self) -> None:
        """A profit gets a plus sign and a loss a minus sign."""
        money = formatter.Formatter()

        assert money.signed_money(1250.0) == '+₹1,250.00'
        assert money.signed_money(-300.0) == '−₹300.00'

    def test_token_counts_and_durations(self) -> None:
        """Token counts shorten to k and M, and durations read like Claude Code's."""
        numbers = formatter.Formatter()

        assert numbers.token_count(850) == '850'
        assert numbers.token_count(12345) == '12.3k'
        assert numbers.token_count(1000000) == '1M'
        assert numbers.elapsed_text(12) == '12s'
        assert numbers.elapsed_text(137) == '2m 17s'

    def test_india_clock_time(self) -> None:
        """A UTC timestamp is shown as an India clock time."""
        assert (
            formatter.Formatter().time('2026-10-19T04:30:05+00:00')
            == '10:00:05'
        )


class TestToolDescriber:
    """Tests for the words used for tool calls."""

    def test_activity_strips_the_mcp_prefix(self) -> None:
        """A tool served over MCP is described by its own name."""
        describer = tool_describer.ToolDescriber()

        assert (
            describer.activity('mcp__trading_agent__get_quote')
            == 'Fetching a quote'
        )
        assert describer.activity('mystery') == 'Using mystery'

    def test_detail_takes_the_most_telling_argument(self) -> None:
        """The symbol of a quote is its detail."""
        describer = tool_describer.ToolDescriber()

        assert describer.detail('{"symbol": "RELIANCE"}') == 'RELIANCE'
        assert describer.detail('not json') == ''

    def test_summary_counts_kinds_and_failures(self) -> None:
        """Several calls are summed up in one sentence, with failures counted."""
        describer = tool_describer.ToolDescriber()

        summary = describer.summary(
            [
                (
                    'get_quote',
                    False,
                ),
                (
                    'get_quote',
                    False,
                ),
                (
                    'bash_run',
                    True,
                ),
            ]
        )

        assert summary == 'Fetched 2 quotes, ran a command (1 failed)'


class TestEventDescriber:
    """Tests for the words used for events."""

    def test_risk_refusal_is_a_warning(self) -> None:
        """A refused order is described with the risk engine's reasons."""
        description = event_describer.EventDescriber().describe(
            {
                'kind': 'risk_decision',
                'payload': {
                    'approved': False,
                    'order': 'BUY 10 RELIANCE',
                    'reasons': [
                        'Over the limit.',
                    ],
                },
            }
        )

        assert description.title == 'Risk engine refused: BUY 10 RELIANCE'
        assert description.detail == 'Over the limit.'
        assert description.tone == 'warning'

    def test_fill_with_money(self) -> None:
        """A fill names the quantity and the average price."""
        description = event_describer.EventDescriber().describe(
            {
                'kind': 'fill',
                'payload': {
                    'status': 'COMPLETE',
                    'filled_quantity': 10,
                    'average_price': 2945.5,
                },
            }
        )

        assert description.title == 'Order complete: 10 at 2,945.50'
        assert description.tone == 'good'

    def test_unknown_kind(self) -> None:
        """An unknown kind is named in words, with its payload as detail."""
        description = event_describer.EventDescriber().describe(
            {
                'kind': 'something_new',
                'payload': {
                    'a': 1,
                },
            }
        )

        assert description.title == 'something new'
        assert '"a": 1' in description.detail
