# margin_estimator.py

The user chose on 2026-10-17 that "largest single order: 25% of balance" means the margin an order blocks, not its full value, so that futures are not ruled out by their notional size. UBI has no margin route; its broker selector estimates margin with the rules in `unified_broker_interface/docs/architecture/broker-selection.md`, which came within a few rupees of the brokers' calculators for delivery, intraday and option buys on 2026-09-30. This class follows those rules:

| Order | Estimate |
|---|---|
| Delivery buy | quantity × price |
| Intraday (mis) cash | quantity × price × 20% |
| Future, bought or sold | quantity × price × the segment's rate |
| Option bought | quantity × premium |
| Option sold | quantity × price × the futures rate (UBI uses the underlying's price; the option's own price is a stand-in until the order tools supply the underlying) |

The rates are UBI's deliberately high segment-wide ones: index derivatives 15%, stock derivatives 40%, commodities 47%. Currency is not in UBI's table; 10% is a cautious guess, well above real currency margins. They are configurable under `[risk.margin_rates]`. Because the index rate is high, one NIFTY futures lot was estimated at 2,60,394 on 2026-10-17 against UBI's measured 1,67,120 for a lot; erring high only refuses orders that might have passed.
