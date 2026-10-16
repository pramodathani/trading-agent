# order_arguments.py

The price checks copy UBI's own coupling of price fields to order type, so a model that forgets a price is told at once by pydantic, in a sentence, before any UBI call. `reason` is required on every order tool, because the plan's journal keeps the model's stated reason for each action.
