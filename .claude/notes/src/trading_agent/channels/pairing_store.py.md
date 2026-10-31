# pairing_store.py

Pairing is the plan's answer to "only you can command the bot". A bot is public: anyone who guesses or finds its username can message it. Pairing ties a chat to the person who controls this machine, because approving a code needs the web page (which needs the gateway token) or a terminal on the machine.

## Choices

- **Eight characters from a 32-letter alphabet** without 0, O, 1 and I: about a trillion codes, easy to read off a phone and type, and no look-alike mistakes.
- **One hour lifetime**, as the plan asks. Expired codes are dropped whenever the file is read, so no clean-up job is needed.
- **One code per chat.** A stranger who keeps messaging gets the same code, and at most five codes wait at once, so strangers cannot flood the Channels page.
- **The file is read afresh each time**, so `trading-agent pairing approve` in a terminal takes effect in the running gateway without a restart.
- **The file is written in one step** (temporary file, then rename) so a crash mid-write cannot leave a half-written file that unpairs everyone.
- **It lives in workspace/shared**, which the traders' file tools cannot write and the bash sandbox mounts read-only, so a trader cannot pair a chat on its own.
