# ruff.toml

Copied from sridhara so that the projects agree. Python 3.14 is the target and the line length is 80.

- `force-single-line` puts each import on its own line, as the Google style guide asks; `typing` and `collections.abc` may name several symbols on one line.
- Single quotes are the formatter's quote style, matching sridhara.
- `FLY002`, `TRY004` and `UP040` are ignored for the reasons recorded in sridhara's own note: joined lists of lines are the readable way to build multi-line test text, `ValueError` is used for every wrong-kind value as the Google guide advises, and the guide asks for `TypeAlias` annotations rather than `type` statements.

Ruff 0.16's default rule set includes the `BLE` (blind except) and `SIM` (simplify) rules. The one deliberate `except Exception` in `doctor.py` carries a `# noqa: BLE001` directive, because the doctor must report a crashing check rather than crash itself.
