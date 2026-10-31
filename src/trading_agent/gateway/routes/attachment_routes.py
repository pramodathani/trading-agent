"""Routes for the files the user sends with chat messages.

  POST /api/traders/{trader}/attachments          upload one file (a form with a "file" field); answers its attachment
  GET  /api/traders/{trader}/attachments/{id}     the uploaded file itself, for showing a picture or opening a document
  GET  /api/traders/{trader}/pictures/{path}      a picture in the trader's folder, such as a screenshot shown in a tool's card

Sending a message with files takes two steps: each file is uploaded here first, and the message then names the uploads by their identifiers in POST /api/traders/{trader}/messages. Each upload can then fail or succeed on its own, with its own explanation, before anything reaches the trader.

Typical usage example:

  application.include_router(AttachmentRoutes(traders, store, layout, guard).router())
"""

import asyncio
from collections.abc import Mapping
from typing import Any

import fastapi
import fastapi.responses

from trading_agent.attachments import (
    attachment_store as attachment_store_module,
)
from trading_agent.attachments import image_preparer as image_preparer_module
from trading_agent.gateway import access_guard
from trading_agent.gateway.routes import route_group
from trading_agent.runtime import trader_runtime
from trading_agent.workspace import workspace_layout


class AttachmentRoutes(route_group.RouteGroup):
    """The /api/traders/{trader}/attachments routes."""

    def __init__(
        self,
        traders: Mapping[str, trader_runtime.TraderRuntime],
        store: attachment_store_module.AttachmentStore,
        layout: workspace_layout.WorkspaceLayout,
        guard: access_guard.AccessGuard,
    ):
        """Creates the routes.

        Args:
            traders (Mapping[str, trader_runtime.TraderRuntime]): The running traders, keyed by name.
            store (attachment_store_module.AttachmentStore): Where uploads are kept.
            layout (workspace_layout.WorkspaceLayout): Where the trader folders are.
            guard (access_guard.AccessGuard): Checks the access token.
        """
        super().__init__(guard)
        self._traders = traders
        self._store = store
        self._layout = layout
        self._image_preparer = image_preparer_module.ImagePreparer()

    def _add_routes(self, router: fastapi.APIRouter) -> None:
        """Adds the attachment routes.

        Args:
            router (fastapi.APIRouter): The router.
        """
        router.add_api_route(
            '/api/traders/{trader_name}/attachments',
            self.upload,
            methods=['POST'],
            status_code=201,
        )
        router.add_api_route(
            '/api/traders/{trader_name}/attachments/{attachment_id}',
            self.download,
            methods=['GET'],
        )
        router.add_api_route(
            '/api/traders/{trader_name}/pictures/{picture_path:path}',
            self.picture,
            methods=['GET'],
        )

    async def upload(
        self,
        trader_name: str,
        file: fastapi.UploadFile,
    ) -> dict[str, Any]:
        """Stores one uploaded file for a trader, reading a document's text.

        Args:
            trader_name (str): The trader.
            file (fastapi.UploadFile): The uploaded file.

        Returns:
            dict[str, Any]: The stored attachment.

        Raises:
            fastapi.HTTPException: There is no such trader (404), or the file is refused (413 when too large, otherwise 422), with the reason.
        """
        self._find(self._traders, trader_name, 'trader')
        data = await file.read(attachment_store_module.MAXIMUM_BYTES + 1)
        file_name = file.filename or 'file'
        try:
            attachment = await asyncio.to_thread(
                self._store.save, trader_name, file_name, data
            )
        except attachment_store_module.AttachmentRefusedError as error:
            status_code = 422
            if len(data) > attachment_store_module.MAXIMUM_BYTES:
                status_code = 413
            raise fastapi.HTTPException(
                status_code=status_code, detail=str(error)
            ) from error
        return attachment.to_json_dictionary()

    def download(
        self,
        trader_name: str,
        attachment_id: str,
    ) -> fastapi.responses.FileResponse:
        """Answers an uploaded file, shown in the browser rather than saved.

        Args:
            trader_name (str): The trader.
            attachment_id (str): The upload's identifier.

        Returns:
            fastapi.responses.FileResponse: The file, with its media type and name.

        Raises:
            fastapi.HTTPException: There is no such trader or upload, or its file is gone (404).
        """
        self._find(self._traders, trader_name, 'trader')
        try:
            attachment = self._store.find(trader_name, attachment_id)
        except attachment_store_module.AttachmentNotFoundError as error:
            raise fastapi.HTTPException(
                status_code=404, detail=str(error)
            ) from error
        stored = attachment.stored_file()
        if not stored.is_file():
            raise fastapi.HTTPException(
                status_code=404,
                detail=f'The file of upload {attachment_id} is no longer there',
            )
        return fastapi.responses.FileResponse(
            stored,
            media_type=attachment.media_type,
            filename=attachment.file_name,
            content_disposition_type='inline',
        )

    def picture(
        self,
        trader_name: str,
        picture_path: str,
    ) -> fastapi.responses.FileResponse:
        """Answers a picture inside a trader's folder, such as a browser screenshot.

        Only real PNG, JPEG, WebP and GIF pictures are answered, judged by their contents, and only from inside the trader's own folder.

        Args:
            trader_name (str): The trader.
            picture_path (str): The picture's path relative to the trader folder.

        Returns:
            fastapi.responses.FileResponse: The picture, with its media type.

        Raises:
            fastapi.HTTPException: There is no such trader (404), the path leads outside the trader folder or is not a picture (404), or the file is gone (404).
        """
        self._find(self._traders, trader_name, 'trader')
        trader_directory = self._layout.trader_directory(trader_name).resolve()
        path = (trader_directory / picture_path).resolve()
        if not path.is_relative_to(trader_directory) or not path.is_file():
            raise fastapi.HTTPException(
                status_code=404,
                detail=f'The {trader_name} trader has no picture {picture_path}',
            )
        try:
            media_type = self._image_preparer.check(path)
        except image_preparer_module.ImageError as error:
            raise fastapi.HTTPException(
                status_code=404,
                detail=f'{picture_path}: {error}',
            ) from error
        return fastapi.responses.FileResponse(
            path,
            media_type=media_type,
            content_disposition_type='inline',
        )
