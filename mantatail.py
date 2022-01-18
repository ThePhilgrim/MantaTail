"""
Represents the core of the server, with its main functionality and classes.
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
    """
    Represents the current state of the Server.
    Keeps track of existing channels & connected users.
    """

    def __init__(self, motd_content: Optional[Dict[str, List[str]]]) -> None:
        self.lock = threading.Lock()
        self.channels: Dict[str, Channel] = {}
        self.connected_users: Dict[str, UserConnection] = {}
        self.motd_content = motd_content

    def find_user(self, nick: str) -> UserConnection:
        """Looks for a connected user and returns the UserConnection object corresponding to that user."""
        return self.connected_users[nick.lower()]

    def find_channel(self, channel_name: str) -> Channel:
        """Looks for an existing channel and returns the Channel object corresponding to that channel."""
        return self.channels[channel_name.lower()]

    def delete_user(self, nick: str) -> None:
        """
        Removes a user from all channels of which the user is connected to,
        thereafter removes user from dict of connected users.
        """
        user = self.connected_users[nick.lower()]
        for channel in self.channels.values():
            if user in channel.users:
                channel.users.discard(user)
        del self.connected_users[nick.lower()]

    def delete_channel(self, channel_name: str) -> None:
        """Removes channel from dict of existing channels."""
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
        Starts a receive loop on a separate thread,
        listening for incoming commands from client.
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
    Ensures that the connection to a client is closed cleanly without errors.

    The code is based on this blog post:
    https://blog.netherlabs.nl/articles/2009/01/18/the-ultimate-so_linger-page-or-why-is-my-tcp-not-reliable

    Args:
        sock: Client socket

    Raises:
        OSError:
            Possible causes:
            - Client decided to keep its connection open for more than 10sec.
            - Client was already disconnected.
            - Probably something else too that I didn't think of...
    """
    try:
        sock.shutdown(socket.SHUT_WR)
        sock.settimeout(10)
        sock.recv(1)  # Wait for client to close the connection
    except OSError:
        pass

    sock.close()


def recv_loop(state: ServerState, user_host: str, user_socket: socket.socket) -> None:
    """
    Instantiates UserConnection and listens for commands/messages from the client,
    parses them and sends them to appropriate "handle_" function in "commands".

    IRC Messages are formatted "bytes(COMMAND args\r\n)"
    Ex: b"JOIN #foo\r\n"
    Ex: b"PRIVMSG #foo :This is a message\r\n"

    Note that netcat uses "\n" in place of "\r\n".

    Args:
        user_host: Client IP address
        user_socket: Client socket
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
                        if args[0].lower() in state.connected_users.keys():
                            commands.error_nick_in_use(user, args[0])
                        else:
                            user.nick = args[0]
                            state.connected_users[user.nick.lower()] = user
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
    Starts a Queue on a separate thread on which the client receives all messages from the server.

    Format examples:
    - Nick: Alice
    - User message: AliceUsr 0 * Alice's Real Name
    - Username: AliceUsr
    - User Mask Alice!AliceUsr@127.0.0.1 (Nick!Username@Host)

    All references to UserConnection (lists, dicts, etc.) are based on Nick.
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
        return f"{self.nick}!{self.user_name}@{self.host}"

    def send_queue_thread(self) -> None:
        """
        Queue on which the client receives messages from server.

        All messages are a Tuple formatted as (message, prefix).
        Prefixes are either ":mantatail" or "sender.user_mask"

        A Tuple containing (None, None) indicates a QUIT and closes the connection to the client.
        """
        while True:
            (message, prefix) = self.send_que.get()

            # (None, None) disconnects the user
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

        receivers = set()
        for channel in self.state.channels.values():
            if self in channel.users:
                for usr in channel.users:
                    if usr != self:
                        receivers.add(usr)

            if channel.is_operator(self):
                channel.remove_operator(self)

        for receiver in receivers:
            receiver.send_que.put((message, self.get_user_mask()))

    def send_string_to_client(self, message: str, prefix: Optional[str]) -> None:
        """
        Takes the message and prefix sent from the server through self.send_que as strings,
        converts the formatted message to bytes and sends it to the client.
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
        Starts a timer on a separate thread that when finished sends a PING message to the client
        to establish that the client still has an open connection to the server.
        """
        self.ping_timer = threading.Timer(TIMER_SECONDS, self.queue_ping_message)
        self.ping_timer.start()

    def queue_ping_message(self) -> None:
        """
        Puts PING message in the client's Queue, and starts a new timer waiting for the
        expected PONG response from the client.

        Ex:
        Sends ":mantatail PING :mantatail"
        Expected response: ":Alice!AliceUsr@127.0.0.1 PONG :mantatail"
        """
        self.send_que.put(("PING :mantatail", "mantatail"))
        threading.Timer(5, self.assert_pong_received).start()

    def assert_pong_received(self) -> None:
        """
        Uses self.pong_received to assert if the client has sent an appropriate
        PONG response to the server's PING message.

        If no PONG response has been received, the server closes the connection to the client.
        """
        if not self.pong_received:
            self.send_que.put((None, None))
        else:
            self.pong_received = False


class Channel:
    """
    Represents an existing channel on the server.
    """

    def __init__(self, channel_name: str, user: UserConnection) -> None:
        self.name = channel_name
        self.founder = user.user_name
        self.topic = None
        self.modes: List[str] = []
        self.operators: Set[str] = set()
        self.users: Set[UserConnection] = set()

        self.set_operator(user)

    def set_operator(self, user: UserConnection) -> None:
        """
        Takes a UserConnection object as an argument and adds the user's
        Nick to the channel's operators.
        """
        self.operators.add(user.nick.lower())

    def remove_operator(self, user: UserConnection) -> None:
        """
        Takes a UserConnection object as an argument and removes the user's
        Nick from the channel's operators.
        """
        self.operators.discard(user.nick.lower())

    def is_operator(self, user: UserConnection) -> bool:
        """
        Takes a UserConnection object as an argument and checks if the user's
        Nick is a channel operator.

        Returns a Boolean.
        """
        return user.nick.lower() in self.operators

    def kick_user(self, kicker: UserConnection, user_to_kick: UserConnection, message: str) -> None:
        """
        Puts a KICK message in the channel users' Queues notifying them that
        an operator has kicked a user from the channel.

        Thereafter removes the kicked user from the channel's user Set.
        """
        for usr in self.users:
            usr.send_que.put((message, kicker.get_user_mask()))

        self.users.discard(user_to_kick)


def split_on_new_line(string: str) -> List[str]:
    """
    Takes string as an argument and splits it on "\r\n" or "\n".

    Returns a List of strings.
    """
    if string.endswith("\r\n"):
        return string.split("\r\n")
    else:
        return string.split("\n")


def get_motd_content_from_json() -> Optional[Dict[str, List[str]]]:
    """
    Fetches the server's Message of the Day from 'motd.json'.

    Returns Dict ("String": List)
    """
    try:
        with open("./resources/motd.json", "r") as file:
            motd_content: Dict[str, List[str]] = json.load(file)
            return motd_content
    except FileNotFoundError:
        return None


if __name__ == "__main__":
    Listener(6667, get_motd_content_from_json()).run_server_forever()
