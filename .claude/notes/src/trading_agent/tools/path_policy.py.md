# path_policy.py

The file tools follow the user's decision that a trader may edit only its own notes and memory. Relative paths start at the trader's folder, so `Memory.md` and `notes/x.md` mean the trader's own files. Every path is resolved before it is checked, so `notes/../../TradingRules.md` and a link inside `notes/` pointing at the user's file are both refused; tests cover both.

Reading is allowed anywhere except the same secrets the bash sandbox hides, because the terminal can already read the rest of the filesystem; refusing reads that the terminal allows would only make the tools inconsistent.
