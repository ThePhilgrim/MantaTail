from io import open_code
import socket
import threading
import re
import json
import sys


try:
    with open("./resources/irc_response_nums.json", "r") as file:
        irc_response_nums = json.load(file)
except FileNotFoundError:
    sys.exit("FileNotFoundError: Missing resources/irc_response_nums.json")


class Channel:
    def __init__(self):
        pass


class IrcCommandHandler:
    def __init__(self, client_socket):
        self.client_socket = client_socket
        self.encoding = "utf-8"
        self.send_to_client_prefix = ":mantatail"
        self.send_to_client_suffix = "\r\n"

    def handle_motd(self, user_nick):
        # https://datatracker.ietf.org/doc/html/rfc1459#section-6.2
        start_num = "372"
        motd_num = "375"
        end_num = "376"

        motd_start_and_end = {
            "start_msg": f"{self.send_to_client_prefix} {start_num} {user_nick} :- mantatail Message of the Day - {self.send_to_client_suffix}",
            "end_msg": f"{self.send_to_client_prefix} {end_num} {user_nick} :End of /MOTD command.{self.send_to_client_suffix}",
        }

        motd = [
            f"- Hello {user_nick}, welcome to Mantatail!",
            "-",
            "- Mantatail is a free, open-source IRC server released under MIT License",
            "-",
            "-",
            "-",
            "- For more info, please visit https://github.com/ThePhilgrim/MantaTail",
        ]

        start_msg = bytes(motd_start_and_end["start_msg"], encoding=self.encoding)
        end_msg = bytes(motd_start_and_end["end_msg"], encoding=self.encoding)

        self.client_socket.sendall(start_msg)

        for motd_line in motd:
            motd_msg = bytes(
                f"{self.send_to_client_prefix} {motd_num} {user_nick} :{motd_line}{self.send_to_client_suffix}",
                encoding=self.encoding,
            )
            self.client_socket.sendall(motd_msg)

        self.client_socket.sendall(end_msg)

    def handle_join(self, message):
        channel_regex = r"[&#+!][^ \x07,]{1,49}"  # Covers max 200 characters?
        if not re.match(channel_regex, message):
            self.client_socket.sendall(
                bytes(f"{self.send_to_client_prefix} ", encoding=self.encoding)
            )
        # TODO: Check for:
        #   * User invited to channel
        #   * Nick/user not matching bans
        #   * Eventual password matches
        #   * Not joined too many channels
        print(message[1:])

    def handle_part(self, message):
        pass

    def handle_quit(self, message):
        print("Connection closed:", message)

    def handle_kick(self, message):
        pass

    def handle_nick(self, message):
        pass

    def handle_user(self, message):
        pass

    def handle_privmsg(self, message):
        pass


class Server:
    def __init__(self, port: int) -> None:
        self.host = "127.0.0.1"
        self.port = port
        self.listener_socket = socket.socket()
        self.listener_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.listener_socket.bind((self.host, self.port))
        self.listener_socket.listen(5)

        self.user_nick = None

    def run_server_forever(self) -> None:
        while True:
            client_socket, client_address = self.listener_socket.accept()
            print("Connection", client_address)
            client_thread = threading.Thread(
                target=self.recv_loop, args=[client_socket], daemon=True
            )
            self.irc_command_handler = IrcCommandHandler(client_socket)

            client_thread.start()

    def recv_loop(self, client_socket) -> None:
        while True:
            request = b""
            # IRC messages always end with b"\r\n"
            while not request.endswith(b"\r\n"):
                request += client_socket.recv(10)

            decoded_message = request.decode("utf-8")
            for line in decoded_message.split("\r\n")[:-1]:
                print(line)
                if " " in line:
                    verb, message = line.split(" ", 1)
                else:
                    verb = line
                    message = verb
                if verb.lower() == "nick":
                    self.user_nick = message
                    self.irc_command_handler.handle_motd(self.user_nick)

                handler_function_to_call = "handle_" + verb.lower()

                call_handler_function = getattr(
                    self.irc_command_handler, handler_function_to_call
                )
                call_handler_function(message)

            if not request:
                break

        print("Connection Closed")


if __name__ == "__main__":
    server = Server(6667)
    server.run_server_forever()
