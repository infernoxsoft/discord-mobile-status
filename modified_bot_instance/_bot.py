from discord import gateway
from discord import Client
from discord.backoff import ExponentialBackoff
from discord.gateway import DiscordWebSocket
from discord.gateway import ReconnectWebSocket
from discord.gateway import _log
from discord.ext import commands
from discord.errors import HTTPException
from discord.errors import GatewayNotFound
from discord.errors import ConnectionClosed
from discord.errors import PrivilegedIntentsRequired
from asyncio import AbstractEventLoop
from asyncio import wait_for
from asyncio import TimeoutError
from asyncio import sleep
from aiohttp import ClientError
from aiohttp import ClientWebSocketResponse
from sys import platform
from typing import Optional
from typing import Self
from yarl import URL


class CustomWebSocket(DiscordWebSocket):
    def __init__(
        self, socket: ClientWebSocketResponse, *, loop: AbstractEventLoop
    ) -> None:
        self.__payload_properties = {
            "$os": platform,
            "$browser": "discord.py",
            "$device": "discord.py",
            "$referrer": "",
            "$referring_domain": "",
        }

        super().__init__(socket=socket, loop=loop)

    def set_websocket_identify_properties(self, properties: dict) -> None:
        self.__payload_properties = properties

    async def identify(self) -> None:
        payload = {
            "op": self.IDENTIFY,
            "d": {
                "token": self.token,
                "properties": self.__payload_properties,
                "compress": True,
                "large_threshold": 250,
                "v": 3,
            },
        }

        if self.shard_id is not None and self.shard_count is not None:
            payload["d"]["shard"] = [self.shard_id, self.shard_count]

        state = self._connection

        if state._activity is not None or state._status is not None:
            payload["d"]["presence"] = {
                "status": state._status,
                "game": state._activity,
                "since": 0,
                "afk": False,
            }

        if state._intents is not None:
            payload["d"]["intents"] = state._intents.value

        await self.call_hooks(
            "before_identify", self.shard_id, initial=self._initial_identify
        )
        await self.send_as_json(payload)
        gateway._log.info("Shard ID %s has sent the IDENTIFY payload.", self.shard_id)

    @classmethod
    async def from_client(
        cls,
        client: Client,
        *,
        initial: bool = False,
        gateway: Optional[URL] = None,
        shard_id: Optional[int] = None,
        session: Optional[str] = None,
        sequence: Optional[int] = None,
        resume: bool = False,
        encoding: str = "json",
        zlib: bool = True,
        websocket_identify_properties: dict = None,
    ) -> Self:
        """Creates a main websocket for Discord from a :class:`Client`.

        This is for internal use only.
        """
        # Circular import
        from discord.http import INTERNAL_API_VERSION

        gateway = gateway or cls.DEFAULT_GATEWAY

        if zlib:
            url = gateway.with_query(
                v=INTERNAL_API_VERSION, encoding=encoding, compress="zlib-stream"
            )

        else:
            url = gateway.with_query(v=INTERNAL_API_VERSION, encoding=encoding)

        socket = await client.http.ws_connect(str(url))
        ws = cls(socket, loop=client.loop)

        # dynamically add attributes needed
        ws.token = client.http.token
        ws._connection = client._connection
        ws._discord_parsers = client._connection.parsers
        ws._dispatch = client.dispatch
        ws.gateway = gateway
        ws.call_hooks = client._connection.call_hooks
        ws._initial_identify = initial
        ws.shard_id = shard_id
        ws._rate_limiter.shard_id = shard_id
        ws.shard_count = client._connection.shard_count
        ws.session_id = session
        ws.sequence = sequence
        ws._max_heartbeat_timeout = client._connection.heartbeat_timeout
        ws.set_websocket_identify_properties(properties=websocket_identify_properties)

        if client._enable_debug_events:
            ws.send = ws.debug_send
            ws.log_receive = ws.debug_log_receive

        client._connection._update_references(ws)

        _log.debug("Created websocket connected to %s", gateway)

        # poll event for OP Hello
        await ws.poll_event()

        if not resume:
            await ws.identify()
            return ws

        await ws.resume()
        return ws


