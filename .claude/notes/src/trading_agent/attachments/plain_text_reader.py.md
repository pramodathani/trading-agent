# plain_text_reader.py

Reads files that are already text: `.txt`, `.md`, `.csv`, `.tsv`, `.json`.

`utf-8-sig` drops the byte-order mark that Excel puts at the start of CSV files it saves as "CSV UTF-8"; without it the first column's name would start with an invisible character. Bytes that are not UTF-8 are replaced rather than refused, because a CSV exported by a broker in another encoding is still mostly readable, and a few replaced characters are better than no document.
