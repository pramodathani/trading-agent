"""Talks to a running gateway's HTTP routes, one method per route, as the web page's apiClient.ts does.

Every request carries the access token as a Bearer header. A route that answers with an error raises GatewayError with the gateway's own explanation.

Typical usage example:

  async with GatewayClient('http://127.0.0.1:8120', token) as gateway:
      desks = await gateway.desks()
      reply = await gateway.send_message('general', '/status')
"""

import urllib.parse
from collections.abc import Sequence
from pathlib import Path
from types import TracebackType
from typing import Any, Self

import httpx

_TIMEOUT_SECONDS = 30.0
_JOURNAL_LIMIT = 1500


class GatewayError(Exception):
    """The gateway answered with an error, or could not be reached.

    Attributes:
        status_code: The HTTP status, or 0 when the gateway could not be reached.
        message: The gateway's explanation.
    """

    def __init__(self, status_code: int, message: str):
        """Creates the error.

        Args:
            status_code (int): The HTTP status, or 0 when the gateway could not be reached.
            message (str): The gateway's explanation.
        """
        super().__init__(f'HTTP {status_code}: {message}')
        self.status_code = status_code
        self.message = message


class GatewayClient:
    """A connection to the gateway's routes."""

    def __init__(
        self,
        base_url: str,
        access_token: str,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        """Creates the client without connecting.

        Args:
            base_url (str): The gateway's address, such as http://127.0.0.1:8120.
            access_token (str): The gateway's access token.
            transport (httpx.AsyncBaseTransport | None): A transport to use instead of the network, such as one that calls the gateway in the same process in tests.
        """
        self.base_url = base_url.rstrip('/')
        self._access_token = access_token
        self._http = httpx.AsyncClient(
            base_url=self.base_url,
            headers={
                'Authorization': f'Bearer {access_token}',
            },
            timeout=_TIMEOUT_SECONDS,
            transport=transport,
        )

    async def __aenter__(self) -> Self:
        """Opens the client.

        Returns:
            GatewayClient: The client.
        """
        return self

    async def __aexit__(
        self,
        error_type: type[BaseException] | None,
        error: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Closes the client's connections.

        Args:
            error_type (type[BaseException] | None): The type of the exception that ended the block, if any.
            error (BaseException | None): The exception, if any.
            traceback (TracebackType | None): Its traceback, if any.
        """
        await self.close()

    async def close(self) -> None:
        """Closes the client's connections."""
        await self._http.aclose()

    def events_address(self, desk_name: str | None = None) -> str:
        """The WebSocket address of the event stream, with the token.

        Args:
            desk_name (str | None): A desk to keep only that desk's events and events of no desk, or None for every event.

        Returns:
            str: Such as ws://127.0.0.1:8120/ws/events?token=....
        """
        query = {
            'token': self._access_token,
        }
        if desk_name is not None:
            query['desk'] = desk_name
        address = self.base_url.replace('http', 'ws', 1)
        return f'{address}/ws/events?{urllib.parse.urlencode(query)}'

    async def health(self) -> dict[str, Any]:
        """Whether the gateway is up; this route needs no token.

        Returns:
            dict[str, Any]: The status and each desk's state.
        """
        return await self._json('GET', '/api/health')

    async def desks(self) -> dict[str, Any]:
        """Every desk's state, models and session.

        Returns:
            dict[str, Any]: The mode and the desks.
        """
        return await self._json('GET', '/api/desks')

    async def desk(self, desk_name: str) -> dict[str, Any]:
        """One desk's state, with its persona.

        Args:
            desk_name (str): The desk.

        Returns:
            dict[str, Any]: The desk's summary and Persona.md text.
        """
        return await self._json('GET', f'/api/desks/{self._part(desk_name)}')

    async def desk_context(self, desk_name: str) -> dict[str, Any]:
        """How full a desk's context window is, and its tools.

        Args:
            desk_name (str): The desk.

        Returns:
            dict[str, Any]: The desk, its usage snapshot or None, and its tool names.
        """
        return await self._json(
            'GET', f'/api/desks/{self._part(desk_name)}/context'
        )

    async def desk_commands(self, desk_name: str) -> dict[str, Any]:
        """A desk's slash commands and usable skills.

        Args:
            desk_name (str): The desk.

        Returns:
            dict[str, Any]: The desk and its command entries.
        """
        return await self._json(
            'GET', f'/api/desks/{self._part(desk_name)}/commands'
        )

    async def send_message(
        self,
        desk_name: str,
        text: str,
        attachment_ids: Sequence[str] = (),
    ) -> str:
        """Queues a message or /command for a desk; the reply arrives on the event stream.

        Args:
            desk_name (str): The desk.
            text (str): The message or command.
            attachment_ids (Sequence[str]): Uploads to send with it.

        Returns:
            str: The trigger id that the reply's events carry.
        """
        answer = await self._json(
            'POST',
            f'/api/desks/{self._part(desk_name)}/messages',
            body={
                'text': text,
                'attachment_ids': list(attachment_ids),
            },
        )
        return answer['trigger_id']

    async def choose_model(
        self,
        desk_name: str,
        backend_name: str | None,
        model: str | None = None,
    ) -> dict[str, Any]:
        """Makes a desk try one backend first, or go back to the configured order.

        Args:
            desk_name (str): The desk.
            backend_name (str | None): The backend, or None for the configured order.
            model (str | None): Another model of that backend's provider, or None for its configured model.

        Returns:
            dict[str, Any]: The desk's new summary.
        """
        return await self._json(
            'POST',
            f'/api/desks/{self._part(desk_name)}/model',
            body={
                'backend': backend_name,
                'model': model,
            },
        )

    async def upload_attachment(
        self, desk_name: str, file_path: Path
    ) -> dict[str, Any]:
        """Uploads a file for a desk, to be named in a later message.

        Args:
            desk_name (str): The desk.
            file_path (Path): The file to upload.

        Returns:
            dict[str, Any]: The attachment, with its id, kind and any problem reading it.
        """
        with file_path.open('rb') as file:
            return await self._json(
                'POST',
                f'/api/desks/{self._part(desk_name)}/attachments',
                files={
                    'file': (file_path.name, file),
                },
            )

    async def attachment_bytes(
        self, desk_name: str, attachment_id: str
    ) -> bytes:
        """Downloads an attachment.

        Args:
            desk_name (str): The desk.
            attachment_id (str): The attachment's id.

        Returns:
            bytes: The file's contents.
        """
        return await self._bytes(
            f'/api/desks/{self._part(desk_name)}/attachments/{self._part(attachment_id)}'
        )

    async def picture_bytes(self, desk_name: str, picture_path: str) -> bytes:
        """Downloads a picture from inside a desk's folder.

        Args:
            desk_name (str): The desk.
            picture_path (str): The picture's path relative to the desk folder.

        Returns:
            bytes: The picture's contents.
        """
        encoded = '/'.join(
            self._part(segment) for segment in picture_path.split('/')
        )
        return await self._bytes(
            f'/api/desks/{self._part(desk_name)}/pictures/{encoded}'
        )

    async def pause(self, desk_name: str) -> dict[str, Any]:
        """Stops a desk asking models until it is resumed.

        Args:
            desk_name (str): The desk.

        Returns:
            dict[str, Any]: The desk's new summary.
        """
        return await self._json(
            'POST', f'/api/desks/{self._part(desk_name)}/pause'
        )

    async def resume(self, desk_name: str) -> dict[str, Any]:
        """Makes a paused desk answer again.

        Args:
            desk_name (str): The desk.

        Returns:
            dict[str, Any]: The desk's new summary.
        """
        return await self._json(
            'POST', f'/api/desks/{self._part(desk_name)}/resume'
        )

    async def flatten(self, desk_name: str, reason: str) -> dict[str, Any]:
        """Cancels a desk's orders and closes its positions.

        Args:
            desk_name (str): The desk.
            reason (str): Why, for the journal.

        Returns:
            dict[str, Any]: The flatten tool's report text and whether it failed.
        """
        return await self._json(
            'POST',
            f'/api/desks/{self._part(desk_name)}/flatten',
            body={
                'reason': reason,
            },
        )

    async def requests(self, status: str = 'pending') -> list[dict[str, Any]]:
        """The desks' questions, plans and permission requests.

        Args:
            status (str): "pending" for the ones waiting for an answer, or "all".

        Returns:
            list[dict[str, Any]]: The requests.
        """
        answer = await self._json(
            'GET',
            '/api/requests',
            parameters={
                'status': status,
            },
        )
        return answer['requests']

    async def answer_questions(
        self,
        request_id: str,
        answers: Sequence[dict[str, Any]],
    ) -> dict[str, Any]:
        """Answers a desk's questions.

        Args:
            request_id (str): The request.
            answers (Sequence[dict[str, Any]]): One answer per question, each with "selected" labels and "other" text.

        Returns:
            dict[str, Any]: The request, now answered.
        """
        return await self._json(
            'POST',
            f'/api/requests/{self._part(request_id)}/answer',
            body={
                'answers': list(answers),
            },
        )

    async def decide_plan(
        self,
        request_id: str,
        decision: str,
        feedback: str,
    ) -> dict[str, Any]:
        """Approves a desk's plan or asks it to keep planning.

        Args:
            request_id (str): The request.
            decision (str): "approve" or "revise".
            feedback (str): What to change, or notes on the approval.

        Returns:
            dict[str, Any]: The request, now answered.
        """
        return await self._json(
            'POST',
            f'/api/requests/{self._part(request_id)}/plan',
            body={
                'decision': decision,
                'feedback': feedback,
            },
        )

    async def decide_permission(
        self,
        request_id: str,
        decision: str,
        reason: str,
    ) -> dict[str, Any]:
        """Allows or denies a tool call that needs permission.

        Args:
            request_id (str): The request.
            decision (str): "allow_once", "always_allow" or "deny".
            reason (str): Why, sent to the desk with a denial.

        Returns:
            dict[str, Any]: The request, with the call's result when it ran.
        """
        return await self._json(
            'POST',
            f'/api/requests/{self._part(request_id)}/permission',
            body={
                'decision': decision,
                'reason': reason,
            },
        )

    async def dismiss_request(self, request_id: str) -> dict[str, Any]:
        """Dismisses a question or plan without answering it.

        Args:
            request_id (str): The request.

        Returns:
            dict[str, Any]: The request, now dismissed.
        """
        return await self._json(
            'POST', f'/api/requests/{self._part(request_id)}/dismiss'
        )

    async def permission_grants(self) -> list[dict[str, Any]]:
        """The tools each desk may call without asking.

        Returns:
            list[dict[str, Any]]: The grants, each with desk, tool_name and granted_at.
        """
        answer = await self._json('GET', '/api/permissions')
        return answer['grants']

    async def revoke_permission(
        self, desk_name: str, tool_name: str
    ) -> dict[str, Any]:
        """Makes a desk ask again before calling a tool.

        Args:
            desk_name (str): The desk.
            tool_name (str): The tool.

        Returns:
            dict[str, Any]: Whether a grant was revoked.
        """
        return await self._json(
            'POST',
            '/api/permissions/revoke',
            body={
                'desk': desk_name,
                'tool_name': tool_name,
            },
        )

    async def account(self) -> dict[str, Any]:
        """The account's balance, profit and loss, positions, owners and halts.

        Returns:
            dict[str, Any]: The account.
        """
        return await self._json('GET', '/api/account')

    async def desk_orders(self) -> dict[str, Any]:
        """Each desk's open orders.

        Returns:
            dict[str, Any]: The orders, keyed by desk.
        """
        return await self._json('GET', '/api/desk-orders')

    async def broker_orders(self, kind: str = 'orders') -> dict[str, Any]:
        """UBI's own order book.

        Args:
            kind (str): "orders", "trades" or "open_parents".

        Returns:
            dict[str, Any]: The rows, keyed by kind.
        """
        return await self._json(
            'GET',
            '/api/orders',
            parameters={
                'kind': kind,
            },
        )

    async def kill(self, reason: str) -> dict[str, Any]:
        """Fires the kill switch: every desk is halted and the account is flattened.

        Args:
            reason (str): Why, for the journal.

        Returns:
            dict[str, Any]: The kill switch's report.
        """
        return await self._json(
            'POST',
            '/api/account/kill',
            body={
                'confirm': 'FLATTEN',
                'reason': reason,
            },
        )

    async def desk_journal(
        self,
        desk_name: str,
        limit: int = _JOURNAL_LIMIT,
        day: str | None = None,
    ) -> dict[str, Any]:
        """A desk's events of one day, oldest first.

        Args:
            desk_name (str): The desk.
            limit (int): The most events to return, newest kept.
            day (str | None): The day as YYYY-MM-DD, or None for today.

        Returns:
            dict[str, Any]: The day and its events.
        """
        parameters = {
            'limit': str(limit),
        }
        if day is not None:
            parameters['day'] = day
        return await self._json(
            'GET',
            f'/api/desks/{self._part(desk_name)}/journal',
            parameters=parameters,
        )

    async def journal(self, limit: int = _JOURNAL_LIMIT) -> dict[str, Any]:
        """Today's events that belong to no desk, oldest first.

        Args:
            limit (int): The most events to return, newest kept.

        Returns:
            dict[str, Any]: The day and its events.
        """
        return await self._json(
            'GET',
            '/api/journal',
            parameters={
                'limit': str(limit),
            },
        )

    async def sessions(self, desk_name: str) -> dict[str, Any]:
        """A desk's sessions.

        Args:
            desk_name (str): The desk.

        Returns:
            dict[str, Any]: The current session id and every session with its exchange count.
        """
        return await self._json(
            'GET', f'/api/desks/{self._part(desk_name)}/sessions'
        )

    async def session(self, desk_name: str, session_id: str) -> dict[str, Any]:
        """One session's exchanges.

        Args:
            desk_name (str): The desk.
            session_id (str): The session.

        Returns:
            dict[str, Any]: The session id and its exchanges.
        """
        return await self._json(
            'GET',
            f'/api/desks/{self._part(desk_name)}/sessions/{self._part(session_id)}',
        )

    async def summaries(self, desk_name: str) -> dict[str, Any]:
        """A desk's daily summaries.

        Args:
            desk_name (str): The desk.

        Returns:
            dict[str, Any]: The summaries, each with date and text.
        """
        return await self._json(
            'GET', f'/api/desks/{self._part(desk_name)}/summaries'
        )

    async def notes(self, desk_name: str) -> dict[str, Any]:
        """A desk's notes files.

        Args:
            desk_name (str): The desk.

        Returns:
            dict[str, Any]: The notes, each with file and text.
        """
        return await self._json(
            'GET', f'/api/desks/{self._part(desk_name)}/notes'
        )

    async def search(self, desk_name: str, keywords: str) -> dict[str, Any]:
        """Searches a desk's memory.

        Args:
            desk_name (str): The desk.
            keywords (str): The words to look for.

        Returns:
            dict[str, Any]: Whether every word matched, and the hits.
        """
        return await self._json(
            'GET',
            f'/api/desks/{self._part(desk_name)}/search',
            parameters={
                'keywords': keywords,
                'limit': '40',
            },
        )

    async def files(self) -> dict[str, Any]:
        """The files the user may edit.

        Returns:
            dict[str, Any]: The files, each with name, desk, whether it exists and its size.
        """
        return await self._json('GET', '/api/files')

    async def file_text(
        self, name: str, desk_name: str | None
    ) -> dict[str, Any]:
        """Reads an editable file.

        Args:
            name (str): The file's name, such as "TradingRules.md".
            desk_name (str | None): Its desk, or None for a shared file.

        Returns:
            dict[str, Any]: The name, desk and text.
        """
        parameters = {
            'name': name,
        }
        if desk_name is not None:
            parameters['desk'] = desk_name
        return await self._json(
            'GET', '/api/files/content', parameters=parameters
        )

    async def save_file(
        self,
        name: str,
        desk_name: str | None,
        text: str,
    ) -> dict[str, Any]:
        """Writes an editable file.

        Args:
            name (str): The file's name.
            desk_name (str | None): Its desk, or None for a shared file.
            text (str): The new text.

        Returns:
            dict[str, Any]: The number of characters written.
        """
        return await self._json(
            'PUT',
            '/api/files/content',
            body={
                'name': name,
                'desk': desk_name,
                'text': text,
            },
        )

    async def proposals(self) -> dict[str, Any]:
        """The changes desks propose to the user's files.

        Returns:
            dict[str, Any]: The proposals, each with its unified diff.
        """
        return await self._json('GET', '/api/proposals')

    async def decide_proposal(
        self, proposal_id: str, accept: bool
    ) -> dict[str, Any]:
        """Accepts or rejects a proposal.

        Args:
            proposal_id (str): The proposal.
            accept (bool): True to apply it, False to reject it.

        Returns:
            dict[str, Any]: The outcome.
        """
        action = 'reject'
        if accept:
            action = 'accept'
        return await self._json(
            'POST', f'/api/proposals/{self._part(proposal_id)}/{action}'
        )

    async def jobs(self, desk_name: str) -> dict[str, Any]:
        """A desk's scheduled jobs and their latest runs.

        Args:
            desk_name (str): The desk.

        Returns:
            dict[str, Any]: The jobs and recent runs.
        """
        return await self._json(
            'GET', f'/api/desks/{self._part(desk_name)}/jobs'
        )

    async def create_job(
        self, desk_name: str, job: dict[str, Any]
    ) -> dict[str, Any]:
        """Schedules a new job for a desk.

        Args:
            desk_name (str): The desk.
            job (dict[str, Any]): The job: name, schedule, run_at, instructions or command, trading_days_only and market_hours_only.

        Returns:
            dict[str, Any]: The job as stored.
        """
        return await self._json(
            'POST', f'/api/desks/{self._part(desk_name)}/jobs', body=job
        )

    async def delete_job(self, desk_name: str, job_id: str) -> dict[str, Any]:
        """Removes a scheduled job.

        Args:
            desk_name (str): The desk.
            job_id (str): The job.

        Returns:
            dict[str, Any]: The deleted job's id.
        """
        return await self._json(
            'DELETE',
            f'/api/desks/{self._part(desk_name)}/jobs/{self._part(job_id)}',
        )

    async def run_job(self, desk_name: str, job_id: str) -> dict[str, Any]:
        """Runs a scheduled job now.

        Args:
            desk_name (str): The desk.
            job_id (str): The job.

        Returns:
            dict[str, Any]: The started job's id.
        """
        return await self._json(
            'POST',
            f'/api/desks/{self._part(desk_name)}/jobs/{self._part(job_id)}/run',
        )

    async def alerts(self, desk_name: str) -> dict[str, Any]:
        """A desk's price alerts.

        Args:
            desk_name (str): The desk.

        Returns:
            dict[str, Any]: The alerts.
        """
        return await self._json(
            'GET', f'/api/desks/{self._part(desk_name)}/alerts'
        )

    async def delete_alert(
        self, desk_name: str, alert_id: str
    ) -> dict[str, Any]:
        """Removes a price alert.

        Args:
            desk_name (str): The desk.
            alert_id (str): The alert.

        Returns:
            dict[str, Any]: The deleted alert's id.
        """
        return await self._json(
            'DELETE',
            f'/api/desks/{self._part(desk_name)}/alerts/{self._part(alert_id)}',
        )

    async def skills(self, desk_name: str) -> dict[str, Any]:
        """A desk's usable and hidden skills.

        Args:
            desk_name (str): The desk.

        Returns:
            dict[str, Any]: The available and hidden skills.
        """
        return await self._json(
            'GET', f'/api/desks/{self._part(desk_name)}/skills'
        )

    async def subagents(self) -> dict[str, Any]:
        """The subagent definitions, and files that could not be read.

        Returns:
            dict[str, Any]: The subagents and the broken files.
        """
        return await self._json('GET', '/api/subagents')

    async def mcp_servers(self) -> dict[str, Any]:
        """The MCP servers and their tools.

        Returns:
            dict[str, Any]: The servers.
        """
        return await self._json('GET', '/api/mcp')

    async def packages(self) -> dict[str, Any]:
        """The installed packages.

        Returns:
            dict[str, Any]: The packages.
        """
        return await self._json('GET', '/api/packages')

    async def checkpoints(self, desk_name: str) -> dict[str, Any]:
        """A desk's checkpoints, newest first.

        Args:
            desk_name (str): The desk.

        Returns:
            dict[str, Any]: The checkpoints.
        """
        return await self._json(
            'GET', f'/api/desks/{self._part(desk_name)}/checkpoints'
        )

    async def restore_checkpoint(
        self, desk_name: str, checkpoint_id: str
    ) -> dict[str, Any]:
        """Puts a desk's own files back as they were at a checkpoint.

        Args:
            desk_name (str): The desk.
            checkpoint_id (str): The checkpoint.

        Returns:
            dict[str, Any]: The restored checkpoint and the checkpoint that undoes it.
        """
        return await self._json(
            'POST',
            f'/api/desks/{self._part(desk_name)}/checkpoints/{self._part(checkpoint_id)}/restore',
        )

    async def usage(self) -> dict[str, Any]:
        """Today's model calls, tokens and costs, and Claude's limits.

        Returns:
            dict[str, Any]: The usage per desk and backend, and the rate limits.
        """
        return await self._json('GET', '/api/usage')

    async def configuration(self) -> dict[str, Any]:
        """The configuration file's settings, with secrets masked.

        Returns:
            dict[str, Any]: The settings, by section.
        """
        return await self._json('GET', '/api/configuration')

    async def apps(self) -> list[dict[str, Any]]:
        """The packages' web apps.

        Returns:
            list[dict[str, Any]]: The apps, each with its health and unit state.
        """
        answer = await self._json('GET', '/api/apps')
        return answer['apps']

    async def app_action(
        self, package_name: str, action: str
    ) -> dict[str, Any]:
        """Starts, stops or restarts a package's app.

        Args:
            package_name (str): The package.
            action (str): "start", "stop" or "restart".

        Returns:
            dict[str, Any]: The app's new state.
        """
        return await self._json(
            'POST', f'/api/apps/{self._part(package_name)}/{action}'
        )

    async def telegram(self) -> dict[str, Any]:
        """The Telegram channel's state, pairings and paired chats.

        Returns:
            dict[str, Any]: The Telegram status.
        """
        answer = await self._json('GET', '/api/channels')
        return answer['telegram']

    async def approve_pairing(self, code: str) -> dict[str, Any]:
        """Pairs the Telegram chat that the bot gave a code.

        Args:
            code (str): The code.

        Returns:
            dict[str, Any]: The paired chat.
        """
        return await self._json(
            'POST',
            f'/api/channels/telegram/pairings/{self._part(code)}/approve',
        )

    async def revoke_pairing(self, chat_id: int) -> dict[str, Any]:
        """Unpairs a Telegram chat.

        Args:
            chat_id (int): The chat.

        Returns:
            dict[str, Any]: The outcome.
        """
        return await self._json(
            'DELETE', f'/api/channels/telegram/chats/{chat_id}'
        )

    async def _json(
        self,
        method: str,
        path: str,
        body: Any = None,
        parameters: dict[str, str] | None = None,
        files: dict[str, Any] | None = None,
    ) -> Any:
        """Sends one request and reads its JSON answer.

        Args:
            method (str): The HTTP method.
            path (str): The route, such as /api/desks.
            body (Any): A JSON body, or None.
            parameters (dict[str, str] | None): Query parameters, or None.
            files (dict[str, Any] | None): Multipart files, or None.

        Returns:
            Any: The decoded answer.

        Raises:
            GatewayError: The gateway could not be reached or answered with an error.
        """
        response = await self._send(method, path, body, parameters, files)
        return response.json()

    async def _bytes(self, path: str) -> bytes:
        """Downloads a file.

        Args:
            path (str): The route.

        Returns:
            bytes: The file's contents.

        Raises:
            GatewayError: The gateway could not be reached or answered with an error.
        """
        response = await self._send('GET', path)
        return response.content

    async def _send(
        self,
        method: str,
        path: str,
        body: Any = None,
        parameters: dict[str, str] | None = None,
        files: dict[str, Any] | None = None,
    ) -> httpx.Response:
        """Sends one request and checks its status.

        Args:
            method (str): The HTTP method.
            path (str): The route.
            body (Any): A JSON body, or None.
            parameters (dict[str, str] | None): Query parameters, or None.
            files (dict[str, Any] | None): Multipart files, or None.

        Returns:
            httpx.Response: The response, whose status is below 400.

        Raises:
            GatewayError: The gateway could not be reached or answered with an error.
        """
        try:
            response = await self._http.request(
                method,
                path,
                json=body,
                params=parameters,
                files=files,
            )
        except httpx.TransportError as error:
            raise GatewayError(
                0,
                f'The gateway at {self.base_url} does not answer ({error.__class__.__name__}). Start it with `bin/trading-agent serve` or `systemctl --user start trading-agent`.',
            ) from error
        if response.status_code >= 400:
            raise GatewayError(response.status_code, self._explain(response))
        return response

    def _explain(self, response: httpx.Response) -> str:
        """The gateway's explanation of an error.

        Args:
            response (httpx.Response): The error response.

        Returns:
            str: FastAPI's detail text when there is one, otherwise the body.
        """
        try:
            detail = response.json().get('detail')
        except ValueError:
            return response.text
        if isinstance(detail, str):
            return detail
        if isinstance(detail, list):
            messages = []
            for item in detail:
                if isinstance(item, dict):
                    messages.append(str(item.get('msg', item)))
                else:
                    messages.append(str(item))
            return '; '.join(messages)
        return response.text

    def _part(self, value: str) -> str:
        """Encodes one path segment.

        Args:
            value (str): The segment, such as a desk name.

        Returns:
            str: The segment, safe to put in a URL path.
        """
        return urllib.parse.quote(value, safe='')
