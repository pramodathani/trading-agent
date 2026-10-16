"""Tests for the browser session, run in the real Chrome against a small local web server."""

import asyncio
import http.server
import shutil
import threading
from pathlib import Path

import pytest

from trading_agent.configuration import agent_configuration
from trading_agent.tools import address_guard
from trading_agent.tools import browser_session

pytestmark = pytest.mark.skipif(
    shutil.which('google-chrome') is None,
    reason='Google Chrome is not installed',
)

_PAGES = {
    '/start': '<html><head><title>Start</title></head><body><p>Market notes for testing.</p><a href="/second">Go to second</a><button style="display:none">Hidden button</button></body></html>',
    '/second': '<html><head><title>Second</title></head><body><p>Second page.</p></body></html>',
    '/form': '<html><head><title>Search</title></head><body><form action="/result"><input name="q" placeholder="Search symbol"></form></body></html>',
    '/result': '<html><head><title>Result</title></head><body><p id="out"></p><script>document.getElementById("out").innerText = "searched " + new URLSearchParams(location.search).get("q");</script></body></html>',
    '/sneaky': '<html><head><title>Sneaky</title></head><body><p id="out">waiting</p><script>fetch("http://127.0.0.1:PORT/start").then(() => { document.getElementById("out").innerText = "reached"; }).catch(() => { document.getElementById("out").innerText = "blocked"; });</script></body></html>',
}


class _PageHandler(http.server.BaseHTTPRequestHandler):
    """Serves the test pages."""

    def do_GET(self) -> None:
        """Answers one GET request with a test page, or 404."""
        page = _PAGES.get(self.path.split('?')[0])
        if page is None:
            self.send_response(404)
            self.end_headers()
            return
        body = page.replace('PORT', str(self.server.server_port)).encode(
            'utf-8'
        )
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *arguments: object) -> None:
        """Keeps the test output quiet.

        Args:
            format (str): The log format, unused.
            *arguments (object): The log values, unused.
        """
        del format, arguments


class _OnlyLocalhostGuard(address_guard.AddressGuard):
    """Allows the host name "localhost" and refuses every other address, including 127.0.0.1."""

    async def check(self, url: str) -> None:
        """Allows only localhost.

        Args:
            url (str): The URL.

        Raises:
            address_guard.AddressRefusedError: The host is not "localhost", or the scheme is not http.
        """
        if not url.startswith('http://localhost:'):
            raise address_guard.AddressRefusedError(
                f'{url} is not allowed in this test.'
            )


@pytest.fixture(name='server_port', scope='module')
def _server_port():
    """Runs the test web server for the whole module.

    Yields:
        int: The server's port on localhost.
    """
    server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), _PageHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server.server_port
    server.shutdown()


def _run(tmp_path: Path, scenario) -> object:
    """Runs a scenario with a fresh browser session and closes the browser afterwards.

    Args:
        tmp_path (Path): A temporary folder from pytest.
        scenario (Callable): An async function taking the session.

    Returns:
        object: What the scenario returned.
    """
    session = browser_session.BrowserSession(
        tmp_path / 'profile',
        tmp_path / 'screenshots',
        _OnlyLocalhostGuard(),
        agent_configuration.BrowserConfiguration(),
    )

    async def wrapped() -> object:
        """Runs the scenario, then closes the browser.

        Returns:
            object: What the scenario returned.
        """
        try:
            return await scenario(session)
        finally:
            await session.close()

    return asyncio.run(wrapped())


