"""Tests for the pictures desks show: view_image, send_image, tool-card pictures and Telegram photos."""

import asyncio
import io
from pathlib import Path

import fastapi
import fastapi.testclient
import PIL.Image

from tests import test_openai_compatible_backend
from trading_agent.agent import conversation as conversation_module
from trading_agent.agent import loop_guard
from trading_agent.agent import messages
from trading_agent.attachments import (
    attachment_store as attachment_store_module,
)
from trading_agent.backends import ollama_backend
from trading_agent.channels import notification_formatter
from trading_agent.channels import pairing_store as pairing_store_module
from trading_agent.channels import telegram_channel
from trading_agent.configuration import agent_configuration
from trading_agent.gateway import access_guard
from trading_agent.gateway.routes import attachment_routes
from trading_agent.runtime import event as event_module
from trading_agent.runtime import event_bus as event_bus_module
from trading_agent.runtime import trigger as trigger_module
from trading_agent.tools import path_policy
from trading_agent.tools import send_image_tool
from trading_agent.tools import tool
from trading_agent.tools import tool_call_executor
from trading_agent.tools import tool_registry
from trading_agent.tools import view_image_tool
from trading_agent.workspace import workspace_layout

_TOKEN = 'test-access-token'
_OWNER = 111
_SECOND_CHAT = 222


def _picture(width: int = 40, height: int = 30) -> bytes:
    """Draws a plain PNG picture.

    Args:
        width (int): Its width in pixels.
        height (int): Its height in pixels.

    Returns:
        bytes: The encoded picture.
    """
    output = io.BytesIO()
    PIL.Image.new('RGB', (width, height), 'teal').save(output, format='PNG')
    return output.getvalue()


def _desk(directory: Path) -> tuple[Path, path_policy.PathPolicy]:
    """Makes a main desk folder with a picture in scratch/ and a secret beside it.

    Args:
        directory (Path): A scratch workspace.

    Returns:
        tuple[Path, path_policy.PathPolicy]: The desk folder and its file rules, with secrets/ hidden.
    """
    layout = workspace_layout.WorkspaceLayout(directory)
    desk_directory = layout.desk_directory('main')
    (desk_directory / 'scratch').mkdir(parents=True)
    (desk_directory / 'scratch' / 'chart.png').write_bytes(_picture())
    (desk_directory / 'scratch' / 'notes.txt').write_text('not a picture')
    (desk_directory / 'scratch' / 'fake.png').write_text('not a picture')
    secrets = directory / 'secrets'
    secrets.mkdir()
    (secrets / 'key.png').write_bytes(_picture())
    return desk_directory, path_policy.PathPolicy(
        desk_directory,
        [
            secrets,
        ],
    )


class TestViewImageTool:
    """Tests for looking at a picture file."""

    def test_picture_is_shown_with_its_path(self, tmp_path: Path) -> None:
        """A picture in the desk folder comes back as an image, with its path for the web page."""
        _desk_directory, policy = _desk(tmp_path)
        viewer = view_image_tool.ViewImageTool(policy)

        result = asyncio.run(
            viewer.run(
                view_image_tool.ViewImageArguments(path='scratch/chart.png')
            )
        )

        assert not result.is_error
        assert result.image is not None
        assert result.image.media_type == 'image/jpeg'
        assert result.picture_desk_path == 'scratch/chart.png'

    def test_text_file_is_refused(self, tmp_path: Path) -> None:
        """A file that is not a picture, even one named .png, gives an error and no image."""
        _desk_directory, policy = _desk(tmp_path)
        viewer = view_image_tool.ViewImageTool(policy)

        result = asyncio.run(
            viewer.run(
                view_image_tool.ViewImageArguments(path='scratch/fake.png')
            )
        )

        assert result.is_error
        assert result.image is None
        assert 'not a picture' in result.text

    def test_secret_picture_is_refused(self, tmp_path: Path) -> None:
        """A picture inside a hidden secret folder cannot be looked at."""
        _desk_directory, policy = _desk(tmp_path)
        viewer = view_image_tool.ViewImageTool(policy)

        result = asyncio.run(
            viewer.run(
                view_image_tool.ViewImageArguments(
                    path=str(tmp_path / 'secrets' / 'key.png')
                )
            )
        )

        assert result.is_error
        assert 'secrets' in result.text


