from __future__ import annotations
import time
import socket
import threading
import re
import json
from typing import Dict, Optional, List, Tuple

import irc_responses


class Server:
    def __init__(self, port: int, motd_content: Optional[Dict[str, List[str]]]) -> None:
        print("Starting Mantatail...")
        self.host = "127.0.0.1"
        self.port = port
        self.motd_content = motd_content
        self.listener_socket = socket.socket()
        self.listener_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.listener_socket.bind((self.host, self.port))
        self.listener_socket.listen(5)

        self.channels: Dict[str, Channel] = {}

    def run_server_forever(self) -> None:
        print(f"Mantatail running ({self.host}:{self.port})")
        while True:
            (user_socket, user_address) = self.listener_socket.accept()
            user_info = (user_address[0], user_socket)

            client_thread = threading.Thread(
                target=self.recv_loop, args=[user_info], daemon=True
            )

            client_thread.start()

    def recv_loop(self, user_info: Tuple[str, socket.socket]) -> None:

        user_host = user_info[0]
        user_socket = user_info[1]
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
                        (
                            verb,
                            message,
                        ) = line.split(" ", 1)
                    else:
                        verb = line
                        message = verb

                    verb_lower = verb.lower()

                    # ex. "handle_nick" or "handle_join"
                    handler_function_to_call = "handle_" + verb_lower

                    if user is None:
                        if verb_lower == "user":
                            _user_message = message
                        elif verb_lower == "nick":
                            _nick = message
                        else:
                            (error_code, error_info) = irc_responses.ERR_NOTREGISTERED
                            user_socket.sendall(
                                bytes(
                                    f":mantatail {error_code} * {error_info}\r\n",
                                    encoding="utf-8",
                                )
                            )

                        if _user_message and _nick:
                            user = User(user_host, user_socket, _user_message, _nick)
                            command_handler: IrcCommandHandler = IrcCommandHandler(
                                self, user
                            )
                            command_handler.handle_motd()

                    else:
                        try:
                            call_handler_function = getattr(
                                command_handler, handler_function_to_call
                            )
                        except AttributeError:
                            command_handler.handle_unknown_command(verb_lower)
                            return

                        call_handler_function(message)
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


class Channel:
    def __init__(self, channel_name: str, channel_creator: str) -> None:
        self.name = channel_name
        self.creator = channel_creator
        self.topic = None
        self.user_dict: Dict[Optional[str], User] = {}


