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
from datetime import datetime
from typing import Dict, Optional, List, Set, Tuple

import commands, errors

MANTATAIL_VERSION = "0.0.1"
SERVER_STARTED = datetime.today().ctime()
PING_TIMER_SECS = 300
CAP_LS: List[str] = ["away-notify", "cap-notify"]
ISUPPORT = {"NICKLEN": "16", "PREFIX": "(o)@", "CHANTYPES": "#", "TARGMAX": "PRIVMSG:1,JOIN:1,PART:1,KICK:1"}


class State:
    """Keeps track of existing channels & connected users."""

    def __init__(self, motd_content: Optional[Dict[str, List[str]]], port: int) -> None:
        """
        Attributes:
            - lock: Locks the state of the server to avoid modifications
            to iterables during iteration.

            - supported_modes: These are the channel and user modes that the server supports.
            Modes are divided into four types (A, B, C, D). Depending on the mode type,
            they either must take a parameter, or they must not.

            - Channel modes are set on channels to modify their functionality.
            - User modes are set on users to change how they are affected by different
            commands and features. All user modes are of type D (they never take a parameter).

            supported_modes also contains "prefix", which are channel modes set on a user (ex. +o, +v).

            More info:
                https://modern.ircdocs.horse/#channel-mode
                https://modern.ircdocs.horse/#user-modes
        """

        self.lock = threading.Lock()
        self.channels: Dict[str, Channel] = {}
        self.connected_users: Dict[str, UserConnection] = {}
        self.port = port
        self.motd_content = motd_content
        # Supported Modes:
        # b: Ban/Unban user from channel (channel)
        # i: Make user invisible, and hide them from e.g WHO, NAMES commands.
        # o: Set/Unset channel operator (channel)
        # t: Only operator can set channel topic (channel)

        self.supported_modes: Dict[str, List[str]] = {"A": ["b"], "B": [], "C": [], "D": ["i"], "PREFIX": ["o"]}
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
        self.host = ""
        self.port = port
        self.listener_socket = socket.socket()
        self.listener_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.listener_socket.bind((self.host, port))
        self.listener_socket.listen(5)
        self.state = State(motd_content, self.port)

    def run_server_forever(self) -> None:
        """
        Accepts incoming connections from clients.
        Starts a separate thread to handle each connection.
        """
        print(f"Mantatail running (port {self.port})")
        while True:
            (user_socket, user_address) = self.listener_socket.accept()
            print("Got connection from", user_address)
            client_thread = threading.Thread(
                target=CommandReceiver, args=[self.state, user_address[0], user_socket], daemon=True
            )
            client_thread.start()