class TestSendImageTool:
    """Tests for showing the user a picture."""

    def _tool(
        self, directory: Path
    ) -> tuple[
        send_image_tool.SendImageTool,
        event_bus_module.EventSubscription,
        attachment_store_module.AttachmentStore,
    ]:
        """Builds the tool for a main desk.

        Args:
            directory (Path): A scratch workspace.

        Returns:
            tuple[send_image_tool.SendImageTool, event_bus_module.EventSubscription, attachment_store_module.AttachmentStore]: The tool, a subscription to its events, and the upload store.
        """
        _desk_directory, policy = _desk(directory)
        event_bus = event_bus_module.EventBus()
        subscription = event_bus.subscribe()
        store = attachment_store_module.AttachmentStore(
            workspace_layout.WorkspaceLayout(directory)
        )
        sender = send_image_tool.SendImageTool(policy, store, event_bus, 'main')
        return sender, subscription, store

    def test_picture_is_kept_and_published(self, tmp_path: Path) -> None:
        """The picture is copied into uploads and published as a message carrying it."""
        sender, subscription, store = self._tool(tmp_path)

        result = asyncio.run(
            sender.run(
                send_image_tool.SendImageArguments(
                    path='scratch/chart.png', caption='Today'
                )
            )
        )
        published = asyncio.run(subscription.next_event())

        assert not result.is_error
        assert published.kind == event_module.EventKind.MESSAGE
        assert published.desk == 'main'
        assert published.payload['text'] == 'Today'
        sent = published.payload['attachments'][0]
        kept = store.find('main', sent['attachment_id'])
        assert kept.is_image
        assert kept.desk_path.startswith('uploads/')
        assert kept.stored_file().read_bytes() == _picture()

    def test_document_is_refused(self, tmp_path: Path) -> None:
        """A text file is refused with advice to save a picture first."""
        sender, _subscription, _store = self._tool(tmp_path)

        result = asyncio.run(
            sender.run(
                send_image_tool.SendImageArguments(path='scratch/notes.txt')
            )
        )

        assert result.is_error
        assert 'save a chart or table as PNG first' in result.text

    def test_fake_picture_is_refused(self, tmp_path: Path) -> None:
        """A file named .png that holds text is refused by its contents."""
        sender, _subscription, _store = self._tool(tmp_path)

        result = asyncio.run(
            sender.run(
                send_image_tool.SendImageArguments(path='scratch/fake.png')
            )
        )

        assert result.is_error
        assert 'not a picture that can be read' in result.text


class _PictureTool(tool.Tool):
    """A tool that returns a picture saved in the desk folder."""

    name = 'show_picture'
    description = 'Returns a picture.'

    async def run(self, arguments: tool.NoArguments) -> tool.ToolResult:
        """Returns the picture.

        Args:
            arguments (tool.NoArguments): No arguments.

        Returns:
            tool.ToolResult: A picture with its desk path.
        """
        del arguments
        return tool.ToolResult(
            text='A picture.',
            image=messages.MessageImage('image/png', _picture()),
            picture_desk_path='scratch/chart.png',
        )


class TestToolPictures:
    """Tests for pictures returned by tools, on their way to the models and the web page."""

    def test_tool_result_event_names_the_picture(self) -> None:
        """The published tool result carries the picture's path for the tool card."""
        event_bus = event_bus_module.EventBus()
        subscription = event_bus.subscribe()
        executor = tool_call_executor.ToolCallExecutor(
            'main',
            tool_registry.ToolRegistry(
                [
                    _PictureTool(),
                ],
                timeout_seconds=10,
            ),
            event_bus,
            loop_guard.LoopGuard(3),
        )
        trigger = trigger_module.Trigger.now(
            trigger_module.TriggerSource.USER_MESSAGE, 'main', 'show me'
        )

        result = asyncio.run(
            executor.execute(trigger, messages.ToolCall.new('show_picture', {}))
        )
        asyncio.run(subscription.next_event())
        published = asyncio.run(subscription.next_event())

        assert result.image is not None
        assert published.kind == event_module.EventKind.TOOL_RESULT
        assert published.payload['picture_path'] == 'scratch/chart.png'

    def _conversation(self) -> conversation_module.Conversation:
        """Builds a conversation in which one tool call returned a JPEG picture.

        Returns:
            conversation_module.Conversation: The conversation.
        """
        call = messages.ToolCall('call-1', 'view_image', {})
        conversation = conversation_module.Conversation('be brief')
        conversation.append(messages.ConversationMessage.user('Look'))
        conversation.append(messages.ConversationMessage.assistant('', [call]))
        conversation.append(
            messages.ConversationMessage.tool_result(
                call,
                'This is the picture.',
                False,
                messages.MessageImage('image/jpeg', b'\xff\xd8picture'),
            )
        )
        return conversation

    def test_openai_models_get_the_picture_in_a_user_message(self) -> None:
        """Chat Completions takes only text from tools, so the picture follows in a user message."""
        backend = test_openai_compatible_backend._backend()

        wire = backend._wire_messages(self._conversation())

        assert wire[3]['role'] == 'tool'
        assert 'next user message' in wire[3]['content']
        assert wire[4]['role'] == 'user'
        assert 'view_image' in wire[4]['content'][0]['text']
        assert wire[4]['content'][1]['image_url']['url'].startswith(
            'data:image/jpeg;base64,'
        )

    def test_ollama_gets_the_picture_in_the_tool_message(self) -> None:
        """Ollama takes pictures in the tool message itself, of any media type."""
        backend = ollama_backend.OllamaBackend(
            'gemma',
            agent_configuration.BackendConfiguration(
                kind='ollama',
                base_url='http://127.0.0.1:11434',
                model='gemma4:31b',
                context_window=32768,
            ),
        )

        wire = backend._wire_messages(self._conversation())

        assert wire[3]['role'] == 'tool'
        assert wire[3]['images'] == [
            messages.MessageImage(
                'image/jpeg', b'\xff\xd8picture'
            ).base64_data(),
        ]


