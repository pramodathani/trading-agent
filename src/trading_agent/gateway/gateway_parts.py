"""What the gateway's API routes can reach: the parts of each desk, and the parts every desk shares.

The desk builder fills these in as it builds the desks, and the application hands them to the route groups. Each route group takes only the parts it uses, so it can be tested with stand-ins for the rest.

Typical usage example:

  parts = builder.desk_parts('main')
  parts.sessions.exchanges(session_id)
"""

import dataclasses

from trading_agent.attachments import attachment_store
from trading_agent.extensions import installed_packages
from trading_agent.memory import checkpoints
from trading_agent.memory import session_store
from trading_agent.risk import account_snapshot
from trading_agent.risk import kill_switch
from trading_agent.risk import risk_engine
from trading_agent.risk import risk_ledger
from trading_agent.scheduling import cron_job
from trading_agent.scheduling import cron_job_store
from trading_agent.scheduling import market_calendar
from trading_agent.scheduling import price_alert_store
from trading_agent.skills import skill_library
from trading_agent.subagents import subagent_library
from trading_agent.tools import tool_registry
from trading_agent.trading import broker_reader
from trading_agent.trading import desk_order_book
from trading_agent.workspace import proposal_store
from trading_agent.workspace import workspace_layout


@dataclasses.dataclass
class DeskParts:
    """One desk's stores and tools.

    Attributes:
        sessions: Its sessions, exchanges and daily summaries.
        jobs: Its scheduled jobs and their runs.
        built_in_jobs: Its heartbeat, rollover and scheduled checks.
        alerts: Its price alerts.
        skills: Its usable and hidden skills.
        checkpoints: The snapshots of its own files.
        tools: Its tools, for actions such as flatten_desk.
    """

    sessions: session_store.SessionStore
    jobs: cron_job_store.CronJobStore
    built_in_jobs: list[cron_job.CronJob]
    alerts: price_alert_store.PriceAlertStore
    skills: skill_library.SkillLibrary
    checkpoints: checkpoints.Checkpoints
    tools: tool_registry.ToolRegistry


@dataclasses.dataclass
class SharedParts:
    """The parts every desk shares.

    Attributes:
        layout: Where the workspace's files are.
        reader: The UBI reader.
        snapshot_reader: Reads balances and positions.
        risk_engine: The one risk engine.
        ledger: The risk ledger: ownership, halts, daily profit and loss.
        kill_switch: Halts and flattens the whole account.
        order_book: Which desk placed which order.
        proposals: The desks' proposed changes to the user's files.
        subagents: The subagent definitions.
        packages: The installed packages.
        calendar: The exchange calendar.
        attachments: The files the user sends with messages.
    """

    layout: workspace_layout.WorkspaceLayout
    reader: broker_reader.BrokerReader
    snapshot_reader: account_snapshot.AccountSnapshotReader
    risk_engine: risk_engine.RiskEngine
    ledger: risk_ledger.RiskLedger
    kill_switch: kill_switch.KillSwitch
    order_book: desk_order_book.DeskOrderBook
    proposals: proposal_store.ProposalStore
    subagents: subagent_library.SubagentLibrary
    packages: installed_packages.InstalledPackages
    calendar: market_calendar.MarketCalendar
    attachments: attachment_store.AttachmentStore
