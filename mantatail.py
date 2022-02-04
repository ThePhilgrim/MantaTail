"""
Represents the core of the server, with its main functionality and classes.

All communication between server and client is encoded with latin-1.
This ensures compatibility regardless of what encoding is used client-side.
"""

from __future__ import annotations
import socket
import threading
import queue
import fnmatch
import json
from typing import Dict, Optional, List, Set, Tuple

import commands
import irc_responses

TIMER_SECONDS = 600
CAP_LS: List[str] = ["away-notify", "cap-notify"]


class ServerState:
    """Keeps track of existing channels & connected users."""

    def __init__(self, motd_content: Optional[Dict[str, List[str]]]) -> None:
        """
        Attributes:
            - lock: Locks the state of the server to avoid modifications
            to iterables during iteration.

            - chanmodes: These are the channel modes that the server supports.
            Chanmodes are divided into four types (A, B, C, D). It also contains
            "prefix", which are chanmodes set on a user (ex. +o, +v).
            Depending on the channel mode type, they either must take
            a parameter, or they must not.
            More info: https://modern.ircdocs.horse/#channel-mode
        """

        self.lock = threading.Lock()
        self.channels: Dict[str, Channel] = {}
        self.connected_users: Dict[str, UserConnection] = {}
        self.motd_content = motd_content
        # Supported Channel Modes:
        # b: Ban/Unban user from channel
        # o: Set/Unset channel operator
        # t: Only operator can set channel topic
        self.chanmodes: Dict[str, List[str]] = {"A": ["b"], "B": [], "C": [], "D": [], "PREFIX": ["o"]}
        # TODO: Support -t and add "t" to self.chanmodes

    def find_user(self, nick: str) -> Optional[UserConnection]:
        """
        Looks for a connected user and returns its user object.
        Returns None if user doesn't exist.
        """
        try:
            return self.connected_users[nick.lower()]
        except KeyError:
            return None

    def find_channel(self, channel_name: str) -> Optional[Channel]:
        """
        Looks for an existing channel and returns its channel object.
        Returns None if user doesn't exist.
        """
        try:
            return self.channels[channel_name.lower()]
        except KeyError:
            return None

    def delete_user(self, nick: str) -> None:
        """
        Removes a user from all channels they are connected to,
        thereafter removes user from connected users.

        Note: This does not actually disconnect the user from the server.
        To disconnect the user, a tuple (None, disconnect_reason: str) must be put in their send queue.
        """
        user = self.find_user(nick)
        assert user is not None

        for channel in self.channels.values():
            if user in channel.users:
                channel.users.discard(user)
        del self.connected_users[nick.lower()]

    def delete_channel(self, channel_name: str) -> None:
        """
        Removes a channel from server.
        """
        del self.channels[channel_name.lower()]


