"""Routes for the files the user sends with chat messages.

  POST /api/desks/{desk}/attachments          upload one file (a form with a "file" field); answers its attachment
  GET  /api/desks/{desk}/attachments/{id}     the uploaded file itself, for showing a picture or opening a document

Sending a message with files takes two steps: each file is uploaded here first, and the message then names the uploads by their identifiers in POST /api/desks/{desk}/messages. Each upload can then fail or succeed on its own, with its own explanation, before anything reaches the desk.

Typical usage example:

  application.include_router(AttachmentRoutes(desks, store, guard).router())
"""

import asyncio
from collections.abc import Mapping
from typing import Any

import fastapi
import fastapi.responses

from trading_agent.attachments import (
    attachment_store as attachment_store_module,
)
from trading_agent.gateway import access_guard
from trading_agent.gateway.routes import route_group
from trading_agent.runtime import desk_runtime


class AttachmentRoutes(route_group.RouteGroup):
    """The /api/desks/{desk}/attachments routes."""

    def __init__(
        self,
        desks: Mapping[str, desk_runtime.DeskRuntime],
        store: attachment_store_module.AttachmentStore,
        guard: access_guard.AccessGuard,
    ):
        """Creates the routes.

        Args:
            desks (Mapping[str, desk_runtime.DeskRuntime]): The running desks, keyed by name.
            store (attachment_store_module.AttachmentStore): Where uploads are kept.
            guard (access_guard.AccessGuard): Checks the access token.
        """
        super().__init__(guard)
        self._desks = desks
        self._store = store

    def _add_routes(self, router: fastapi.APIRouter) -> None:
        """Adds the attachment routes.

        Args:
            router (fastapi.APIRouter): The router.
        """
        router.add_api_route(
            '/api/desks/{desk_name}/attachments',
            self.upload,
            methods=['POST'],
            status_code=201,
        )
        router.add_api_route(
            '/api/desks/{desk_name}/attachments/{attachment_id}',
            self.download,
            methods=['GET'],
        )

    async def upload(
        self,
        desk_name: str,
        file: fastapi.UploadFile,
    ) -> dict[str, Any]:
        """Stores one uploaded file for a desk, reading a document's text.

        Args:
            desk_name (str): The desk.
            file (fastapi.UploadFile): The uploaded file.

        Returns:
            dict[str, Any]: The stored attachment.

        Raises:
            fastapi.HTTPException: There is no such desk (404), or the file is refused (413 when too large, otherwise 422), with the reason.
        """
        self._find(self._desks, desk_name, 'desk')
        data = await file.read(attachment_store_module.MAXIMUM_BYTES + 1)
        file_name = file.filename or 'file'
        try:
            attachment = await asyncio.to_thread(
                self._store.save, desk_name, file_name, data
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
        desk_name: str,
        attachment_id: str,
    ) -> fastapi.responses.FileResponse:
        """Answers an uploaded file, shown in the browser rather than saved.

        Args:
            desk_name (str): The desk.
            attachment_id (str): The upload's identifier.

        Returns:
            fastapi.responses.FileResponse: The file, with its media type and name.

        Raises:
            fastapi.HTTPException: There is no such desk or upload, or its file is gone (404).
        """
        self._find(self._desks, desk_name, 'desk')
        try:
            attachment = self._store.find(desk_name, attachment_id)
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
