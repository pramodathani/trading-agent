# injection_scanner.py

Prompt-injection defence (block 30), first layer: recognise the common shapes of text aimed at the model.

## Rules

Eight patterns, each reported at most once with its line and an excerpt: asks to ignore instructions; announces new instructions; tries to give the model a new role; asks for the system prompt; contains chat-format markers (`<|im_start|>`, `[INST]`, `<<SYS>>`); asks to hide something from the user; asks to send secrets somewhere; asks to get around the risk controls. The last is specific to trading-agent: an attack on a trading agent is most likely to target the risk engine or the loss limits.

Plus invisible characters: zero-width characters, text-direction controls and Unicode tag characters (U+E0000 to U+E007F), which can carry whole hidden sentences. `remove_hidden_characters` strips them before the model reads outside text.

## False positives

The patterns need an instruction-like phrase, not single words: a news paragraph saying "investors ignored weak guidance" and "the rules on buybacks" raises nothing (there is a test for it). A finding never blocks anything; it only adds a warning.

## Limits

Pattern matching cannot catch every phrasing. The main defence is the label every piece of outside text carries (`untrusted_text.py`), the risk engine that checks every order in code whatever the model was persuaded of, and the desks' instructions. The scanner makes attacks visible to the model and the user.

## A bug this file had

The hidden-character pattern was first written with `\u` escapes in an ordinary string, and the file ended up containing the invisible characters themselves; ruff's PLE2502 rule caught it. It is now a raw string, so the file holds only visible escape codes, and the repository was scanned to confirm no source or test file contains invisible characters.
