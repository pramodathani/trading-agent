# order_request.py

The order tools of milestone 10 build one of these from what the model asks for, after looking the instrument up, so the engine never sees a half-described order. The quantity is in units (lots times lot size for derivatives), always positive, with the side in `transaction_type`.
