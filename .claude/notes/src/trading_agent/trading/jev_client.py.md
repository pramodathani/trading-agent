# jev_client.py

The HTTP client for TypeSafe AI's Jev decision model, used by the jev_decision tool, the Jev signal watcher and the doctor.

## Why plain httpx, not TypeSafe's SDK

TypeSafe publishes `typesafe-sdk` for Python, but the API is one POST, and httpx is already a pinned dependency. Avoiding a new, very young package keeps the live gateway's dependencies unchanged, and lets the tests swap in `httpx.MockTransport` without network access.

## The API, as documented on 2026-11-01

Taken from https://docs.typesafe.ai/introduction/quickstart.md:

- `POST https://api.typesafe.ai/v1/systemone`, with `Authorization: Bearer <key>`.
- The body holds `model` (`jev-latest`), `state` (text or an object) and `questions`, a map of question ids to questions. A choice question has `type: "choice"`, `instructions` and `criteria`, an object of answer labels to descriptions.
- The answer holds `model` (the exact version, such as `jev-1.13.0`), `answers` keyed by question id with `choice`, `confidence` and `probabilities`, and `usage`.

TypeSafe's own examples read the key from `TYPESAFE_API_KEY`. This project names it `TRADING_AGENT_TYPESAFE_API_KEY` instead, like every other secret held in the `Secrets` class.

## The question

One choice question, `direction`, with the answers buy, sell and hold. The descriptions talk about the NIFTY index over the next 5 to 15 minutes, because the jev-scalper's brackets close within about 15 minutes. "sell" is described as a bearish trade rather than a short sale, since option writing is not allowed: the trader turns it into buying a put.

## Caveats

`confidence` is described by TypeSafe as how peaked the probability distribution is. It is Jev's certainty about its own choice, not a calibrated probability that the market moves, so it must not be used to size positions. TypeSafe's speed and cost claims were unverified at the time of writing.
