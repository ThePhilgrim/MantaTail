from io import open_code
import socket
import threading
import re
import json
import sys


try:
    # https://datatracker.ietf.org/doc/html/rfc1459#section-6.2
    with open("./resources/irc_response_nums.json", "r") as file:
        irc_response_nums = json.load(file)
except FileNotFoundError:
    sys.exit("FileNotFoundError: Missing resources/irc_response_nums.json")


class User:
    def __init__(self, host, socket):
        self.socket = socket
        self.host = host
        self.nick = None
        self.user_name = None

    def create_user_mask(self):
        return f"{self.nick}!{self.user_name}@{self.host}"


class Channel:
    def __init__(self):
        self.user_list = {}


class IrcCommandHandler:
    def __init__(self, server, user):
        self.encoding = "utf-8"
        self.send_to_client_prefix = ":mantatail"
        self.send_to_client_suffix = "\r\n"
        self.server = server
        self.user = user

    def handle_motd(self):
        start_num, start_info = (
            irc_response_nums["command_responses"]["RPL_MOTDSTART"][0],
            irc_response_nums["command_responses"]["RPL_MOTDSTART"][1].replace(
                "<server>", "mantatail"
            ),
        )
        motd_num = irc_response_nums["command_responses"]["RPL_MOTD"][0]
        end_num, end_info = (
            irc_response_nums["command_responses"]["RPL_ENDOFMOTD"][0],
            irc_response_nums["command_responses"]["RPL_ENDOFMOTD"][1],
        )

        motd_start_and_end = {
            "start_msg": f"{self.send_to_client_prefix} {start_num} {self.user.nick} {start_info}{self.send_to_client_suffix}",
            "end_msg": f"{self.send_to_client_prefix} {end_num} {self.user.nick} {end_info}{self.send_to_client_suffix}",
        }

        motd = [
            f"- Hello {self.user.nick}, welcome to Mantatail!",
            "-",
            "- Mantatail is a free, open-source IRC server released under MIT License",
            "-",
            "-",
            "-",
            "- For more info, please visit https://github.com/ThePhilgrim/MantaTail",
        ]

        start_msg = bytes(motd_start_and_end["start_msg"], encoding=self.encoding)
        end_msg = bytes(motd_start_and_end["end_msg"], encoding=self.encoding)

        self.user.socket.sendall(start_msg)

        for motd_line in motd:
            motd_msg = bytes(
                f"{self.send_to_client_prefix} {motd_num} {self.user.nick} :{motd_line}{self.send_to_client_suffix}",
                encoding=self.encoding,
            )
            self.user.socket.sendall(motd_msg)

        self.user.socket.sendall(end_msg)

    def handle_join(self, message):
        channel_regex = r"#[^ \x07,]{1,49}"  # TODO: Make more restrictive (currently valid: ###, #ö?!~ etc)

        if not re.match(channel_regex, message):
            no_channel_num, no_channel_info = (
                irc_response_nums["error_replies"]["ERR_NOSUCHCHANNEL"][0],
                irc_response_nums["error_replies"]["ERR_NOSUCHCHANNEL"][1].replace(
                    "<channel name>", message
                ),
            )

            self.generate_error_reply(no_channel_num, no_channel_info)

        else:
            if message not in self.server.channels.keys():
                self.server.channels[message] = Channel()

            if self.user.nick not in self.server.channels[message].user_list.keys():
                self.server.channels[message].user_list[self.user.nick] = self.user

        # TODO: Check for:
        #   * User invited to channel
        #   * Nick/user not matching bans
        #   * Eventual password matches
        #   * Not joined too many channels

    def handle_part(self, message):
        pass

    def handle_quit(self, message):
        print("Connection closed:", message)

    def handle_kick(self, message):
        pass

    def handle_nick(self, message):
        self.user.nick = message

    def handle_user(self, message):
        self.user.user_name = message.split(" ", 1)[0]

    def handle_privmsg(self, message):
        pass

    def generate_error_reply(self, error_num, error_info):
        self.user.socket.sendall(
            bytes(
                f"{self.send_to_client_prefix} {error_num} {self.user.nick} {error_info}{self.send_to_client_suffix}",
                encoding=self.encoding,
            )
        )


class Server:
    def __init__(self, port: int) -> None:
        self.host = "127.0.0.1"
        self.port = port
        self.listener_socket = socket.socket()
        self.listener_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.listener_socket.bind((self.host, self.port))
        self.listener_socket.listen(5)

        self.channels = {}
        # print("CHANNELS", self.channels)

    def run_server_forever(self) -> None:
        while True:
            user_socket, user_address = self.listener_socket.accept()
            user = User(user_address[0], user_socket)
            command_handler = IrcCommandHandler(self, user)
            client_thread = threading.Thread(
                target=self.recv_loop, args=[user, command_handler], daemon=True
            )

            client_thread.start()

    def recv_loop(self, user, command_handler) -> None:
        while True:
            request = b""
            # IRC messages always end with b"\r\n"
            while not request.endswith(b"\r\n"):
                request += user.socket.recv(10)

            decoded_message = request.decode("utf-8")
            for line in decoded_message.split("\r\n")[:-1]:
                # print(line)
                if " " in line:
                    verb, message = line.split(" ", 1)
                else:
                    verb = line
                    message = verb
                if verb.lower() == "nick":
                    user.nick = message
                    command_handler.handle_motd()

                # ex. "handle_nick" or "handle_join"
                handler_function_to_call = "handle_" + verb.lower()

                call_handler_function = getattr(
                    command_handler, handler_function_to_call
                )
                call_handler_function(message)

            if not request:
                break

        print("Connection Closed")


if __name__ == "__main__":
    server = Server(6667)
    server.run_server_forever()
