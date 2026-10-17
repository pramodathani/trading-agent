"""Starts, resumes and rolls over a desk's sessions.

When the desk starts, the keeper asks the model router to pick up the session saved before a restart. Before each turn it checks the India date: on the first turn of a new day it asks the desk to summarise the old session and fold the day's notes into Memory.md, saves that summary, and starts a fresh session. The first message of every new session carries the most recent summary, so the desk knows what happened last.

Typical usage example:

  keeper = SessionKeeper('main', router, store, event_bus)
  await keeper.start()
  trigger = await keeper.prepare(trigger)
"""

import dataclasses
import datetime
import logging
from pathlib import Path

from trading_agent.backends import backend as backend_module
from trading_agent.backends import model_router as model_router_module
from trading_agent.memory import session_store as session_store_module
from trading_agent.runtime import event as event_module
from trading_agent.runtime import event_bus as event_bus_module
from trading_agent.runtime import trigger as trigger_module
from trading_agent.skills import skill_curator as skill_curator_module

_LOGGER = logging.getLogger(__name__)
_FALLBACK_TRIGGER_CHARACTERS = 300
_FALLBACK_ANSWER_CHARACTERS = 600


class SessionKeeper:
    """Looks after one desk's sessions."""

    def __init__(
        self,
        desk_name: str,
        router: model_router_module.ModelRouter,
        store: session_store_module.SessionStore,
        event_bus: event_bus_module.EventBus,
        curator: skill_curator_module.SkillCurator | None = None,
    ):
        """Creates the keeper.

        Args:
            desk_name (str): The desk.
            router (model_router_module.ModelRouter): The desk's router, built with the same store.
            store (session_store_module.SessionStore): The desk's sessions folder.
            event_bus (event_bus_module.EventBus): Where new sessions are announced.
            curator (skill_curator_module.SkillCurator | None): Reviews the desk's own skills after the day's summary, or None to skip the review.
        """
        self._desk_name = desk_name
        self._router = router
        self._store = store
        self._event_bus = event_bus
        self._curator = curator

    async def start(self) -> None:
        """Picks up the saved session, or starts the first one, when the desk starts."""
        resumed = await self._router.restore_session()
        reason = 'first'
        if resumed:
            reason = 'resumed'
        self._publish_session_started(reason, None, None)

    async def prepare(
        self,
        trigger: trigger_module.Trigger,
    ) -> trigger_module.Trigger:
        """Rolls over to a new session on a new day, and seeds a new session's first message.

        Args:
            trigger (trigger_module.Trigger): The trigger about to run.

        Returns:
            trigger_module.Trigger: The trigger, with the previous session's summary in front when the session is new.
        """
        if self._router.trading_date != self._store.today():
            await self.roll_over()
        if self._router.exchanges:
            return trigger
        summary = self._store.latest_summary()
        if summary is None:
            return trigger
        text = '\n'.join(
            [
                f'[This is the first message of a new session. Summary of your previous session, from {summary.trading_date.isoformat()}:]',
                summary.text,
                '[End of the summary. Your lasting lessons are in Memory.md. The message follows.]',
                '',
                trigger.text,
            ]
        )
        return dataclasses.replace(trigger, text=text)

    async def roll_over(self) -> None:
        """Ends the current session with a summary and starts a fresh one for today."""
        previous_session_id = self._router.session_id
        previous_date = self._router.trading_date
        summary_path = None
        if self._router.exchanges and previous_date is not None:
            summary = await self._summary(previous_date)
            summary_path = self._store.write_summary(previous_date, summary)
            await self._review_skills(previous_date)
        await self._router.reset()
        self._publish_session_started(
            'daily_rollover',
            previous_session_id,
            summary_path,
        )

    async def _summary(self, trading_date: datetime.date) -> str:
        """Asks the desk to summarise its session, or lists the exchanges when no model can.

        Args:
            trading_date (datetime.date): The day the session belongs to.

        Returns:
            str: The summary.
        """
        request = trigger_module.Trigger.now(
            trigger_module.TriggerSource.ROLLOVER,
            self._desk_name,
            '\n'.join(
                [
                    f'[Your session for {trading_date.isoformat()} is ending, and a fresh session starts next. Two jobs before it does:]',
                    f'1. Read your notes for the day (notes/{trading_date.isoformat()}.md, if it exists) and fold what is worth keeping into Memory.md with edit_file or write_file: add new lessons, correct or remove ones that proved wrong, and keep it short and organised.',
                    '2. Then reply with a summary of the session for your next session to read: positions and open orders you hold, trades made and why, what worked and what did not, and what you plan to do next. Write plain text under 400 words. Your reply is saved as the summary.',
                ]
            ),
        )
        try:
            result = await self._router.run_turn(request)
        except backend_module.BackendUnavailableError:
            _LOGGER.exception(
                'No model could summarise the session of desk %s',
                self._desk_name,
            )
            return self._fallback_summary()
        if not result.text.strip():
            return self._fallback_summary()
        return result.text

    async def _review_skills(self, trading_date: datetime.date) -> None:
        """Archives unused skills and gives the desk its daily skill review turn.

        The review runs in the old session, right after the summary, while the whole day is still in the desk's context. A review that fails is logged and the rollover carries on.

        Args:
            trading_date (datetime.date): The day being closed.
        """
        if self._curator is None:
            return
        archived = self._curator.archive_unused(self._store.today())
        request = trigger_module.Trigger.now(
            trigger_module.TriggerSource.ROLLOVER,
            self._desk_name,
            self._curator.review_request(trading_date, archived),
        )
        try:
            await self._router.run_turn(request)
        except backend_module.BackendUnavailableError:
            _LOGGER.exception(
                'No model could review the skills of desk %s', self._desk_name
            )

    def _fallback_summary(self) -> str:
        """Lists the session's exchanges, shortened, when no model could write a summary.

        Returns:
            str: The listing.
        """
        lines = [
            'No model was available to summarise this session, so these are its exchanges, shortened:',
        ]
        for exchange in self._router.exchanges:
            trigger_text = exchange.trigger_text[:_FALLBACK_TRIGGER_CHARACTERS]
            answer = exchange.answer[:_FALLBACK_ANSWER_CHARACTERS]
            lines.append(f'- Trigger: {trigger_text}')
            lines.append(f'  Answer from {exchange.backend_name}: {answer}')
        return '\n'.join(lines)

    def _publish_session_started(
        self,
        reason: str,
        previous_session_id: str | None,
        summary_path: Path | None,
    ) -> None:
        """Announces which session the desk is now in.

        Args:
            reason (str): "first", "resumed" or "daily_rollover".
            previous_session_id (str | None): The session that ended, for a rollover.
            summary_path (Path | None): The summary written for the ended session, or None.
        """
        payload = {
            'session_id': self._router.session_id,
            'reason': reason,
            'exchanges': len(self._router.exchanges),
        }
        if previous_session_id is not None:
            payload['previous_session_id'] = previous_session_id
        if summary_path is not None:
            payload['summary_file'] = str(summary_path)
        self._event_bus.publish(
            event_module.Event.now(
                event_module.EventKind.SESSION_STARTED,
                self._desk_name,
                payload,
            )
        )
