# loop_guard.py

Small local models sometimes repeat the same tool call in a loop. For a trading agent the worst case is the same order sent again and again, so the guard refuses a call once the same tool with the same arguments has run more than `maximum_identical_tool_calls` times (3 by default) in one turn. The refusal goes back to the model as an error result it can read, rather than ending the turn, so the model can recover.

Arguments are compared through `json.dumps(..., sort_keys=True)` so that the same arguments in a different order count as the same call. This is the loop guard Hermes calls "tool loop guardrails".
