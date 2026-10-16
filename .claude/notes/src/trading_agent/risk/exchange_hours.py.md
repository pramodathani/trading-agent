# exchange_hours.py

The user chose each exchange's own opening and closing times. Regular sessions: NSE and BSE equities and derivatives 09:15 to 15:30, currency derivatives 09:00 to 17:00, MCX 09:00 to 23:30 while the United States is on daylight saving time and 23:55 otherwise, decided with `America/New_York`'s `dst()`. Pre-open and closing sessions are not included. Weekends are closed; exchange holidays are not known until the market calendar of milestone 15, so on a holiday the engine would allow an order the exchange then rejects.
