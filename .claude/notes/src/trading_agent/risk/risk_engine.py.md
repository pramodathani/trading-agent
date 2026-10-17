# risk_engine.py

The user decided on 2026-10-16 that no human approves trades, and that hard limits written in plain code would stop the agent instead. This is that code. Every order tool (milestone 10) will call `evaluate` before anything reaches UBI, and no model has a tool that can change the engine, its limits file or its ledger.

## Principles

1. **When in doubt, no.** If TradingRules.md cannot be read, nothing new can be opened; if UBI cannot report the account, no order can be checked, so none passes.
2. **Getting out is never blocked.** An order that only reduces or closes a position the desk itself opened passes every limit and every halt. It still needs an open exchange, because a closed exchange cannot fill it anyway.
3. **Every reason at once.** All failing checks are reported together, so the model can fix the order in one step instead of discovering the limits one refusal at a time.

## The user's own positions and holdings

A desk may trade an instrument the account already holds only if the risk ledger says that desk opened it. The rule was added while writing the engine, because an Indian delivery (`cnc`) sell sells holdings, so without it a desk could sell the user's long-term shares. Cash holdings are also matched by symbol, because UBI returned one of the user's nine holdings (a 2-share KWIL line) with no instrument id. On 2026-10-17, against the real account, the engine refused a delivery buy of INFY because the user holds INFY: no desk can trade any of the user's 8 held symbols. That is intended; if the user wants a desk to trade a held stock, a setting can be added later.

## Limits as the user chose them (2026-10-17)

- Percentages are of the live total balance (`summary.total_balance`, available balance plus margin in use, across all brokers), not of the morning's balance.
- The per-order cap applies to the estimated margin an order blocks, not its full value (see `margin_estimator.py`).
- `capital_percent` caps margin committed: an order's margin must fit in that share of the balance less the margin already in use.
- The weekly loss is the sum of each day's last seen profit and loss since Monday, from the ledger. A day the engine never ran is not counted, which errs toward stopping late; the market watcher of milestone 15 records the profit and loss through every trading day.
- A loss limit fires only on an actual loss (`pnl < 0`), so a limit of 0 does not halt a day that has not traded.

## Ownership

Approving an order claims the instrument for the desk. Before every decision, claims on instruments the account no longer holds are released once they are older than `ownership_grace_minutes` (30), which gives a resting order time to fill.

## Verified on 2026-10-17

28 unit tests cover every rule. Against the real account (balance 1,53,583.08, no positions, P&L 0), with a test ledger and a Monday clock: INFY and KWIL were refused as the user's holdings, and one NIFTY futures lot was refused for an estimated 2,60,394.19 of margin against a 38,395.77 cap; the kill switch did not fire.

## check_account (milestone 15)

Reads the account, records today's profit and loss in the ledger, and runs the loss-limit check, without an order. The market watcher calls it once a minute while the market is open, so the kill switch fires on a losing position even when no desk is trading. A UBI failure is logged and returns None; unreadable limits skip the check.

## Several desks (milestone 16)

- `desk_day_pnl` sums each instrument's day profit and loss for the desk that owned it today (the ledger's `day_owners`); positions no desk claimed, such as the user's own, count for no desk.
- `_check_desk_loss_limits` runs before each order and in `check_account`: a desk at its own daily loss limit is halted until tomorrow, with a `desk_halt` event, and only that desk; the account kill switch is untouched, and the halted desk can still close its positions.
- Stock ownership already gave each instrument to one desk; the new tests run it across the intraday, scalper and positional desks, with each desk's allowed products.
