# set_price_alert_tool.py

Resolves the instrument through UBI (as get_quote does), reads its last price, and refuses an alert already on the wrong side of the price, because the watcher would fire it on its next cycle. Stores UBI's instrument id, so the watcher needs no search. The reply lists every active alert, which saves a separate list tool.
