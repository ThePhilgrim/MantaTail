"""
Represents the core of the server, with its main functionality and classes.

All communication between server and client is encoded with latin-1.
This ensures compatibility regardless of what encoding is used client-side.
"""

from __future__ import annotations
import socket
import threading
import queue
import json
from typing import Dict, Optional, List, Set, Tuple

import commands

# Global so that it can be accessed from pytest
TIMER_SECONDS = 600


class ServerState:
    """Keeps track of existing channels & connected users."""

    def __init__(self, motd_content: Optional[Dict[str, List[str]]]) -> None:
        """
        The attribute "self.lock" locks the state of the server to avoid modifications
        to iterables during iteration.
        """

        self.lock = threading.Lock()
        self.channels: Dict[str, Channel] = {}
        self.connected_users: Dict[str, UserConnection] = {}
        self.motd_content = motd_content

    def find_user(self, nick: str) -> UserConnection:
        """Looks for a connected user and returns its user object."""
        return self.connected_users[nick.lower()]

    def find_channel(self, channel_name: str) -> Channel:
        """Looks for an existing channel and returns its channel object."""
        return self.channels[channel_name.lower()]

    def delete_user(self, nick: str) -> None:
        """
        Removes a user from all channels they are connected to,
        thereafter removes user from connected users.

        Note: This does not actually disconnect the user from the server.
        To disconnect the user, a tuple (None, None) must be put in their send queue.
        """
        user = self.connected_users[nick.lower()]
        for channel in self.channels.values():
            if user in channel.users:
                channel.users.discard(user)
        del self.connected_users[nick.lower()]

    def delete_channel(self, channel_name: str) -> None:
        """Removes a channel from server."""
        del self.channels[channel_name.lower()]


class Listener:
    """Starts the server and listens for incoming connections from clients."""

    def __init__(self, port: int, motd_content: Optional[Dict[str, List[str]]]) -> None:
        self.host = "127.0.0.1"
        self.port = port
        self.listener_socket = socket.socket()
        self.listener_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.listener_socket.bind((self.host, port))
        self.listener_socket.listen(5)
        self.state = ServerState(motd_content)

    def run_server_forever(self) -> None:
        """
        Accepts incoming connections from clients.
        Starts a separate thread to handle each connection.
        """
        print(f"Mantatail running ({self.host}:{self.port})")
        while True:
            (user_socket, user_address) = self.listener_socket.accept()
            client_thread = threading.Thread(
                target=recv_loop, args=[self.state, user_address[0], user_socket], daemon=True
            )
            client_thread.start()


def close_socket_cleanly(sock: socket.socket) -> None:
    """
    Ensures that the connection to a client is closed cleanly without errors and with no data loss.

    Use this instead of the .close() method.
    """
    # The code is based on this blog post:
    # https://blog.netherlabs.nl/articles/2009/01/18/the-ultimate-so_linger-page-or-why-is-my-tcp-not-reliable
    try:
        sock.shutdown(socket.SHUT_WR)
        sock.settimeout(10)
        sock.recv(1)  # Wait for client to close the connection
    except OSError:
        # Possible causes:
        # - Client decided to keep its connection open for more than 10sec.
        # - Client was already disconnected.
        # - Probably something else too that I didn't think of...
        pass

    sock.close()


