"""One desk's Chrome browser, driven by Playwright.

Chrome runs headless with a profile of its own inside the desk's folder, so it never sees the user's logins, cookies or history. It identifies itself as ordinary Chrome rather than HeadlessChrome and hides the automation flag, because Indian finance sites such as Moneycontrol and Zee Business refuse headless browsers with HTTP 403.

Every request the browser makes, including images, scripts and redirects, passes the address guard, so no page can make it fetch anything from this machine or the local network, and file:// pages cannot be opened. Downloads are refused.

A snapshot gives every visible clickable element a number, so a model that cannot see pictures can still say "click 3" or "type into 7".

Typical usage example:

  session = BrowserSession(profile_directory, screenshot_directory, guard, browser_configuration)
  snapshot = await session.open('https://www.nseindia.com/')
  await session.close()
"""

import asyncio
import contextlib
import datetime
import logging
import urllib.parse
from pathlib import Path
from typing import Any

import playwright.async_api

from trading_agent.configuration import agent_configuration
from trading_agent.tools import address_guard as address_guard_module

_LOGGER = logging.getLogger(__name__)
_USER_AGENT = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/153.0.0.0 Safari/537.36'
_REFERENCE_ATTRIBUTE = 'data-trading-agent-ref'
_PAGE_SETTLE_MILLISECONDS = 1500
_ACTION_TIMEOUT_MILLISECONDS = 10000
_ALWAYS_ALLOWED_SCHEMES = (
    'data',
    'blob',
    'about',
)
_SNAPSHOT_SCRIPT = """
(maximumElements) => {
  const attribute = 'data-trading-agent-ref';
  const selector = 'a[href], button, input, select, textarea, summary, [role=button], [role=link], [role=tab], [role=menuitem], [role=checkbox], [role=option], [onclick]';
  for (const old of document.querySelectorAll('[' + attribute + ']')) {
    old.removeAttribute(attribute);
  }
  const elements = [];
  let reference = 0;
  for (const element of document.querySelectorAll(selector)) {
    const box = element.getBoundingClientRect();
    const style = getComputedStyle(element);
    if (box.width === 0 || box.height === 0 || style.visibility === 'hidden' || style.display === 'none') {
      continue;
    }
    reference += 1;
    element.setAttribute(attribute, String(reference));
    const label = (element.getAttribute('aria-label') || element.innerText || element.value || element.getAttribute('placeholder') || element.getAttribute('title') || element.getAttribute('name') || '').trim().replace(/\\s+/g, ' ').slice(0, 80);
    elements.push({
      reference: reference,
      tag: element.tagName.toLowerCase(),
      role: element.getAttribute('role') || '',
      type: element.getAttribute('type') || '',
      label: label,
      address: element.href || '',
    });
    if (elements.length >= maximumElements) {
      break;
    }
  }
  const text = document.body ? document.body.innerText : '';
  return {
    title: document.title,
    address: location.href,
    text: text.replace(/\\n{3,}/g, '\\n\\n'),
    elements: elements,
  };
}
"""


class BrowserError(Exception):
    """The browser could not do what was asked, for a reason the model can act on."""