class CommandReceiver:
    """
    Receives commands/messages from the client, parses them, and sends them to the appropriate
    handler function.

    IRC Messages are formatted "bytes(COMMAND parameters\r\n)"
    Most IRC clients use "\r\n" line endings, but "\n" is accepted as well (used by e.g. netcat).

    Ex: b"JOIN #foo\r\n"
    Ex: b"PRIVMSG #foo :This is a message\r\n"
    """

    def __init__(self, state: State, user_host: str, user_socket: socket.socket) -> None:
        self.state = state
        self.user_host = user_host
        self.user_socket = user_socket
        self.user = UserConnection(state, user_host, user_socket)
        self.disconnect_reason: str = ""

        self.recv_loop()

    def recv_loop(self) -> None:
        """
        Parses incoming messages from the client and sends them to the appropriate
        "handle_" function.

        To handle a command FOO, a function named handle_foo() in commands.py is called.
        For example, "PRIVMSG #foo :this is a message\r\n" results in a call like this:

        commands.handle_privmsg(state, user, ["#foo", "this is a message"])

        The function call is done with getattr().
        getattr(commands, "handle_join") is equivalent to commands.handle_join.
        More info: https://docs.python.org/3/library/functions.html#getattr
        """

        try:
            while True:
                request = self.receive_messages()

                if request is None:
                    return  # go to "finally:"

                decoded_command = request.decode("latin-1")
                for line in split_on_new_line(decoded_command)[:-1]:
                    (command, args) = self.parse_received_command(line)
                    command_lower = command.lower()
                    handler_function = "handle_" + command_lower

                    if self.user.nick == "*" or self.user.user_message is None or not self.user.motd_sent:
                        if command_lower == "quit":
                            self.disconnect_reason = "Client quit"
                            return  # go to "finally:"
                        else:
                            self.handle_user_registration(command_lower, args)

                        if (
                            self.user.nick != "*"
                            and self.user.user_message is not None
                            and not self.user.capneg_in_progress
                        ):
                            self.user.on_registration()

                    else:
                        try:
                            # ex. "command.handle_nick" or "command.handle_join"
                            call_handler_function = getattr(commands, handler_function)
                        except AttributeError:
                            errors.unknown_command(self.user, command)
                        else:
                            with self.state.lock:
                                call_handler_function(self.state, self.user, args)
                                if command_lower == "quit":
                                    return

        finally:
            self.user.send_que.put((None, self.disconnect_reason))

    def receive_messages(self) -> bytes | None:
        """
        Receives one or more lines from the client as bytes and returns them to recv_loop().

        It will receive until the received bytes end with "\n", which indicates that everything
        the client has currently sent has been received.

        None is returned if the user disconnects.

        Also starts the user's ping timer, which will send a PING message to the client
        after a certain time of inactivity.
        The PING message controls that the user still has an open connection to the server.
        """
        request = b""
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

    def handle_user_registration(self, command: str, args: List[str]) -> None:
        """
        Parses messages from the client before they have registered (provided the server
        with their nickname (NICK) and username (USER)).

        This limits what commands the user can send before registering.
        """
        if command == "user":
            if args:
                self.user.user_message = args
                self.user.user_name = args[0]
            else:
                errors.not_enough_params(self.user, command.upper())
        elif command == "nick":
            commands.handle_nick(self.state, self.user, args)
        elif command == "pong":
            commands.handle_pong(self.state, self.user, args)
        elif command == "cap":
            commands.handle_cap(self.state, self.user, args)
        else:
            errors.not_registered(self.user)


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

    def __init__(self, state: State, host: str, socket: socket.socket):
        self.state = state
        self.socket = socket
        self.host = host
        self.nick = "*"
        self.user_message: Optional[List[str]] = None
        self.user_name: Optional[str] = None
        self.modes = {"i"}
        self.away: Optional[str] = None  # None = user not away, str = user away
        self.send_que: queue.Queue[Tuple[str, str] | Tuple[None, str]] = queue.Queue()
        self.que_thread = threading.Thread(target=self.send_queue_thread)
        self.que_thread.start()
        self.cap_list: Set[str] = set()
        self.motd_sent = False
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

    def on_registration(self) -> None:
        """
        After a user has registered on the server by providing a nickname (NICK) and a username (USER),
        several messages are sent to the client with information about the server.
        """
        commands.rpl_welcome(self)
        commands.rpl_yourhost(self, self.state)
        commands.rpl_created(self)
        commands.rpl_myinfo(self, self.state)
        commands.rpl_isupport(self)
        commands.motd(self.state.motd_content, self)
        self.motd_sent = True

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
        """Returns all users of all channels that this user has joined."""
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
        self.ping_timer = threading.Timer(PING_TIMER_SECS, self.queue_ping_message)
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
        self.modes: Set[str] = {"t"}  # See State __init__ for more info on letters.
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
        if self.topic is None:
            message = f"331 {user.nick} {self.name} :No topic is set."
            user.send_que.put((message, "mantatail"))
        else:
            topic_message = f"332 {user.nick} {self.name} :{self.topic[0]}"
            author_message = f"333 {user.nick} {self.name} :{self.topic[1]}"

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
        """
        Checks if the user mask provided in a MODE +b (ban) command matches a
        user mask that is already in the channel's ban list.

        Wildcards "*" are used to cover any set of characters.
        Ex. If the ban list contains "*!Bar@Baz", "Foo!Bar@Baz" will be considered a match.
        """
        return any(fnmatch.fnmatch(target, ban_mask) for ban_mask in self.ban_list.keys())


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