class _StandInDesk:
    """A desk the routes can find."""


class TestPictureRoute:
    """Tests for GET /api/desks/{desk}/pictures/{path}."""

    def _client(self, directory: Path) -> fastapi.testclient.TestClient:
        """Mounts the attachment routes over a desk with pictures.

        Args:
            directory (Path): A scratch workspace.

        Returns:
            fastapi.testclient.TestClient: A client sending the token.
        """
        _desk(directory)
        layout = workspace_layout.WorkspaceLayout(directory)
        application = fastapi.FastAPI()
        application.include_router(
            attachment_routes.AttachmentRoutes(
                {
                    'main': _StandInDesk(),
                },
                attachment_store_module.AttachmentStore(layout),
                layout,
                access_guard.AccessGuard(_TOKEN),
            ).router()
        )
        return fastapi.testclient.TestClient(
            application,
            headers={
                'Authorization': f'Bearer {_TOKEN}',
            },
        )

    def test_picture_in_the_desk_folder_is_served(self, tmp_path: Path) -> None:
        """A screenshot-like picture comes back with its media type."""
        client = self._client(tmp_path)

        answer = client.get('/api/desks/main/pictures/scratch/chart.png')

        assert answer.status_code == 200
        assert answer.headers['content-type'] == 'image/png'
        assert answer.content == _picture()

    def test_path_outside_the_desk_is_refused(self, tmp_path: Path) -> None:
        """A path climbing out of the desk folder finds nothing."""
        client = self._client(tmp_path)

        answer = client.get(
            '/api/desks/main/pictures/scratch/%2E%2E/%2E%2E/%2E%2E/secrets/key.png'
        )

        assert answer.status_code == 404

    def test_file_that_is_not_a_picture_is_refused(
        self, tmp_path: Path
    ) -> None:
        """A text file named .png is not served."""
        client = self._client(tmp_path)

        answer = client.get('/api/desks/main/pictures/scratch/fake.png')

        assert answer.status_code == 404


class _PhotoTelegram:
    """Telegram's servers, recording the photos and messages sent.

    Attributes:
        photos: Every photo sent, as (chat id, file name, caption).
        sent: Every text message sent, as (chat id, text).
    """

    def __init__(self):
        """Creates the stand-in with nothing sent."""
        self.photos: list[tuple[int, str, str]] = []
        self.sent: list[tuple[int, str]] = []

    async def send_photo(self, chat_id: int, path: Path, caption: str) -> None:
        """Records a photo.

        Args:
            chat_id (int): The chat.
            path (Path): The picture.
            caption (str): Its caption.
        """
        self.photos.append((chat_id, path.name, caption))

    async def send(self, chat_id: int, text: str) -> None:
        """Records a message.

        Args:
            chat_id (int): The chat.
            text (str): The message.
        """
        self.sent.append((chat_id, text))