class CustomBot(commands.Bot):
    def __init__(self, *args: tuple, **kwargs: dict) -> None:
        self.__websocket_identify_properties = kwargs.get(
            "ws_identify_properties",
            {
                "$os": platform,
                "$browser": "discord.py",
                "$device": "discord.py",
                "$referrer": "",
                "$referring_domain": "",
            },
        )

        super().__init__(*args, **kwargs)

    def set_ws_identify_properties(self, properties: dict) -> None:
        self.__websocket_identify_properties = properties

    async def connect(self, *, reconnect: bool = True) -> None:
        """|coro|

        Creates a websocket connection and lets the websocket listen
        to messages from Discord. This is a loop that runs the entire
        event system and miscellaneous aspects of the library. Control
        is not resumed until the WebSocket connection is terminated.

        Parameters
        -----------
        reconnect: :class:`bool`
            If we should attempt reconnecting, either due to internet
            failure or a specific failure on Discord's part. Certain
            disconnects that lead to bad state will not be handled (such as
            invalid sharding payloads or bad tokens).

        Raises
        -------
        GatewayNotFound
            If the gateway to connect to Discord is not found. Usually if this
            is thrown then there is a Discord API outage.
        ConnectionClosed
            The websocket connection has been terminated.
        """

        backoff = ExponentialBackoff()
        ws_params = {
            "initial": True,
            "shard_id": self.shard_id,
        }

        while not self.is_closed():
            try:
                coro = CustomWebSocket.from_client(
                    self,
                    **ws_params,
                    websocket_identify_properties=self.__websocket_identify_properties,
                )
                self.ws = await wait_for(coro, timeout=60.0)

                ws_params["initial"] = False

                while True:
                    await self.ws.poll_event()

            except ReconnectWebSocket as e:
                _log.debug("Got a request to %s the websocket.", e.op)
                self.dispatch("disconnect")

                ws_params.update(
                    sequence=self.ws.sequence,
                    resume=e.resume,
                    session=self.ws.session_id,
                )

                if e.resume:
                    ws_params["gateway"] = self.ws.gateway

                continue

            except (
                OSError,
                HTTPException,
                GatewayNotFound,
                ConnectionClosed,
                ClientError,
                TimeoutError,
            ) as exc:
                self.dispatch("disconnect")

                if not reconnect:
                    await self.close()

                    if isinstance(exc, ConnectionClosed) and exc.code == 1000:
                        # clean close, don't re-raise this
                        return

                    raise

                if self.is_closed():
                    return

                # If we get connection reset by peer then try to RESUME
                if isinstance(exc, OSError) and exc.errno in (54, 10054):
                    ws_params.update(
                        sequence=self.ws.sequence,
                        gateway=self.ws.gateway,
                        initial=False,
                        resume=True,
                        session=self.ws.session_id,
                    )
                    continue

                # We should only get this when an unhandled close code happens,
                # such as a clean disconnect (1000) or a bad state (bad token, no sharding, etc)
                # sometimes, discord sends us 1000 for unknown reasons so we should reconnect
                # regardless and rely on is_closed instead
                if isinstance(exc, ConnectionClosed):
                    if exc.code == 4014:
                        raise PrivilegedIntentsRequired(exc.shard_id) from None

                    if exc.code != 1000:
                        await self.close()
                        raise

                retry = backoff.delay()
                _log.exception("Attempting a reconnect in %.2fs", retry)
                await sleep(retry)

                # Always try to RESUME the connection
                # If the connection is not RESUME-able then the gateway will invalidate the session.
                # This is apparently what the official Discord client does.
                ws_params.update(
                    sequence=self.ws.sequence,
                    gateway=self.ws.gateway,
                    resume=True,
                    session=self.ws.session_id,
                )


# example:
# bot = CustomBot(
#     command_prefix="!",
#     intents=Intents.all(),
#     ws_identify_properties={
#         "$os": platform,
#         "$browser": "Discord Android",
#         "$device": "Discord Android",
#         "$referrer": "",
#         "$referring_domain": "",
#     },
# )
