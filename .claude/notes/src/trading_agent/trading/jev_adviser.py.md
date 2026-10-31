# jev_adviser.py

Joins the state reader and the client, so the tool and the watcher do exactly the same thing: read NIFTY's state, ask Jev, and return the decision together with the state.

UBI failures and Jev failures both become `JevAdviserError`, because both callers react the same way: the tool tells the trader to treat the moment as hold, and the watcher wakes nobody. A state without a quote is refused before Jev is asked, so Jev never judges an empty market.

`JevAdvice.describe` writes the sentence both the tool result and the watcher's wake-up message use, with the exact Jev version, so a trader's notes record which model made each call.
