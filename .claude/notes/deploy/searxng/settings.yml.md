# deploy/searxng/settings.yml

`use_default_settings: true` keeps SearXNG's own defaults and changes only what follows. The JSON format is switched on because the agent's web_search tool asks for JSON; SearXNG serves HTML only by default. The limiter is off because it is meant for public instances and needs a separate Valkey server; this instance is reachable from this machine only. Safe search is off so that financial news is never filtered.
