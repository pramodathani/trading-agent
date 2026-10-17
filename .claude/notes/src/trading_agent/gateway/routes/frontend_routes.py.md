# frontend_routes.py

The gateway serves the built web page itself, so there is one process and one port (8120) for the page, the API and the live events, as with sridhara. The route matches every address and must be added last, after every API route.

The web page is a single-page application: addresses such as /chat are handled in the browser, so the server answers any address it does not know with index.html. Addresses under /api, /ws and /hooks are reserved so that a mistyped API address gets a 404 instead of a web page, which would be confusing to debug.

A requested file is resolved and must stay inside the build folder, so `/..%2Fsecret.txt` cannot read outside it. Files under `assets/` have content hashes in their names, so the browser may cache them for a year; index.html is never cached, so a new build is picked up at once.

The route needs no token, because the page holds no data. Every data request the page makes carries the token.

This follows sridhara's `FrontendRoutes`.
