"""Tests for serving the built web page from the gateway."""

from pathlib import Path

import fastapi
import fastapi.testclient

from trading_agent.gateway.routes import frontend_routes


def _client(directory: Path) -> fastapi.testclient.TestClient:
    """Builds a client for the web page routes alone.

    Args:
        directory (Path): The build folder.

    Returns:
        fastapi.testclient.TestClient: The client.
    """
    application = fastapi.FastAPI()
    application.include_router(
        frontend_routes.FrontendRoutes(directory).router()
    )
    return fastapi.testclient.TestClient(application)


def _build(directory: Path) -> Path:
    """Writes a tiny build: index.html, one asset and a file outside the build.

    Args:
        directory (Path): A scratch folder.

    Returns:
        Path: The build folder.
    """
    build = directory / 'dist'
    (build / 'assets').mkdir(parents=True)
    (build / 'index.html').write_text('<p>page</p>', encoding='utf-8')
    (build / 'assets' / 'index-abc.js').write_text(
        'console.log(1)', encoding='utf-8'
    )
    (directory / 'secret.txt').write_text('secret', encoding='utf-8')
    return build


class TestFrontendRoutes:
    """Tests for the catch-all page route."""

    def test_page_address_gets_index(self, tmp_path: Path) -> None:
        """An address the browser handles, such as /chat, is answered with index.html."""
        client = _client(_build(tmp_path))

        response = client.get('/chat')

        assert response.status_code == 200
        assert response.text == '<p>page</p>'
        assert response.headers['cache-control'] == 'no-cache'

    def test_asset_is_served_with_a_long_cache(self, tmp_path: Path) -> None:
        """A built asset is served as it is and may be cached for a year."""
        client = _client(_build(tmp_path))

        response = client.get('/assets/index-abc.js')

        assert response.text == 'console.log(1)'
        assert 'immutable' in response.headers['cache-control']

    def test_api_addresses_are_not_answered_with_the_page(
        self, tmp_path: Path
    ) -> None:
        """A mistyped API, WebSocket or webhook address gets 404, not the page."""
        client = _client(_build(tmp_path))

        for address in ('/api/nothing', '/ws/nothing', '/hooks/nothing'):
            assert client.get(address).status_code == 404

    def test_files_outside_the_build_are_not_served(
        self, tmp_path: Path
    ) -> None:
        """A path that climbs out of the build folder gets the page, not the file."""
        client = _client(_build(tmp_path))

        response = client.get('/..%2Fsecret.txt')

        assert 'secret' not in response.text

    def test_missing_build_explains_itself(self, tmp_path: Path) -> None:
        """Without a build, the page says how to build it."""
        client = _client(tmp_path / 'not-built')

        response = client.get('/')

        assert response.status_code == 503
        assert 'npm run build' in response.text
