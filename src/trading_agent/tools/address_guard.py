"""Refuses web requests to this machine or the local network.

Without it, web_fetch could be pointed at UBI on 127.0.0.1, at the local databases, or at a router on the home network. Every address a host name resolves to must be a public internet address. Each step of a redirect is checked again, so a public page cannot redirect the fetch to a private one.

Typical usage example:

  guard = AddressGuard()
  await guard.check('https://example.com/page')
"""

import asyncio
import ipaddress
import socket
import urllib.parse

_ALLOWED_SCHEMES = (
    'http',
    'https',
)


class AddressRefusedError(ValueError):
    """The address is not a public web address."""


class AddressGuard:
    """Checks that a URL points at the public internet."""

    async def check(self, url: str) -> None:
        """Checks one URL.

        Args:
            url (str): The URL to be fetched.

        Raises:
            AddressRefusedError: The scheme is not http or https, the host cannot be resolved, or it resolves to a private, loopback or other non-public address.
        """
        parts = urllib.parse.urlsplit(url)
        if parts.scheme not in _ALLOWED_SCHEMES:
            raise AddressRefusedError(
                f'Only http and https pages can be fetched, not {parts.scheme!r}.'
            )
        if not parts.hostname:
            raise AddressRefusedError(f'{url} has no host name.')
        loop = asyncio.get_running_loop()
        try:
            address_infos = await loop.getaddrinfo(
                parts.hostname,
                parts.port or 443,
                type=socket.SOCK_STREAM,
            )
        except socket.gaierror as error:
            raise AddressRefusedError(
                f'{parts.hostname} could not be found: {error}'
            ) from error
        for address_info in address_infos:
            address = ipaddress.ip_address(address_info[4][0])
            if not address.is_global:
                raise AddressRefusedError(
                    f'{parts.hostname} points at {address}, which is on this machine or the local network, so it cannot be fetched.'
                )