class IrcCommandHandler:
    def __init__(self, server: Server, user: User) -> None:
        self.encoding = "utf-8"
        self.send_to_client_prefix = ":mantatail"
        self.send_to_client_suffix = "\r\n"
        self.server = server
        self.user = user

    def handle_motd(self) -> None:
        (start_num, start_info) = irc_responses.RPL_MOTDSTART
        motd_num = irc_responses.RPL_MOTD
        (end_num, end_info) = irc_responses.RPL_ENDOFMOTD

        motd_start_and_end = {
            "start_msg": f"{self.send_to_client_prefix} {start_num} {self.user.nick} :- mantatail {start_info}{self.send_to_client_suffix}",
            "end_msg": f"{self.send_to_client_prefix} {end_num} {self.user.nick} {end_info}{self.send_to_client_suffix}",
        }

        start_msg = bytes(motd_start_and_end["start_msg"], encoding=self.encoding)
        end_msg = bytes(motd_start_and_end["end_msg"], encoding=self.encoding)

        self.user.socket.sendall(start_msg)

        if self.server.motd_content:
            motd = self.server.motd_content["motd"]
            for motd_line in motd:
                motd_msg = bytes(
                    f"{self.send_to_client_prefix} {motd_num} {self.user.nick} :{motd_line.format(user_nick=self.user.nick)}{self.send_to_client_suffix}",
                    encoding=self.encoding,
                )
                self.user.socket.sendall(motd_msg)
        # If motd.json could not be found
        else:
            (no_motd_num, no_motd_info) = irc_responses.ERR_NOMOTD
            self.user.socket.sendall(
                bytes(
                    f"{self.send_to_client_prefix} {no_motd_num} {no_motd_info}{self.send_to_client_suffix}",
                    encoding=self.encoding,
                )
            )

        self.user.socket.sendall(end_msg)

    def handle_join(self, channel_name: str) -> None:
        channel_regex = r"#[^ \x07,]{1,49}"  # TODO: Make more restrictive (currently valid: ###, #ö?!~ etc)

        lower_channel_name = channel_name.lower()

        if not re.match(channel_regex, lower_channel_name):
            self.handle_no_such_channel(channel_name)
        else:
            if lower_channel_name not in self.server.channels.keys():
                self.server.channels[lower_channel_name] = Channel(
                    channel_name, self.user.nick
                )

            lower_user_nick = self.user.nick.lower()

            if (
                lower_user_nick
                not in self.server.channels[lower_channel_name].user_dict.keys()
            ):

                channel_user_keys = self.server.channels[
                    lower_channel_name
                ].user_dict.keys()
                channel_users = " ".join(
                    [
                        self.server.channels[lower_channel_name]
                        .user_dict[user_key]
                        .nick
                        for user_key in channel_user_keys
                    ]
                )

                self.server.channels[lower_channel_name].user_dict[
                    lower_user_nick
                ] = self.user
                for user in channel_user_keys:
                    self.server.channels[lower_channel_name].user_dict[
                        user
                    ].socket.sendall(
                        bytes(
                            f":{self.user.user_mask} JOIN {channel_name}{self.send_to_client_suffix}",
                            encoding=self.encoding,
                        )
                    )

                # TODO: Implement topic functionality for existing channels & MODE for new ones

                self.user.socket.sendall(
                    bytes(
                        f"{self.send_to_client_prefix} 353 {self.user.nick} = {channel_name} :{self.user.nick} {channel_users}{self.send_to_client_suffix}",
                        encoding=self.encoding,
                    )
                )
                self.user.socket.sendall(
                    bytes(
                        f"{self.send_to_client_prefix} 366 {self.user.nick} {channel_name} :End of /NAMES list.{self.send_to_client_suffix}",
                        encoding=self.encoding,
                    )
                )

        # TODO:
        #   * Send topic (332)
        #   * Optional/Later: (333) https://modern.ircdocs.horse/#rpltopicwhotime-333
        #   * Send Name list (353)
        #   * Send End of Name list (366)

        # TODO: Check for:
        #   * User invited to channel
        #   * Nick/user not matching bans
        #   * Eventual password matches
        #   * Not joined too many channels

        # TODO:
        #   * Forward to another channel (irc num 470) ex. #homebrew -> ##homebrew

    def handle_part(self, channel_name: str) -> None:
        lower_channel_name = channel_name.lower()
        lower_user_nick = self.user.nick.lower()
        if lower_channel_name not in self.server.channels.keys():
            self.handle_no_such_channel(channel_name)
        elif (
            lower_user_nick
            not in self.server.channels[lower_channel_name].user_dict.keys()
        ):
            (not_on_channel_num, not_on_channel_info) = irc_responses.ERR_NOTONCHANNEL

            self.generate_error_reply(
                not_on_channel_num, not_on_channel_info, channel_name
            )
        else:
            del self.server.channels[lower_channel_name].user_dict[lower_user_nick]
            if len(self.server.channels[lower_channel_name].user_dict) == 0:
                del self.server.channels[lower_channel_name]

    def handle_quit(self, message: str) -> None:
        self.user.closed_connection = True
        self.user.socket.close()

    def _handle_kick(self, message: str) -> None:
        pass

    def _handle_privmsg(self, message: str) -> None:
        pass

    def handle_unknown_command(self, command: str) -> None:
        (unknown_cmd_num, unknown_cmd_info) = irc_responses.ERR_UNKNOWNCOMMAND

        self.generate_error_reply(unknown_cmd_num, unknown_cmd_info, command)

    def handle_no_such_channel(self, channel_name: str) -> None:
        (no_channel_num, no_channel_info) = irc_responses.ERR_NOSUCHCHANNEL
        self.generate_error_reply(no_channel_num, no_channel_info, channel_name)

    def generate_error_reply(
        self, error_num: str, error_info: str, error_topic: str
    ) -> None:
        self.user.socket.sendall(
            bytes(
                f"{self.send_to_client_prefix} {error_num} {error_topic} {error_info}{self.send_to_client_suffix}",
                encoding=self.encoding,
            )
        )


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
    motd_content = get_motd_content_from_json()
    server = Server(6667, motd_content)
    server.run_server_forever()