def recv_loop(state: ServerState, user_host: str, user_socket: socket.socket) -> None:
    """
    Receives commands/messages from the client,
    parses them and sends them to appropriate "handle_" function in "commands".

    IRC Messages are formatted "bytes(COMMAND parameters\r\n)"
    Most IRC clients use "\r\n" line endings, but "\n" is accepted as well (used by e.g. netcat).

    Ex: b"JOIN #foo\r\n"
    Ex: b"PRIVMSG #foo :This is a message\r\n"

    To handle a command FOO, a function named handle_foo() in commands.py is called.
    For example, "PRIVMSG #foo :this is a message\r\n" results in a call like this:

        commands.handle_privmsg(state, user, ["#foo", "this is a message"])
    """

    user = UserConnection(state, user_host, user_socket)

    try:
        while True:
            request = b""
            while not request.endswith(b"\n"):
                user.start_ping_timer()
                try:
                    request_chunk = user_socket.recv(4096)
                except OSError:
                    return  # go to "finally:"
                finally:
                    user.ping_timer.cancel()

                if request_chunk:
                    request += request_chunk
                else:
                    return  # go to "finally:"

            decoded_message = request.decode("latin-1")
            for line in split_on_new_line(decoded_message)[:-1]:
                command, args = commands.parse_received_args(line)
                command_lower = command.lower()
                parsed_command = "handle_" + command_lower

                if not hasattr(user, "nick") or not user.user_message:
                    if command_lower == "user":
                        user.user_message = args
                        user.user_name = args[0]
                    elif command_lower == "nick":
                        commands.handle_nick(state, user, args)
                    elif command_lower == "pong":
                        commands.handle_pong(state, user, args)
                    else:
                        if command_lower == "quit":
                            user.send_que.put((None, None))
                        else:
                            commands.error_not_registered(user)

                    if hasattr(user, "nick") and user.user_message:
                        commands.motd(state.motd_content, user)

                else:
                    try:
                        # ex. "command.handle_nick" or "command.handle_join"
                        call_handler_function = getattr(commands, parsed_command)
                    except AttributeError:
                        commands.error_unknown_command(user, command)
                    else:
                        with state.lock:
                            call_handler_function(state, user, args)
    finally:
        user.send_que.put((None, None))


class UserConnection:
    """
    Represents the connection between server & client.

    Format examples:
    - Nick: Alice
    - User message: AliceUsr 0 * Alice's Real Name
    - Username: AliceUsr
    - User Mask Alice!AliceUsr@127.0.0.1 (Nick!Username@Host)

    Usually the nick is used when referring to the user.

    Send Queue:
        A send queue and a separate thread are used for sending messages to the client.
        This helps with error handling, and even if someone has a slow internet connection,
        other people don't have to wait when a message is sent to several users with a loop.

        All messages are sent as a tuple formatted as (message, prefix).
        Prefixes are either ":mantatail" or ":sender.user_mask"

        A Tuple containing (None, None) indicates a QUIT command and closes the connection to the client.
    """

    # self.nick is defined in recv_loop()
    # It is not set in __init__ to keep mypy happy.
    nick: str  # Nick is shown in user lists etc, user_name is not

    def __init__(self, state: ServerState, host: str, socket: socket.socket):
        self.state = state
        self.socket = socket
        self.host = host
        self.user_message: Optional[List[str]] = None  # Ex. AliceUsr 0 * Alice
        self.user_name: Optional[str] = None  # Ex. AliceUsr
        self.send_que: queue.Queue[Tuple[str, str] | Tuple[None, None]] = queue.Queue()
        self.que_thread = threading.Thread(target=self.send_queue_thread)
        self.que_thread.start()
        self.pong_received = False

    def get_user_mask(self) -> str:
        """Generates and returns a user mask (Nick!Username@Host)."""
        return f"{self.nick}!{self.user_name}@{self.host}"

    def get_nick_with_prefix(self, channel: Channel) -> str:
        """
        Returns user nick with appropriate prefix for a specific channel.
        ("~" for channel founder, "@" for channel operator).
        """
        if channel.is_founder(self):
            return f"~{self.nick}"
        elif channel.is_operator(self):
            return f"@{self.nick}"
        else:
            return self.nick

    def send_queue_thread(self) -> None:
        """Queue on which the client receives messages from server."""
        while True:
            (message, prefix) = self.send_que.get()

            if message is None or prefix is None:
                with self.state.lock:
                    self.queue_quit_message_for_other_users()
                    if hasattr(self, "nick"):
                        self.state.delete_user(self.nick)

                try:
                    reason = "(Remote host closed the connection)"
                    quit_message = f"QUIT :Quit: {reason}"
                    # Can be slow, if user has bad internet. Don't do this while holding the lock.
                    if not hasattr(self, "nick") or not self.user_message:
                        self.send_string_to_client(quit_message, None)
                    else:
                        self.send_string_to_client(quit_message, self.get_user_mask())
                except OSError:
                    pass

                close_socket_cleanly(self.socket)
                return
            else:
                try:
                    self.send_string_to_client(message, prefix)
                except:
                    self.send_que.put((None, None))

    def queue_quit_message_for_other_users(self) -> None:
        """Alerts all other users that the User has QUIT and closed the connection to the server."""
        # TODO: Implement logic for different reasons & disconnects.
        reason = "(Remote host closed the connection)"
        message = f"QUIT :Quit: {reason}"

        receivers = self.get_users_sharing_channel()

        for channel in self.state.channels.values():
            if channel.is_operator(self):
                channel.remove_operator(self)

        for receiver in receivers:
            receiver.send_que.put((message, self.get_user_mask()))

    def get_users_sharing_channel(self) -> Set[UserConnection]:
        receivers = set()
        for channel in self.state.channels.values():
            if self in channel.users:
                for usr in channel.users:
                    if usr != self:
                        receivers.add(usr)
        return receivers

    def send_string_to_client(self, message: str, prefix: Optional[str]) -> None:
        """
        Send a string to the client, without using the send queue.

        In most cases, you should put a message to the send queue instead of using this method directly.
        """
        try:
            if prefix is None:
                message_as_bytes = bytes(f":{message}\r\n", encoding="latin-1")
            else:
                message_as_bytes = bytes(f":{prefix} {message}\r\n", encoding="latin-1")

            self.socket.sendall(message_as_bytes)
        except OSError:
            return

    def start_ping_timer(self) -> None:
        """
        Starts a timer on a separate thread that, when finished, sends a PING message to the client
        to establish that the client still has an open connection to the server.
        """
        self.ping_timer = threading.Timer(TIMER_SECONDS, self.queue_ping_message)
        self.ping_timer.start()

    def queue_ping_message(self) -> None:
        """
        Puts a PING message in the client's send queue, and starts a new timer waiting for the
        expected PONG response from the client.

        This is done to control that the client still has an open connection to the server.

        Ex:
        Sends ":mantatail PING :mantatail"
        Expected response: ":Alice!AliceUsr@127.0.0.1 PONG :mantatail"
        """
        self.send_que.put(("PING :mantatail", "mantatail"))
        threading.Timer(5, self.assert_pong_received).start()

    def assert_pong_received(self) -> None:
        """
        Checks if the client has sent a PONG response to the server's PING message.

        If no PONG response has been received, the server closes the connection to the client.
        """
        if not self.pong_received:
            self.send_que.put((None, None))
        else:
            self.pong_received = False


