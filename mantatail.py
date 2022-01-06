from __future__ import annotations
import socket
import threading
import queue
import json
from typing import Dict, Optional, List, Set, Tuple

import command


class ServerState:
    def __init__(self, motd_content: Optional[Dict[str, List[str]]]) -> None:
        self.lock = threading.Lock()
        self.channels: Dict[str, Channel] = {}
        self.connected_users: Dict[str, UserConnection] = {}
        self.motd_content = motd_content

    def find_user(self, nick: str) -> UserConnection:
        return self.connected_users[nick.lower()]

    def find_channel(self, channel_name: str) -> Channel:
        return self.channels[channel_name.lower()]

    def delete_user(self, nick: str) -> None:
        user = self.connected_users[nick.lower()]
        for channel in self.channels.values():
            if user in channel.users:
                channel.users.discard(user)
        del self.connected_users[nick.lower()]

    def delete_channel(self, channel_name: str) -> None:
        del self.channels[channel_name.lower()]


class Listener:
    def __init__(self, port: int, motd_content: Optional[Dict[str, List[str]]]) -> None:
        self.host = "127.0.0.1"
        self.port = port
        self.listener_socket = socket.socket()
        self.listener_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.listener_socket.bind((self.host, port))
        self.listener_socket.listen(5)
        self.state = ServerState(motd_content)

    def run_server_forever(self) -> None:
        print(f"Mantatail running ({self.host}:{self.port})")
        while True:
            (user_socket, user_address) = self.listener_socket.accept()
            client_thread = threading.Thread(
                target=recv_loop, args=[self.state, user_address[0], user_socket], daemon=True
            )
            client_thread.start()


def recv_loop(state: ServerState, user_host: str, user_socket: socket.socket) -> None:
    _user_message = None
    _nick = None

    user = None

    with user_socket:
        while True:
            request = b""
            # IRC messages always end with b"\r\n" (netcat uses "\n")
            while not request.endswith(b"\n"):
                try:
                    request_chunk = user_socket.recv(4096)
                except OSError:
                    user.send_que.put((None, None))  # type: ignore
                    return

                if request_chunk:
                    request += request_chunk
                else:
                    user.send_que.put((None, None))  # type: ignore
                    return

            decoded_message = request.decode("utf-8")
            for line in split_on_new_line(decoded_message)[:-1]:
                if " " in line:
                    (verb, message) = line.split(" ", 1)
                else:
                    verb = line
                    message = verb

                verb_lower = verb.lower()
                parsed_command = "handle_" + verb_lower

                if user is None:
                    if verb_lower == "user":
                        _user_message = message
                    elif verb_lower == "nick":
                        if message.lower() in state.connected_users.keys():
                            user_socket.sendall(command.error_nick_in_use(message))
                        else:
                            _nick = message
                    else:
                        user_socket.sendall(command.error_not_registered())

                    if _user_message and _nick:
                        user = UserConnection(state, user_host, user_socket, _user_message, _nick)
                        state.connected_users[_nick.lower()] = user
                        command.motd(state.motd_content, user)

                else:
                    try:
                        # ex. "command.handle_nick" or "command.handle_join"
                        call_handler_function = getattr(command, parsed_command)
                    except AttributeError:
                        command.error_unknown_command(user, verb_lower)
                    else:
                        with state.lock:
                            call_handler_function(state, user, message)


class UserConnection:
    def __init__(self, state: ServerState, host: str, socket: socket.socket, user_message: str, nick: str):
        self.state = state
        self.send_que: queue.Queue[Tuple[str, str] | Tuple[None, None]] = queue.Queue()
        self.socket = socket
        self.host = host
        # Nick is shown in user lists etc, user_name is not
        self.nick = nick
        self.user_message = user_message
        self.user_name = user_message.split(" ", 1)[0]
        self.user_mask = f"{self.nick}!{self.user_name}@{self.host}"
        self.que_thread = threading.Thread(target=self.start_queue_listener)
        self.que_thread.start()

    def start_queue_listener(self) -> None:
        while True:
            (message, prefix) = self.send_que.get()

            if message is None or prefix is None:
                with self.state.lock:
                    self.send_quit_message()
                    self.state.delete_user(self.nick)
                    self.socket.close()
                print(f"{self.nick} has disconnected.")
                return
            else:
                try:
                    self.send_string_to_client(message, prefix)
                except:
                    self.send_que.put((None, None))

    def send_string_to_client(self, message: str, prefix: str) -> None:
        try:
            message_as_bytes = bytes(f":{prefix} {message}\r\n", encoding="utf-8")

            self.socket.sendall(message_as_bytes)
        except OSError as err:
            print(err)
            return

    def send_quit_message(self) -> None:
        # TODO: Implement logic for different reasons & disconnects.
        reason = "(Remote host closed the connection)"
        message = f"QUIT :Quit: {reason}"

        receivers = set()
        # receivers.add(self)
        for channel in self.state.channels.values():
            if self in channel.users:
                for usr in channel.users:
                    receivers.add(usr)

            if channel.is_operator(self):
                channel.remove_operator(self)

        for receiver in receivers:
            receiver.send_que.put((message, self.user_mask))

        try:
            self.send_string_to_client(message, self.user_mask)
        except OSError:
            return


class Channel:
    def __init__(self, channel_name: str, user: UserConnection) -> None:
        self.name = channel_name
        self.founder = user.user_name
        self.topic = None
        self.modes: List[str] = []
        self.operators: Set[str] = set()
        self.users: Set[UserConnection] = set()

        self.set_operator(user)

    def set_operator(self, user: UserConnection) -> None:
        self.operators.add(user.nick.lower())

    def remove_operator(self, user: UserConnection) -> None:
        self.operators.discard(user.nick.lower())

    def is_operator(self, user: UserConnection) -> bool:
        return user.nick.lower() in self.operators

    def kick_user(self, kicker: UserConnection, user_to_kick: UserConnection, message: str) -> None:
        for usr in self.users:
            usr.send_que.put((message, kicker.user_mask))

        self.users.discard(user_to_kick)


def split_on_new_line(string: str) -> List[str]:
    if string.endswith("\r\n"):
        return string.split("\r\n")
    else:
        return string.split("\n")


def get_motd_content_from_json() -> Optional[Dict[str, List[str]]]:
    try:
        with open("./resources/motd.json", "r") as file:
            motd_content: Dict[str, List[str]] = json.load(file)
            return motd_content
    except FileNotFoundError:
        return None


if __name__ == "__main__":
    Listener(6667, get_motd_content_from_json()).run_server_forever()
