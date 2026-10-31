# The web page (frontend/)

React 19, TypeScript and Vite 8, laid out like sridhara's frontend, with the same package versions. Fonts are Roboto and Roboto Mono, and the colours are the user's diagram palette (dark by default, Material deep orange accent), so the page and the diagrams look like one product.

| Task | Command |
|---|---|
| Build, which the gateway then serves at http://127.0.0.1:8120 | `source ~/.nvm/nvm.sh && cd frontend && npm run build` |
| Type check only | `npm run typecheck` |
| Development server with hot reload on port 5175, proxying /api and /ws to the gateway | `npm run dev` |

## How it is organised

Logic lives in classes, one instance each: `ApiClient` (every API call), `TokenStore` (the access token), `EventSocket` (the one live connection), `EventDescriber` (an event in words), `ChatTurnBuilder` (events grouped into chat turns), `EventMerger` (journal and live events without duplicates), `Formatter` (money and India times), `ThemeController` and `SelectedTraderStore`. React components are function components that read these through small hooks.

## Pages

| Section | Pages |
|---|---|
| Trade | Traders (the home page), Chat, Activity, Trading |
| Memory | Sessions, Files, Checkpoints |
| Automation | Schedule, Skills, Extensions |
| System | Models, Settings |

Trader-specific pages follow the trader chosen in the header. The plan's Terminal and Browser, Channels and Apps pages belong to later milestones (Telegram in 19, apps in 20). Logs are covered by the Activity page for now.

## Things that are easy to get wrong

- Times are always shown in India time, whatever the browser's time zone, because the market's hours are India hours.
- The trader switcher in the header chooses the trader for trader-specific pages. It is remembered in the browser.
- Browser checks during development use a throwaway token passed in `TRADING_AGENT_GATEWAY_ACCESS_TOKEN` when starting the gateway (environment variables take precedence over .env), so the real token is never typed into a page by an automated check.
