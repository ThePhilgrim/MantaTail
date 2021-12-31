from __future__ import annotations
import socket
import threading
import json
from typing import Dict, Optional, List

import command


class ServerState:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.channels: Dict[str, Channel] = {}


class Listener:
    def __init__(self, port: int, motd_content: Optional[Dict[str, List[str]]]) -> None:
        self.host = "127.0.0.1"
        self.port = port
        self.motd_content = motd_content
        self.listener_socket = socket.socket()
        self.listener_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.listener_socket.bind((self.host, port))
        self.listener_socket.listen(5)
        self.state = ServerState()

    def run_server_forever(self) -> None:
        print(f"Mantatail running ({self.host}:{self.port})")
        while True:
            (user_socket, user_address) = self.listener_socket.accept()
            client_thread = threading.Thread(
                target=recv_loop,
                args=[self.state, user_address[0], user_socket, self.motd_content],
                daemon=True,
            )
            client_thread.start()


def recv_loop(
    state: ServerState,
    user_host: str,
    user_socket: socket.socket,
    motd_content: Optional[Dict[str, List[str]]],
) -> None:
    _user_message = None
    _nick = None

    user = None

    with user_socket:
        while True:
            request = b""
            # IRC messages always end with b"\r\n" (netcat uses "\n")
            while not request.endswith(b"\n"):
                request_chunk = user_socket.recv(4096)
                if request_chunk:
                    request += request_chunk
                else:
                    if user is not None:
                        print(f"{user.nick} has disconnected.")
                    else:
                        print("Disconnected.")
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
                        _nick = message
                    else:
                        user_socket.sendall(command.error_not_registered())

                    if _user_message and _nick:
                        user = User(user_host, user_socket, _user_message, _nick)
                        command.motd(motd_content, user)

                else:
                    try:
                        # ex. "command.handle_nick" or "command.handle_join"
                        call_handler_function = getattr(command, parsed_command)
                    except AttributeError:
                        command.error_unknown_command(user, verb_lower)
                    else:
                        call_handler_function(state, user, message)

                    if user.closed_connection:
                        return


class User:
    def __init__(self, host: str, socket: socket.socket, user_message: str, nick: str):
        self.socket = socket
        self.host = host
        # Nick is shown in user lists etc, user_name is not
        self.nick = nick
        self.user_message = user_message
        self.user_name = user_message.split(" ", 1)[0]
        self.user_mask = f"{self.nick}!{self.user_name}@{self.host}"
        self.closed_connection = False

    def send_string(self, message: str, prefix: str = "mantatail") -> None:
        message_as_bytes = bytes(f":{prefix} {message}\r\n", encoding="utf-8")
        self.socket.sendall(message_as_bytes)


class Channel:
    def __init__(self, channel_name: str, channel_creator: str) -> None:
        self.name = channel_name
        self.creator = channel_creator
        self.topic = None
        self.user_dict: Dict[Optional[str], User] = {}


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
    Listener(6667, get_motd_content_from_json()).run_forever()
