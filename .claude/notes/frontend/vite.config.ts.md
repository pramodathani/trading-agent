# vite.config.ts

The development server runs on port 5175, next to sridhara's 5174, and proxies /api and /ws to the gateway on 8120, so `npm run dev` gives hot reload against the real gateway. The WebSocket needs its own proxy entry with `ws: true`.
