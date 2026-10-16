# docker-compose.yml

The user asked on 2026-10-17 for web search to run on SearXNG in Docker on this machine. The sibling projects each use their own band of host ports (UBI 1000s, tradingmachine 2000s, instruments_explorer 3000s), so trading-agent uses the 4000s, starting with SearXNG on 4001. The port is bound to 127.0.0.1 only, so the search server is not reachable from the network.

The image is pinned to `searxng/searxng:2026.10.2-19ffbcd30`, a release two weeks old on 2026-10-17, so that an upstream change cannot alter search behaviour without a deliberate update. `SEARXNG_SECRET` comes from `TRADING_AGENT_SEARXNG_SECRET` in `.env`, which Docker Compose reads for interpolation; the compose file refuses to start without it.

Firecrawl was considered for page fetching and left out for now: on 2026-10-17 plain fetching with trafilatura read three of six Indian finance sites, the other three either needed JavaScript (MSN) or answered HTTP 403 (Moneycontrol, Zee Business). Self-hosted Firecrawl would render JavaScript but has none of the hosted service's anti-bot features, so it would not fix the 403s. The browser tool (milestone 7) will be compared on the same sites before deciding whether Firecrawl is still needed.