class TestBrowserSession:
    """Tests for opening, clicking, typing and guarding."""

    def test_snapshot_numbers_visible_elements_only(
        self,
        tmp_path: Path,
        server_port: int,
    ) -> None:
        """The visible link gets a number and the hidden button does not.

        Args:
            tmp_path (Path): A temporary folder from pytest.
            server_port (int): The test server's port.
        """

        async def scenario(session: browser_session.BrowserSession) -> str:
            """Opens the start page.

            Args:
                session (browser_session.BrowserSession): The browser.

            Returns:
                str: The snapshot.
            """
            return await session.open(f'http://localhost:{server_port}/start')

        snapshot = _run(tmp_path, scenario)

        assert 'Title: Start' in snapshot
        assert (
            f'[1] a "Go to second" → http://localhost:{server_port}/second'
            in snapshot
        )
        assert 'Hidden button' not in snapshot
        assert 'Market notes for testing.' in snapshot

    def test_click_follows_a_link(
        self, tmp_path: Path, server_port: int
    ) -> None:
        """Clicking a numbered link opens its page.

        Args:
            tmp_path (Path): A temporary folder from pytest.
            server_port (int): The test server's port.
        """

        async def scenario(session: browser_session.BrowserSession) -> str:
            """Opens the start page and clicks the link.

            Args:
                session (browser_session.BrowserSession): The browser.

            Returns:
                str: The snapshot after the click.
            """
            await session.open(f'http://localhost:{server_port}/start')
            return await session.click(1)

        assert 'Title: Second' in _run(tmp_path, scenario)

    def test_typing_and_submitting_a_form(
        self, tmp_path: Path, server_port: int
    ) -> None:
        """Typing into a field and pressing Enter submits the form.

        Args:
            tmp_path (Path): A temporary folder from pytest.
            server_port (int): The test server's port.
        """

        async def scenario(session: browser_session.BrowserSession) -> str:
            """Opens the form and searches.

            Args:
                session (browser_session.BrowserSession): The browser.

            Returns:
                str: The snapshot of the result page.
            """
            await session.open(f'http://localhost:{server_port}/form')
            return await session.type_text(1, 'RELIANCE', submit=True)

        assert 'searched RELIANCE' in _run(tmp_path, scenario)

    def test_screenshot_is_a_saved_png(
        self, tmp_path: Path, server_port: int
    ) -> None:
        """A screenshot comes back as PNG bytes and is saved in the screenshot folder.

        Args:
            tmp_path (Path): A temporary folder from pytest.
            server_port (int): The test server's port.
        """

        async def scenario(session: browser_session.BrowserSession) -> tuple:
            """Opens a page and takes a screenshot.

            Args:
                session (browser_session.BrowserSession): The browser.

            Returns:
                tuple: The picture and its path.
            """
            await session.open(f'http://localhost:{server_port}/start')
            return await session.screenshot()

        picture, path = _run(tmp_path, scenario)

        assert picture.startswith(b'\x89PNG')
        assert path.parent == tmp_path / 'screenshots'
        assert path.read_bytes() == picture

    def test_page_cannot_fetch_a_refused_address(
        self,
        tmp_path: Path,
        server_port: int,
    ) -> None:
        """A page's own script that fetches a refused address is blocked inside the browser.

        Args:
            tmp_path (Path): A temporary folder from pytest.
            server_port (int): The test server's port.
        """

        async def scenario(session: browser_session.BrowserSession) -> str:
            """Opens the page whose script fetches 127.0.0.1.

            Args:
                session (browser_session.BrowserSession): The browser.

            Returns:
                str: The snapshot after the script ran.
            """
            await session.open(f'http://localhost:{server_port}/sneaky')
            await asyncio.sleep(1)
            return await session.snapshot()

        snapshot = _run(tmp_path, scenario)

        assert 'blocked' in snapshot
        assert 'reached' not in snapshot

    def test_refused_and_file_addresses_cannot_be_opened(
        self, tmp_path: Path
    ) -> None:
        """Opening a refused address or a local file raises before Chrome loads anything.

        Args:
            tmp_path (Path): A temporary folder from pytest.
        """

        async def scenario(
            session: browser_session.BrowserSession,
        ) -> list[str]:
            """Tries both addresses.

            Args:
                session (browser_session.BrowserSession): The browser.

            Returns:
                list[str]: The refusal messages.
            """
            messages = []
            for address in [
                'http://127.0.0.1:8080/api/portfolio/funds',
                'file:///etc/passwd',
            ]:
                try:
                    await session.open(address)
                except address_guard.AddressRefusedError as error:
                    messages.append(str(error))
            return messages

        assert len(_run(tmp_path, scenario)) == 2

    def test_snapshot_before_opening_explains_what_to_do(
        self, tmp_path: Path
    ) -> None:
        """A snapshot with no page open says to use browser_open first.

        Args:
            tmp_path (Path): A temporary folder from pytest.
        """

        async def scenario(session: browser_session.BrowserSession) -> str:
            """Asks for a snapshot straight away.

            Args:
                session (browser_session.BrowserSession): The browser.

            Returns:
                str: The error message.
            """
            try:
                await session.snapshot()
            except browser_session.BrowserError as error:
                return str(error)
            return ''

        assert 'browser_open first' in _run(tmp_path, scenario)
