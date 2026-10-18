# formatter.py

Python's own locale formatting cannot do Indian digit grouping (1,23,456) without the en_IN locale being installed, so `grouped()` does it by hand: the last three digits, then pairs. The web page's loss sign is the Unicode minus (−), kept here so both show the same text.
