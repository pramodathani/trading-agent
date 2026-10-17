# dry_run_order_check.py

This is the plan's "test with dry_run on every backend" made into a gate: going live needs at least one order the risk engine approved and UBI accepted. Only `placed` counts; a flatten with nothing to close never reaches UBI's order path. UBI refuses even dry-run orders when its instrument list is not loaded, as at weekends, so this check can only pass on a trading day.
