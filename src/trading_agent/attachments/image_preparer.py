"""Checks uploaded pictures, and prepares them for the models.

A phone photo is often 4000 pixels wide and several megabytes, while the models see detail only up to about 1568 pixels on the long side and charge context for every pixel up to that. Before a picture goes to a model it is turned upright by its EXIF orientation, shrunk to at most 1568 pixels on its long side, and saved as a JPEG, or as a PNG when it has transparency. The uploaded file itself is kept unchanged.

Typical usage example:

  preparer = ImagePreparer()
  media_type = preparer.check(path)
  image = preparer.prepare(path)
"""

import io
from pathlib import Path

import PIL
import PIL.Image
import PIL.ImageOps

from trading_agent.agent import messages

_LONGEST_SIDE = 1568
_JPEG_QUALITY = 85
_MEDIA_TYPES = {
    'PNG': 'image/png',
    'JPEG': 'image/jpeg',
    'WEBP': 'image/webp',
    'GIF': 'image/gif',
}
_OPEN_ERRORS = (
    PIL.UnidentifiedImageError,
    PIL.Image.DecompressionBombError,
    OSError,
    ValueError,
)


class ImageError(ValueError):
    """A file is not a picture that can be used."""


class ImagePreparer:
    """Checks pictures and resizes them for the models."""

    def check(self, path: Path) -> str:
        """Checks that a file is a PNG, JPEG, WebP or GIF picture.

        Args:
            path (Path): The file.

        Returns:
            str: Its media type, from the file's contents rather than its name.

        Raises:
            ImageError: The file is not one of those pictures, or is damaged.
        """
        try:
            with PIL.Image.open(path) as picture:
                picture_format = picture.format
                picture.verify()
        except _OPEN_ERRORS as error:
            raise ImageError(
                f'it is not a picture that can be read ({type(error).__name__})'
            ) from error
        if picture_format not in _MEDIA_TYPES:
            raise ImageError(
                f'{picture_format} pictures are not accepted; send PNG, JPEG, WebP or GIF'
            )
        return _MEDIA_TYPES[picture_format]

    def prepare(self, path: Path) -> messages.MessageImage | None:
        """Makes the copy of a picture that a model is sent.

        Args:
            path (Path): The picture.

        Returns:
            messages.MessageImage | None: The upright, resized picture, or None when the file is gone or cannot be read.
        """
        try:
            with PIL.Image.open(path) as opened:
                picture = PIL.ImageOps.exif_transpose(opened)
                picture.load()
        except _OPEN_ERRORS:
            return None
        picture.thumbnail(
            (
                _LONGEST_SIDE,
                _LONGEST_SIDE,
            )
        )
        output = io.BytesIO()
        if self._has_transparency(picture):
            picture.convert('RGBA').save(output, format='PNG', optimize=True)
            return messages.MessageImage('image/png', output.getvalue())
        picture.convert('RGB').save(
            output, format='JPEG', quality=_JPEG_QUALITY
        )
        return messages.MessageImage('image/jpeg', output.getvalue())

    def _has_transparency(self, picture: PIL.Image.Image) -> bool:
        """Says whether a picture has see-through parts, which JPEG would lose.

        Args:
            picture (PIL.Image.Image): The picture.

        Returns:
            bool: True for a picture with an alpha channel or a transparent colour.
        """
        if picture.mode in ('RGBA', 'LA'):
            return True
        return 'transparency' in picture.info