class ConnectionListener:
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
            print("Got connection from", user_address)
            client_thread = threading.Thread(
                target=CommandReceiver, args=[self.state, user_address[0], user_socket], daemon=True
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


class CommandReceiver:
    """
    Receives commands/messages from the client,
    parses them and sends them to appropriate "handle_" function in the "commands" module.

    IRC Messages are formatted "bytes(COMMAND parameters\r\n)"
    Most IRC clients use "\r\n" line endings, but "\n" is accepted as well (used by e.g. netcat).

    Ex: b"JOIN #foo\r\n"
    Ex: b"PRIVMSG #foo :This is a message\r\n"

    To handle a command FOO, a function named handle_foo() in commands.py is called.
    For example, "PRIVMSG #foo :this is a message\r\n" results in a call like this:

        commands.handle_privmsg(state, user, ["#foo", "this is a message"])
    """

    def __init__(self, state: ServerState, user_host: str, user_socket: socket.socket) -> None:
        self.state = state
        self.user_host = user_host
        self.user_socket = user_socket
        self.user = UserConnection(state, user_host, user_socket)
        self.motd_sent: bool = False
        self.disconnect_reason: str = ""

        self.recv_loop()

    def recv_loop(self) -> None:
        try:
            while True:
                request = self.get_message_request()

                if not request:
                    return  # go to "finally:"

                decoded_command = request.decode("latin-1")
                for line in split_on_new_line(decoded_command)[:-1]:
                    (command, args) = self.parse_received_command(line)
                    command_lower = command.lower()
                    handler_function = "handle_" + command_lower

                    if self.user.nick == "*" or self.user.user_message is None or not self.motd_sent:
                        if command_lower == "user":
                            if args:
                                self.user.user_message = args
                                self.user.user_name = args[0]
                            else:
                                commands.error_not_enough_params(self.user, command)
                        elif command_lower == "nick":
                            commands.handle_nick(self.state, self.user, args)
                        elif command_lower == "pong":
                            commands.handle_pong(self.state, self.user, args)
                        elif command_lower == "cap":
                            commands.handle_cap(self.state, self.user, args)
                        else:
                            if command_lower == "quit":
                                self.disconnect_reason = "Client quit"
                                return
                            else:
                                commands.error_not_registered(self.user)

                        if (
                            self.user.nick != "*"
                            and self.user.user_message is not None
                            and not self.user.capneg_in_progress
                        ):
                            commands.motd(self.state.motd_content, self.user)
                            self.motd_sent = True

                    else:
                        try:
                            # ex. "command.handle_nick" or "command.handle_join"
                            call_handler_function = getattr(commands, handler_function)
                        except AttributeError:
                            commands.error_unknown_command(self.user, command)
                        else:
                            with self.state.lock:
                                call_handler_function(self.state, self.user, args)
                                if command_lower == "quit":
                                    return

        finally:
            self.user.send_que.put((None, self.disconnect_reason))

    def get_message_request(self) -> bytes | None:
        request = b""  # get_message_request
        while not request.endswith(b"\n"):
            self.user.start_ping_timer()
            try:
                request_chunk = self.user_socket.recv(4096)
            except OSError as err:
                self.disconnect_reason = err.strerror
                return None
            finally:
                self.user.ping_timer.cancel()

            if request_chunk:
                request += request_chunk
            else:
                self.disconnect_reason = "Remote host closed the connection"
                return None

        return request

    def parse_received_command(self, msg: str) -> Tuple[str, List[str]]:
        """
        Parses the user command by separating the command (e.g "join", "privmsg", etc.) from the
        arguments.

        If a parameter contains spaces, it must start with ':' to be interpreted as one parameter.
        If the parameter does not start with ':', it will be cut off at the first space.

        Ex:
            - "PRIVMSG #foo :This is a message\r\n" will send "This is a message"
            - "PRIVMSG #foo This is a message\r\n" will send "This"
        """
        split_msg = msg.split(" ")

        for num, arg in enumerate(split_msg):
            if arg.startswith(":"):
                parsed_msg = split_msg[:num]
                parsed_msg.append(" ".join(split_msg[num:])[1:])
                command = parsed_msg[0]
                return command, parsed_msg[1:]

        command = split_msg[0]
        return command, split_msg[1:]


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

        A Tuple containing (None, disconnect_reason: str) indicates a QUIT command and closes the connection to the client.
    """

    def __init__(self, state: ServerState, host: str, socket: socket.socket):
        self.state = state
        self.socket = socket
        self.host = host
        self.nick = "*"
        self.user_message: Optional[List[str]] = None
        self.user_name: Optional[str] = None
        self.away: Optional[str] = None  # None = user not away, str = user away
        self.send_que: queue.Queue[Tuple[str, str] | Tuple[None, str]] = queue.Queue()
        self.que_thread = threading.Thread(target=self.send_queue_thread)
        self.que_thread.start()
        self.cap_list: Set[str] = set()
        self.capneg_in_progress = False
        self.pong_received = False

    def get_user_mask(self) -> str:
        """Generates and returns a user mask (Nick!Username@Host)."""
        return f"{self.nick}!{self.user_name}@{self.host}"

    def get_nick_with_prefix(self, channel: Channel) -> str:
        """
        Returns user nick with appropriate prefix for a specific channel.
        ("@" for channel operator, none for other users).
        """
        if self in channel.operators:
            return f"@{self.nick}"
        else:
            return self.nick

    def send_queue_thread(self) -> None:
        """Queue on which the client receives messages from server."""
        while True:
            (message, prefix) = self.send_que.get()

            if message is None:
                disconnect_reason = prefix
                quit_message = f"QUIT :Quit: {disconnect_reason}"
                with self.state.lock:
                    self.queue_quit_message_for_other_users(quit_message)
                    if self.nick != "*":
                        self.state.delete_user(self.nick)

                try:
                    # Can be slow, if user has bad internet. Don't do this while holding the lock.
                    if self.nick == "*" or not self.user_message:
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
                except OSError as err:
                    disconnect_reason = err.strerror
                    self.send_que.put((None, disconnect_reason))

    def queue_quit_message_for_other_users(self, quit_message: str) -> None:
        """Alerts all other users that the User has QUIT and closed the connection to the server."""
        receivers = self.get_users_sharing_channel()

        for channel in self.state.channels.values():
            channel.operators.discard(self)

        for receiver in receivers:
            receiver.send_que.put((quit_message, self.get_user_mask()))

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
            disconnect_reason = "Ping timeout..."
            self.send_que.put((None, disconnect_reason))
        else:
            self.pong_received = False


class Channel:
    """
    An existing channel on the server.

    Contains all channel-specific actions and modes.
    """

    def __init__(self, channel_name: str, user: UserConnection) -> None:
        self.name = channel_name
        self.topic: Optional[Tuple[str, str]] = None  # (Topic, Topic author)
        self.modes: Set[str] = {"t"}  # See ServerState __init__ for more info on letters.
        self.operators: Set[UserConnection] = set()
        self.users: Set[UserConnection] = set()
        self.ban_list: Dict[str, str] = {}
        self.operators.add(user)

    def set_topic(self, user: UserConnection, topic: str) -> None:
        if not topic:
            self.topic = None
        else:
            self.topic = (topic, user.nick)

    def send_topic_to_user(self, user: UserConnection) -> None:
        topic_num = irc_responses.RPL_TOPIC
        topic_author_num = irc_responses.RPL_TOPICWHOTIME
        (no_topic_num, no_topic_info) = irc_responses.RPL_NOTOPIC

        if self.topic is None:
            message = f"{no_topic_num} {user.nick} {self.name} {no_topic_info}"
            user.send_que.put((message, "mantatail"))
        else:
            topic_message = f"{topic_num} {user.nick} {self.name} :{self.topic[0]}"
            author_message = f"{topic_author_num} {user.nick} {self.name} :{self.topic[1]}"

            user.send_que.put((topic_message, "mantatail"))
            user.send_que.put((author_message, "mantatail"))

    def queue_message_to_chan_users(self, message: str, sender: UserConnection, send_to_self: bool = True) -> None:
        """
        Puts a message in the send queue of all users on the channel.

        In cases where the message should not be sent to self (ex. PRIVMSG), the method
        is called with send_to_self = False.
        """
        for usr in self.users:
            if usr != sender or send_to_self:
                usr.send_que.put((message, sender.get_user_mask()))

    def check_if_banned(self, target: str) -> bool:
        return any(fnmatch.fnmatch(target, ban_mask) for ban_mask in self.ban_list.keys())


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
    ConnectionListener(6667, get_motd_content_from_json()).run_server_forever()
