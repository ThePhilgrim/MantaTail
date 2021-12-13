from io import open_code
import socket
import threading
import re

import get_irc_response_args


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
        start_num, start_info = get_irc_response_args.motd_start_message()
        motd_num = get_irc_response_args.motd_num()
        end_num, end_info = get_irc_response_args.motd_end_message()

        motd_start_and_end = {
            "start_msg": f"{self.send_to_client_prefix} {start_num} {self.user.nick} {start_info}{self.send_to_client_suffix}",
            "end_msg": f"{self.send_to_client_prefix} {end_num} {self.user.nick} {end_info}{self.send_to_client_suffix}",
        }

        start_msg = bytes(motd_start_and_end["start_msg"], encoding=self.encoding)
        end_msg = bytes(motd_start_and_end["end_msg"], encoding=self.encoding)
        motd = get_irc_response_args.motd()

        self.user.socket.sendall(start_msg)

        for motd_line in motd:
            motd_msg = bytes(
                f"{self.send_to_client_prefix} {motd_num} {self.user.nick} :{motd_line.format(user_nick=self.user.nick)}{self.send_to_client_suffix}",
                encoding=self.encoding,
            )
            self.user.socket.sendall(motd_msg)

        self.user.socket.sendall(end_msg)

    def handle_join(self, message):
        channel_regex = r"#[^ \x07,]{1,49}"  # TODO: Make more restrictive (currently valid: ###, #ö?!~ etc)

        if not re.match(channel_regex, message):
            self.handle_no_such_channel(message)
            # no_channel_num, no_channel_info = get_irc_response_args.no_such_channel(
            #     message
            # )

            # self.generate_error_reply(no_channel_num, no_channel_info)

        else:
            if not message in self.server.channels.keys():
                self.server.channels[message] = Channel()

            if self.user.nick in self.server.channels[message].user_list.keys():
                return
            else:
                self.server.channels[message].user_list[self.user.nick] = self.user

        # TODO: Check for:
        #   * User invited to channel
        #   * Nick/user not matching bans
        #   * Eventual password matches
        #   * Not joined too many channels

    def handle_part(self, message):
        if message not in self.server.channels.keys():
            self.handle_no_such_channel(message)
        elif self.user.nick not in self.server.channels[message].user_list.keys():
            (
                not_on_channel_num,
                not_on_channel_info,
            ) = get_irc_response_args.not_on_channel(message)

            self.generate_error_reply(not_on_channel_num, not_on_channel_info)
        else:
            del self.server.channels[message].user_list[self.user.nick]
            if len(self.server.channels[message].user_list.keys()) == 0:
                del self.server.channels[message]

    def handle_quit(self, message):
        pass

    def handle_kick(self, message):
        pass

    def handle_nick(self, message):
        self.user.nick = message

    def handle_user(self, message):
        self.user.user_name = message.split(" ", 1)[0]

    def handle_privmsg(self, message):
        pass

    def handle_unknown_command(self, command):
        unknown_cmd_num, unknown_cmd_info = get_irc_response_args.unknown_command(
            command
        )

        self.generate_error_reply(unknown_cmd_num, unknown_cmd_info)

    def handle_no_such_channel(self, message):
        no_channel_num, no_channel_info = get_irc_response_args.no_such_channel(message)

        self.generate_error_reply(no_channel_num, no_channel_info)

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

        self.supported_commands = ["nick", "user", "join", "part"]
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

                verb_lower = verb.lower()

                if verb_lower == "nick":
                    user.nick = message
                    command_handler.handle_motd()

                if verb_lower not in self.supported_commands:
                    command_handler.handle_unknown_command(verb_lower)
                    return
                # ex. "handle_nick" or "handle_join"
                handler_function_to_call = "handle_" + verb_lower

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
