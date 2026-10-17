"""Serves the built web page, falling back to index.html for the page's own addresses.

The web page is a single-page React application: addresses such as /chat/main are handled in the browser, so the server answers each of them with index.html. Files the build produced, such as scripts and styles, are served as they are. Addresses under /api, /ws and /hooks are never answered with the page, so a mistyped API address gets a clear 404.

This route needs no access token: the page itself holds no data, and every request it makes for data carries the token.

Typical usage example:

  application.include_router(FrontendRoutes(Path('frontend/dist')).router())
"""

from pathlib import Path

import fastapi
import fastapi.responses

_NOT_BUILT_PAGE = '<!doctype html><title>trading-agent</title><p>The web page has not been built. Run <code>npm run build</code> in <code>frontend/</code>.</p>'
_RESERVED_PREFIXES = (
    'api',
    'ws',
    'hooks',
)


class FrontendRoutes:
    """The catch-all route for the web page; it must be the last router added."""

    def __init__(self, frontend_directory: Path):
        """Creates the route.

        Args:
            frontend_directory (Path): The Vite build output folder.
        """
        self._frontend_directory = frontend_directory.resolve()

    def router(self) -> fastapi.APIRouter:
        """Builds the router holding the catch-all route.

        Returns:
            fastapi.APIRouter: The router.
        """
        router = fastapi.APIRouter()
        router.add_api_route(
            '/{path:path}',
            self.serve,
            methods=[
                'GET',
            ],
            include_in_schema=False,
        )
        return router

    def serve(self, path: str) -> fastapi.responses.Response:
        """Serves a built file, or index.html for any other page address.

        Args:
            path (str): The requested path without the leading slash.

        Returns:
            fastapi.responses.Response: The file, index.html, or a page explaining that the web page is not built.

        Raises:
            fastapi.HTTPException: The address is under /api, /ws or /hooks (status 404).
        """
        first_part = path.split('/', 1)[0]
        if first_part in _RESERVED_PREFIXES:
            raise fastapi.HTTPException(status_code=404, detail='Not found')
        index = self._frontend_directory / 'index.html'
        if not index.is_file():
            return fastapi.responses.HTMLResponse(
                _NOT_BUILT_PAGE, status_code=503
            )
        if path:
            candidate = (self._frontend_directory / path).resolve()
            inside = candidate.is_relative_to(self._frontend_directory)
            if inside and candidate.is_file():
                return fastapi.responses.FileResponse(
                    candidate, headers=self._cache_headers(path)
                )
        return fastapi.responses.FileResponse(
            index,
            headers={
                'Cache-Control': 'no-cache',
            },
        )

    def _cache_headers(self, path: str) -> dict[str, str]:
        """Chooses how long a browser may keep a built file.

        Args:
            path (str): The file's path inside the build folder.

        Returns:
            dict[str, str]: A long cache for files under assets/, whose names change with their content, and no cache for the rest.
        """
        if path.startswith('assets/'):
            return {
                'Cache-Control': 'public, max-age=31536000, immutable',
            }
        return {
            'Cache-Control': 'no-cache',
        }
