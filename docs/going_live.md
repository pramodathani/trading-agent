# Going live

This is the plan for the first trading day: finish the checks that only a trading day allows, switch from dry runs to live orders, and watch the first live session. Every step says what to look at and how to stop.

trading-agent already runs as the systemd user service `trading-agent.service`, in `dry_run` mode. It starts at boot, restarts ten seconds after a crash, and resumes each desk's conversation.

## Before you start: what live means

In `dry_run` mode, UBI checks every order the desks place and sends none to a broker. In `live` mode the same orders go to the brokers with real money, and no human approves them. The risk engine's hard limits still apply to every order:

| Limit | Value | From |
|---|---|---|
| Daily loss | 15% of the account; every desk stops and the account is flattened | TradingRules.md |
| Weekly loss | 35% | TradingRules.md |
| One order's margin | at most 25% of the account | TradingRules.md |
| Option writing | forbidden | TradingRules.md |
| Each desk's products | intraday and scalper `mis`, positional `cnc` and `nrml`, main any | TradingRules.md |
| Desk loss limits | none; only the account limits apply (your choice on 17 October 2026) | TradingRules.md |
| One stock, one desk | a desk cannot trade a stock another desk holds | the risk engine |

Change any of these on the Files page or in `workspace/shared/TradingRules.md` before going live.

## 1. Before the open (by 09:00)

1. Check that everything is in place:

   ```bash
   bin/trading-agent preflight
   ```

   Expect one failure, "Dry-run order through UBI", and warnings for the stock-sharing test, Telegram and the trading mode. Anything else that fails must be fixed first; the line says how.

2. Open the web page at <http://127.0.0.1:8120>. The header must say **DRY RUN**, and the dot on the right **Live**.

3. The positional desk's 08:45 check, the intraday desk's 09:05 check and the scalper's 09:10 check run by themselves, and from 09:15 the intraday and scalper heartbeats wake them every 10 and 2 minutes. Watch them on the Activity page; each answers on the Chat page of its desk.

## 2. The trading-day checks, in dry run (09:15 to 10:00)

1. **A dry-run order through UBI.** In Chat, choose the **main** desk and send:

   > Place a dry-run limit order to buy 1 share of IDEA at the current price, product mis, then tell me what UBI answered.

   The Trading page should show the order under "Desks' open orders", and main as the owner of IDEA.

2. **Two desks cannot share a stock.** Choose the **intraday** desk and send:

   > Try to buy 1 share of IDEA, product mis, as a dry run, and tell me exactly what the risk engine said.

   The risk engine must refuse it with "IDEA belongs to the main desk; one desk trades an instrument at a time." The Activity page shows the refusal.

3. **A fill report.** Dry runs reach no broker, so they never fill; the first real fill report is seen in the live session. Ask main to flatten itself afterwards:

   > Flatten your desk: cancel your open orders and close your positions.

4. Run the check again:

   ```bash
   bin/trading-agent preflight
   ```

   It should now end with "Ready to go live", with warnings only for Telegram (if you have not paired a phone) and the trading mode.

## 3. Switch to live

1. In `trading_agent.toml`, change the first line to:

   ```toml
   mode = "live"
   ```

2. Restart the service:

   ```bash
   systemctl --user restart trading-agent
   ```

3. Reload the web page. The header must now say **LIVE ORDERS** in red.

A desk that is in the middle of a turn when the service restarts loses that turn; its conversation and everything it had saved are kept.

## 4. Watch the first live session

Keep these pages open:

| Page | What to watch |
|---|---|
| Desks | Each desk's state and today's profit or loss |
| Activity | Every order, risk decision and fill as it happens |
| Trading | Positions, which desk owns each, open orders, halts |
| Models | Claude's five-hour limit, if the desks talk a lot |

Things that should happen, and what they mean:

- A desk's **order** event, followed by a **fill** a few seconds later: the broker filled the order, and the desk is told.
- A **risk engine refused** line: a limit stopped an order. That is the risk engine working, not an error.
- A **model switch** from claude to qwen: Claude hit a limit or failed, and the desk carried on with the next model.

## How to stop

From gentlest to strongest:

| You want to | Do this | What happens to open positions |
|---|---|---|
| Stop one turn | Stop button in Chat, or `/stop` | Nothing; the desk just stops thinking |
| Stop one desk thinking | Pause on the Desks page, or `/pause intraday` | Nothing; its orders and stops at UBI stay |
| Stop every desk thinking | `/pause all` on Telegram, or Pause on each desk card | Nothing |
| Close one desk's trades | Flatten on the desk's card | That desk's orders are cancelled and positions closed |
| Stop everything | The kill switch on the Trading page (type FLATTEN), or `/kill CONFIRM <reason>` on Telegram | Every desk halts until tomorrow and UBI flattens the whole account |
| Stop trading-agent itself | `systemctl --user stop trading-agent` | Nothing is closed: orders and bracket stops already at UBI stay in place |

To go back to dry runs at any time, set `mode = "dry_run"` and run `systemctl --user restart trading-agent`.

## After the close

At 15:45 each desk rolls over: it summarises the day, starts a fresh session for tomorrow, and folds its notes into Memory.md. Read the summaries on the Sessions page, and accept or reject any proposals the desks made on the Files page.

## Useful commands

```bash
systemctl --user status trading-agent      # is it running?
journalctl --user -u trading-agent -f      # its log, live
systemctl --user restart trading-agent     # after changing trading_agent.toml
bin/trading-agent preflight                # everything, plus the going-live checks
```
