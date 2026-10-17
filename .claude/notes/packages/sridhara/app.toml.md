# packages/sridhara/app.toml

The plan's proof that packages can be apps: sridhara is added to the sidebar without changing sridhara. It points at sridhara's page on port 8095 and its existing `sridhara.service`, and names sridhara's own unit file (`services/sridhara.service` in its repository) for machines where the service is not set up yet.

The health check uses the page, not sridhara's /api/health, because that route needs sridhara's login and answers 401. On 2026-10-17 the page showed sridhara's login inside trading-agent, with the unit reported active and running.
