# address_guard.py

The gateway, UBI, the databases and SearXNG all listen on this machine, and UBI's REST API is on 127.0.0.1:8080. A fetch tool that followed any address could be talked, by a page or a prompt, into requesting those. The guard resolves the host name and refuses any address that is not globally routable (`ipaddress.is_global`), which covers loopback, private ranges, link-local and reserved space, and refuses every scheme except http and https. `web_fetch` follows redirects itself and checks each step, so a public page cannot redirect it to a private address; a test proves the second request is never sent.

The check and the connection are separate lookups, so a host that changes its DNS answer between them could slip through. That is accepted for now; the local services it could reach still require credentials.
