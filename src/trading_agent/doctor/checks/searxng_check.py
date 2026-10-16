"""Checks that the local SearXNG search server answers JSON searches.

Typical usage example:

  result = SearxngCheck('http://127.0.0.1:4001').run()
"""

import httpx

from trading_agent.doctor import doctor_check

_TIMEOUT_SECONDS = 15.0


class SearxngCheck(doctor_check.DoctorCheck):
    """Checks the web search server."""

    name = 'Web search (SearXNG)'

    def __init__(self, base_url: str):
        """Creates the check.

        Args:
            base_url (str): The SearXNG server's address.
        """
        self._base_url = base_url.rstrip('/')

    def run(self) -> doctor_check.CheckResult:
        """Runs one small search and counts the results.

        Returns:
            doctor_check.CheckResult: OK when results come back, failed when the server is down or JSON answers are switched off.
        """
        try:
            response = httpx.get(
                f'{self._base_url}/search',
                params={
                    'q': 'NSE India',
                    'format': 'json',
                },
                timeout=_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
        except httpx.HTTPError as error:
            return doctor_check.CheckResult(
                doctor_check.CheckStatus.FAILED,
                f'SearXNG at {self._base_url} did not answer ({error!r}); start it with: docker compose up -d',
            )
        result_count = len(response.json().get('results', []))
        if result_count == 0:
            return doctor_check.CheckResult(
                doctor_check.CheckStatus.WARNING,
                f'SearXNG at {self._base_url} answered, but with no results.',
            )
        return doctor_check.CheckResult(
            doctor_check.CheckStatus.OK,
            f'SearXNG at {self._base_url} returned {result_count} results.',
        )
