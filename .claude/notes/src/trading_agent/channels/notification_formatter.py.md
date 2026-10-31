# notification_formatter.py

The plan lists what Telegram pushes: fills, rejections, model switches, cron results and end-of-day summaries. Price alerts, halts, the traders' send_message messages and failed turns were added because each is something the user wants on the phone. The user narrows the list in `[telegram] notifications`.

Every message starts with the trader's name, because one chat hears from all traders.

## Trader reports

When a trader wakes on its own (a scheduled check, a heartbeat, a price alert, a webhook) and says something, that answer is pushed; nobody would otherwise see it until they opened the web page. Three kinds of answer are not pushed:

- answers to the user's own messages, which go only to the chat that asked;
- silent heartbeats (NOTHING_TO_DO);
- commands run by jobs, such as the daily /rollover, whose "Rolled over" line is noise; the day's summary is pushed separately as a daily summary.

## Fills

The market watcher's fill event did not name the stock, so milestone 19 added the symbol, side and quantity to it. A fill reads like "intraday: COMPLETE buy 10 INFY, 10 filled at 1501.2".

A message with `attachments` begins "Picture from <trader>:" instead of "Message from", and the text is stripped so a picture with no caption does not end in a blank line. "URGENT from" still wins.
