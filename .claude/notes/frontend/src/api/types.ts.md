# types.ts

These interfaces mirror the JSON the gateway's routes return. They are written by hand from the route code rather than generated, which keeps the build simple; when a route's answer changes, this file must change with it.

## `Attachment`, since 2026-10-17

Mirrors `Attachment.to_json_dictionary` in Python, minus the absolute `path`, which the page has no use for.
