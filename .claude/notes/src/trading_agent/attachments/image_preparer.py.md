# image_preparer.py

Uses Pillow 12.3.0, which was already installed as a dependency of another package and is now pinned in pyproject.toml.

## `check`

The media type is taken from the file's contents (`picture.format`), not its name or the browser's claim, so a JPEG named `.png` is labelled correctly for the model, and a text file named `.png` is refused. `verify()` catches truncated files. Pillow's `DecompressionBombError` refuses pictures over about 178 million pixels, which could otherwise exhaust memory when opened.

## `prepare`

1. `exif_transpose` turns phone photos upright. Phones store the picture sideways with an orientation tag; models ignore the tag, so without this a portrait photo of a chart reaches the model on its side.
2. `thumbnail` shrinks to at most 1568 pixels on the long side, keeping the shape and never enlarging. 1568 is the size above which Claude's API downsizes pictures anyway; the local models also do better with smaller pictures, and each pixel costs context.
3. The copy is saved as a JPEG at quality 85, or as a PNG when the picture has transparency, which JPEG cannot hold. A GIF's first frame is used.

The copy is made at each turn rather than stored, so a later change of size limit applies to old uploads too, and nothing extra is kept on disk. Preparing one picture takes tens of milliseconds.

`prepare` returns None for a picture whose file is gone or broken, so a turn that names a deleted upload still runs, without the picture, instead of failing.
