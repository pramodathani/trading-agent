# tokenStore.ts

The gateway's API needs the access token on every request. The page asks for it once and keeps it in the browser's localStorage, which is acceptable because the gateway listens on 127.0.0.1 only and the browser is the user's own. A 401 from the API, or the WebSocket closing with code 1008 (policy violation), clears the token so the token page appears again instead of a page full of errors.

Every localStorage call is wrapped in try and catch, because a private window or blocked site data can make it throw. The token still works for the session in that case; it is just not remembered.