class TestTelegramPictures:
    """Tests for sending the pictures desks show to Telegram."""

    def _channel(
        self,
        directory: Path,
        api: _PhotoTelegram,
        notifications: list[str],
    ) -> telegram_channel.TelegramChannel:
        """Builds a channel with two paired chats.

        Args:
            directory (Path): A scratch folder.
            api (_PhotoTelegram): The stand-in.
            notifications (list[str]): The kinds of notification pushed.

        Returns:
            telegram_channel.TelegramChannel: The channel.
        """
        pairing = pairing_store_module.PairingStore(
            directory / 'telegram_pairing.json'
        )
        pairing.approve(pairing.request(_OWNER, 'Owner'), 'main')
        pairing.approve(pairing.request(_SECOND_CHAT, 'Phone'), 'main')
        return telegram_channel.TelegramChannel(
            api,
            pairing,
            None,
            notification_formatter.NotificationFormatter(notifications),
            {},
            {},
            event_bus_module.EventBus(),
            'main',
        )

    def _picture_message(self, directory: Path) -> event_module.Event:
        """Builds the message event send_image publishes.

        Args:
            directory (Path): Where the picture is written.

        Returns:
            event_module.Event: The event.
        """
        path = directory / 'table.png'
        path.write_bytes(_picture())
        return event_module.Event.now(
            event_module.EventKind.MESSAGE,
            'main',
            {
                'text': 'The table you asked for',
                'urgent': False,
                'attachments': [
                    {
                        'path': str(path),
                    },
                ],
            },
        )

    async def _forward_all(
        self,
        channel: telegram_channel.TelegramChannel,
        events: list[event_module.Event],
    ) -> None:
        """Hands events to the channel in order.

        Args:
            channel (telegram_channel.TelegramChannel): The channel.
            events (list[event_module.Event]): The events.
        """
        for published_event in events:
            await channel._forward(published_event)

    def test_picture_goes_to_the_chat_that_asked(self, tmp_path: Path) -> None:
        """A picture shown during a turn started from Telegram goes only to that chat."""
        api = _PhotoTelegram()
        channel = self._channel(tmp_path, api, [])
        channel._reply_chats['trigger-1'] = {
            _OWNER,
        }

        asyncio.run(
            self._forward_all(
                channel,
                [
                    event_module.Event.now(
                        event_module.EventKind.TURN_STARTED,
                        'main',
                        {
                            'trigger_id': 'trigger-1',
                        },
                    ),
                    self._picture_message(tmp_path),
                ],
            )
        )

        assert api.photos == [
            (
                _OWNER,
                'table.png',
                'The table you asked for',
            ),
        ]

    def test_picture_is_pushed_when_messages_are(self, tmp_path: Path) -> None:
        """With no chat waiting, the picture goes to every paired chat when messages are pushed."""
        api = _PhotoTelegram()
        channel = self._channel(
            tmp_path,
            api,
            [
                'messages',
            ],
        )

        asyncio.run(
            self._forward_all(channel, [self._picture_message(tmp_path)])
        )

        assert sorted(api.photos) == [
            (
                _OWNER,
                'table.png',
                'Picture from main:\nThe table you asked for',
            ),
            (
                _SECOND_CHAT,
                'table.png',
                'Picture from main:\nThe table you asked for',
            ),
        ]

    def test_picture_is_not_pushed_when_messages_are_off(
        self, tmp_path: Path
    ) -> None:
        """With no chat waiting and messages not pushed, nothing is sent."""
        api = _PhotoTelegram()
        channel = self._channel(tmp_path, api, [])

        asyncio.run(
            self._forward_all(channel, [self._picture_message(tmp_path)])
        )

        assert api.photos == []
        assert api.sent == []


class TestKeepingNewestPictures:
    """Tests for taking older pictures out of a conversation."""

    def _conversation(
        self, picture_count: int
    ) -> conversation_module.Conversation:
        """Builds a conversation with one screenshot result per picture.

        Args:
            picture_count (int): How many tool results carry a picture.

        Returns:
            conversation_module.Conversation: The conversation.
        """
        conversation = conversation_module.Conversation('be brief')
        conversation.append(
            messages.ConversationMessage.user(
                'Look at this',
                (messages.MessageImage('image/jpeg', b'user picture'),),
            )
        )
        for index in range(picture_count - 1):
            call = messages.ToolCall(f'call-{index}', 'browser_screenshot', {})
            conversation.append(
                messages.ConversationMessage.assistant('', [call])
            )
            conversation.append(
                messages.ConversationMessage.tool_result(
                    call,
                    f'Screenshot saved as scratch/screenshots/{index}.png.',
                    False,
                    messages.MessageImage('image/png', b'screenshot'),
                )
            )
        return conversation

    def test_only_the_newest_pictures_stay(self) -> None:
        """With six pictures and four kept, the two oldest become notes and keep their text."""
        conversation = self._conversation(6)

        removed = conversation.keep_newest_pictures(4)

        kept = []
        for message in conversation.messages:
            if message.image is not None or message.images:
                kept.append(message)
        first = conversation.messages[0]
        first_screenshot = conversation.messages[2]
        assert removed == 2
        assert len(kept) == 4
        assert first.images == ()
        assert first.text.startswith('Look at this\n[The picture that was here')
        assert first_screenshot.image is None
        assert 'scratch/screenshots/0.png' in first_screenshot.text
        assert 'view_image shows it again' in first_screenshot.text

    def test_nothing_changes_under_the_limit(self) -> None:
        """With no more pictures than are kept, the conversation is untouched."""
        conversation = self._conversation(3)
        before = conversation.messages

        removed = conversation.keep_newest_pictures(4)

        assert removed == 0
        assert conversation.messages == before
