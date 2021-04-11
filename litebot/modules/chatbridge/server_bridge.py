from typing import Optional, List

from discord.ext import commands

from litebot.errors import ServerNotFound
from litebot.minecraft import server_commands
from litebot.minecraft.server import MinecraftServer
from litebot.minecraft.server_commands.server_context import ServerCommandContext, ServerEventContext


class BridgeConnection:
    """
    Models a bridge connection.
    Models either the connection for a single player, or for an entire server
    """
    def __init__(self, origin_server: MinecraftServer, connected_servers: List[MinecraftServer], player: Optional[str] = None) -> None:
        """
        :param origin_server: The server that is being connected
        :type origin_server: MinecraftServer
        :param connected_servers: The servers that the origin server is connected to
        :type connected_servers: List[MinecraftServer]
        :param player: The player that is being connected
        :type player: Optional[str]
        """
        self.player = player
        self.origin_server = origin_server
        self._connected_servers = connected_servers

    async def send_bridge_message(self, source_server: MinecraftServer, message: str) -> None:
        """
        Sends a message to all the connected servers.
        Sends a message from the connected servers to the origin server
        :param source_server: The server that the message was sent on
        :type source_server: MinecraftServer
        :param message: The message that was sent
        :type message: str
        """
        if source_server in self._connected_servers and source_server is not self.origin_server:
            await self.origin_server.send_message(player=self.player, message=message)

        for server in self._connected_servers:
            if server is not source_server:
                await server.send_message(message=message)

    async def send_discord_message(self, source_server: MinecraftServer, message: str) -> None:
        """
        Sends a discord message from the source server to the bridge channels for the connected servers.
        :param source_server: The server that the message was sent on
        :type source_server: MinecraftServer
        :param message: The message that was sent
        :type message: str
        """
        for server in self._connected_servers:
            if server is not source_server:
                await server.dispatch_message(message)

class ServerBridge(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.connections: List[BridgeConnection] = [] 

    @server_commands.command(name="bridge")
    async def _bridge_command(self, ctx: ServerCommandContext) -> None:
        """
        Defines a server command called `bridge`.
        This function is never invoked, just serves as a namespace to register the subcommands.
        :param ctx: The context with which the command is invoked
        :type ctx: ServerCommandContext
        """
        pass

    @_bridge_command.sub(name="send")
    async def _bridge_player_send(self, ctx: ServerCommandContext, message: str, server_name: str) -> None:
        """
        Sends a single message to another another server
        `message` The message to send
        `server_name` The name of the server to send the message to
        """
        try:
            servers = [MinecraftServer.get_from_name(server_name)]
        except ServerNotFound:
            servers = [s for s in MinecraftServer.get_all_instances() if s is not ctx.server]

        for server in servers:
            await server.send_message(message=message)

    @_bridge_command.sub(name="connect")
    async def _bridge_player_connect(self, ctx: ServerCommandContext, server_name: Optional[str] = None) -> None:
        """
        Connects a single player to another server.
        All messages sent by the player will be forwarded to all players on the connected servers.
        All messages sent by players on connected servers will be sent to the player.
        `server_name` The server to connect the player to. If a name is not provided, will connect to all servers.
        """
        try:
            servers = [MinecraftServer.get_from_name(server_name)]
        except ServerNotFound:
            servers = [s for s in MinecraftServer.get_all_instances() if s is not ctx.server]

        if ctx.player not in [s.player for s in self.connections]:
            self.connections.append(BridgeConnection(ctx.server, servers, ctx.player))
        await ctx.send(f"Connected to {', '.join([s.name for s in servers])}")

    @_bridge_command.sub(name="disconnect")
    async def _bridge_player_disconnect(self, ctx: ServerCommandContext) -> None:
        """
        Disconnects a player's bridge connections
        """
        self.connections = list(filter(lambda s: s.player != ctx.player, self.connections))
        await ctx.send("Disconnected from bridge connections")

    @_bridge_command.sub(name="server_connect")
    async def _bridge_server_connect(self, ctx: ServerCommandContext, server_name: Optional[str] = None) -> None:
        """
        Connects the entire server to the other servers.
        All messages sent by all players on the server will be sent to the connected servers.
        All messages sent on connected servers will be forwared to all players on the server.
        `server_name` The server to connect the player to. If a name is not provided, will connect to all servers.
        """
        try:
            servers = [MinecraftServer.get_from_name(server_name)]
        except ServerNotFound:
            servers = [s for s in MinecraftServer.get_all_instances() if s is not ctx.server]

        if ctx.server not in [s.origin_server for s in self.connections]:
            self.connections.append(BridgeConnection(ctx.server, servers))
        await ctx.server.send_message(message=f"Server connected to {', '.join([s.name for s in servers])}", op_only=True)

    @_bridge_command.sub(name="server_disconnect")
    async def _bridge_server_disconnect(self, ctx: ServerCommandContext) -> None:
        """
        Disconnects a server's bridge connections
        """
        self.connections= list(filter(lambda s: s.origin_server != ctx.server, self.connections))
        await ctx.server.send_message(message="Disconnected from bridge connections", op_only=True)

    @server_commands.event(name="message")
    async def _bridge_message(self, ctx: ServerEventContext, message: str) -> None:
        """
        Accesses the message event, which is executed whenever a message is sent on a server.
        Forwards message to all connected bridge servers.

        :param ctx: The context that the event was executed in
        :type ctx: ServerEventContext
        :param message: The message sent
        :type message: str
        """
        for conn in self.connections:
            await conn.send_bridge_message(ctx.server, message)