class Channel:
    """
    An existing channel on the server.

    Contains all channel-specific actions and modes.
    """

    def __init__(self, channel_name: str, user: UserConnection) -> None:
        self.name = channel_name
        self.founder = user.user_name
        self.topic = None
        self.modes: List[str] = []
        self.operators: Set[UserConnection] = set()
        self.users: Set[UserConnection] = set()

        self.set_operator(user)

    def set_operator(self, user: UserConnection) -> None:
        """Adds a user to the channel's operators."""
        self.operators.add(user)

    def remove_operator(self, user: UserConnection) -> None:
        """Removes a user from the channel's operators."""
        self.operators.discard(user)

    def is_founder(self, user: UserConnection) -> bool:
        """Checks if the user is the channel founder."""
        return user.user_name == self.founder

    def is_operator(self, user: UserConnection) -> bool:
        """Checks if a user is an operator on the channel."""
        return user in self.operators

    def kick_user(self, kicker: UserConnection, user_to_kick: UserConnection, message: str) -> None:
        """
        Notifies all users on the channel that a user has been kicked.
        Thereafter removes the kicked user from the channel.
        """
        for usr in self.users:
            usr.send_que.put((message, kicker.get_user_mask()))

        self.users.discard(user_to_kick)


def split_on_new_line(string: str) -> List[str]:
    """Splits a message received by a client on "\r\n" (most IRC clients) or "\n" (e.g. Netcat)."""
    if string.endswith("\r\n"):
        return string.split("\r\n")
    else:
        return string.split("\n")


def get_motd_content_from_json() -> Optional[Dict[str, List[str]]]:
    """Loads the Message of the Day file.

    Returns None if the file is not found.
    """
    try:
        with open("./resources/motd.json", "r") as file:
            motd_content: Dict[str, List[str]] = json.load(file)
            return motd_content
    except FileNotFoundError:
        return None


if __name__ == "__main__":
    Listener(6667, get_motd_content_from_json()).run_server_forever()