class BrowserSession:
    """A desk's browser, started on first use."""

    def __init__(
        self,
        profile_directory: Path,
        screenshot_directory: Path,
        guard: address_guard_module.AddressGuard,
        browser_configuration: agent_configuration.BrowserConfiguration,
    ):
        """Creates the session without starting Chrome.

        Args:
            profile_directory (Path): The desk's own Chrome profile folder.
            screenshot_directory (Path): Where screenshots are saved.
            guard (address_guard_module.AddressGuard): The check every request must pass.
            browser_configuration (agent_configuration.BrowserConfiguration): Timeouts and limits.
        """
        self._profile_directory = profile_directory
        self._screenshot_directory = screenshot_directory
        self._guard = guard
        self._settings = browser_configuration
        self._playwright = None
        self._context = None
        self._current_page = None
        self._host_verdicts = {}
        self._lock = asyncio.Lock()

    async def open(self, address: str) -> str:
        """Opens a page in the current tab and returns its snapshot.

        Args:
            address (str): The page's address.

        Returns:
            str: The page's snapshot.

        Raises:
            BrowserError: The address is refused, or the page could not be opened.
            address_guard_module.AddressRefusedError: The address is not on the public internet.
        """
        async with self._lock:
            await self._guard.check(address)
            page = await self._page()
            try:
                response = await page.goto(
                    address,
                    wait_until='domcontentloaded',
                    timeout=self._settings.navigation_timeout_seconds * 1000,
                )
            except playwright.async_api.Error as error:
                raise BrowserError(
                    f'Could not open {address}: {error.message.splitlines()[0]}'
                ) from error
            await page.wait_for_timeout(_PAGE_SETTLE_MILLISECONDS)
            status = response.status if response is not None else 'unknown'
            return f'HTTP status {status}\n' + await self._snapshot_text(page)

    async def snapshot(self) -> str:
        """Lists the current page's clickable elements and text.

        Returns:
            str: The snapshot.

        Raises:
            BrowserError: No page is open yet.
        """
        async with self._lock:
            return await self._snapshot_text(await self._open_page())

    async def click(self, reference: int) -> str:
        """Clicks a numbered element from the last snapshot.

        Args:
            reference (int): The element's number.

        Returns:
            str: The snapshot after the click.

        Raises:
            BrowserError: No element has that number, or the click failed.
        """
        async with self._lock:
            page = await self._open_page()
            element = page.locator(f'[{_REFERENCE_ATTRIBUTE}="{reference}"]')
            try:
                await element.click(timeout=_ACTION_TIMEOUT_MILLISECONDS)
            except playwright.async_api.Error as error:
                raise BrowserError(
                    f'Could not click element {reference}: {error.message.splitlines()[0]}. Take a new snapshot; the numbers change when the page changes.'
                ) from error
            await self._settle(page)
            return await self._snapshot_text(page)

    async def type_text(self, reference: int, text: str, submit: bool) -> str:
        """Types into a numbered field, replacing what is in it.

        Args:
            reference (int): The field's number from the last snapshot.
            text (str): What to type.
            submit (bool): Whether to press Enter afterwards.

        Returns:
            str: The snapshot after typing.

        Raises:
            BrowserError: No field has that number, or typing failed.
        """
        async with self._lock:
            page = await self._open_page()
            field = page.locator(f'[{_REFERENCE_ATTRIBUTE}="{reference}"]')
            try:
                await field.fill(text, timeout=_ACTION_TIMEOUT_MILLISECONDS)
                if submit:
                    await field.press(
                        'Enter', timeout=_ACTION_TIMEOUT_MILLISECONDS
                    )
            except playwright.async_api.Error as error:
                raise BrowserError(
                    f'Could not type into element {reference}: {error.message.splitlines()[0]}. Take a new snapshot and pick a text field.'
                ) from error
            await self._settle(page)
            return await self._snapshot_text(page)

    async def screenshot(self) -> tuple[bytes, Path]:
        """Takes a screenshot of the visible part of the current page.

        Returns:
            tuple[bytes, Path]: The PNG picture and where it was saved.

        Raises:
            BrowserError: No page is open yet.
        """
        async with self._lock:
            page = await self._open_page()
            self._screenshot_directory.mkdir(parents=True, exist_ok=True)
            now = datetime.datetime.now(datetime.UTC)
            path = self._screenshot_directory / f'{now:%Y%m%d-%H%M%S-%f}.png'
            picture = await page.screenshot(path=str(path), type='png')
            return picture, path

    async def back(self) -> str:
        """Goes back one page in the current tab.

        Returns:
            str: The snapshot of the previous page.

        Raises:
            BrowserError: There is no earlier page.
        """
        async with self._lock:
            page = await self._open_page()
            response = await page.go_back(
                wait_until='domcontentloaded',
                timeout=self._settings.navigation_timeout_seconds * 1000,
            )
            if response is None:
                raise BrowserError('There is no earlier page in this tab.')
            await page.wait_for_timeout(_PAGE_SETTLE_MILLISECONDS)
            return await self._snapshot_text(page)

    async def tabs(self, action: str, index: int | None) -> str:
        """Lists, switches to, or closes tabs.

        Args:
            action (str): "list", "switch" or "close".
            index (int | None): The tab's number from the list, for "switch" and "close".

        Returns:
            str: The list of tabs after the action, with the current one marked.

        Raises:
            BrowserError: The tab number does not exist, or no number was given.
        """
        async with self._lock:
            await self._page()
            pages = self._context.pages
            if action != 'list':
                if index is None or not 1 <= index <= len(pages):
                    raise BrowserError(
                        f'Give a tab number from 1 to {len(pages)}.'
                    )
                chosen = pages[index - 1]
                if action == 'switch':
                    self._current_page = chosen
                    await chosen.bring_to_front()
                if action == 'close':
                    await chosen.close()
                    if chosen is self._current_page:
                        self._current_page = None
            lines = []
            for number, page in enumerate(self._context.pages, start=1):
                marker = ' (current)' if page is self._current_page else ''
                lines.append(
                    f'{number}. {await page.title() or "(untitled)"} · {page.url}{marker}'
                )
            return '\n'.join(lines) or 'No tabs are open.'

    async def close(self) -> None:
        """Closes Chrome and stops Playwright."""
        if self._context is not None:
            try:
                await self._context.close()
            except playwright.async_api.Error:
                _LOGGER.warning('Chrome did not close cleanly')
        if self._playwright is not None:
            await self._playwright.stop()
        self._context = None
        self._playwright = None
        self._current_page = None

    async def _page(self) -> playwright.async_api.Page:
        """The current tab, starting Chrome on first use.

        Returns:
            playwright.async_api.Page: The current tab.
        """
        if self._context is None:
            self._profile_directory.mkdir(parents=True, exist_ok=True)
            self._playwright = (
                await playwright.async_api.async_playwright().start()
            )
            self._context = (
                await self._playwright.chromium.launch_persistent_context(
                    str(self._profile_directory),
                    channel='chrome',
                    headless=self._settings.headless,
                    user_agent=_USER_AGENT,
                    args=[
                        '--disable-blink-features=AutomationControlled',
                    ],
                    locale='en-IN',
                    timezone_id='Asia/Kolkata',
                    viewport={
                        'width': 1366,
                        'height': 900,
                    },
                    accept_downloads=False,
                )
            )
            await self._context.route('**/*', self._guard_request)
        if self._current_page is None or self._current_page.is_closed():
            if self._context.pages:
                self._current_page = self._context.pages[-1]
            else:
                self._current_page = await self._context.new_page()
        return self._current_page

    async def _open_page(self) -> playwright.async_api.Page:
        """The current tab, which must already show a page.

        Returns:
            playwright.async_api.Page: The current tab.

        Raises:
            BrowserError: Nothing has been opened yet.
        """
        page = await self._page()
        if page.url in ('', 'about:blank'):
            raise BrowserError('No page is open yet; use browser_open first.')
        return page

    async def _guard_request(
        self,
        route: playwright.async_api.Route,
        request: playwright.async_api.Request,
    ) -> None:
        """Lets a request through only when its address is on the public internet.

        Args:
            route (playwright.async_api.Route): Playwright's handle on the request.
            request (playwright.async_api.Request): The request.
        """
        parts = urllib.parse.urlsplit(request.url)
        if parts.scheme in _ALWAYS_ALLOWED_SCHEMES:
            await route.continue_()
            return
        if parts.scheme not in ('http', 'https') or not parts.hostname:
            await route.abort('blockedbyclient')
            return
        verdict = self._host_verdicts.get(parts.hostname)
        if verdict is None:
            try:
                await self._guard.check(request.url)
                verdict = True
            except address_guard_module.AddressRefusedError:
                verdict = False
            self._host_verdicts[parts.hostname] = verdict
        if verdict:
            await route.continue_()
        else:
            await route.abort('blockedbyclient')

    async def _settle(self, page: playwright.async_api.Page) -> None:
        """Waits briefly for a page to react to a click or a submitted form.

        Args:
            page (playwright.async_api.Page): The tab.
        """
        with contextlib.suppress(playwright.async_api.Error):
            await page.wait_for_load_state(
                'domcontentloaded',
                timeout=self._settings.navigation_timeout_seconds * 1000,
            )
        await page.wait_for_timeout(_PAGE_SETTLE_MILLISECONDS)

    async def _snapshot_text(self, page: playwright.async_api.Page) -> str:
        """Numbers the page's clickable elements and formats them with its text.

        Args:
            page (playwright.async_api.Page): The tab.

        Returns:
            str: The title, address, numbered elements and visible text, under a data label.
        """
        snapshot: dict[str, Any] = await page.evaluate(
            _SNAPSHOT_SCRIPT,
            self._settings.maximum_elements,
        )
        lines = [
            f'Title: {snapshot["title"] or "(untitled)"}',
            f'Address: {snapshot["address"]}',
            '',
            'Clickable elements (use their numbers with browser_click and browser_type):',
        ]
        for element in snapshot['elements']:
            kind = element['role'] or element['tag']
            if element['type']:
                kind = f'{kind}:{element["type"]}'
            line = f'[{element["reference"]}] {kind} "{element["label"]}"'
            if element['address'] and element['tag'] == 'a':
                line += f' → {element["address"][:120]}'
            lines.append(line)
        if not snapshot['elements']:
            lines.append('(none found)')
        text = snapshot['text'].strip()
        maximum = self._settings.maximum_text_characters
        lines.append('')
        lines.append('Visible text:')
        lines.append(text[:maximum] or '(no visible text)')
        if len(text) > maximum:
            lines.append(f'[text cut: {len(text) - maximum} more characters]')
        return '\n'.join(lines)
