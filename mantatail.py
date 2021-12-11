import socket
import threading


class IrcCommandHandler:
    def __init__(self, client_socket):
        self.client_socket = client_socket

    def handle_motd(self, user_nick):
        motd = [
            f"- Hello {user_nick}, welcome to Mantatail!",
            "-",
            "- Mantatail is a free, open-source IRC server released under MIT License",
            "-",
            "-",
            "-",
            "- For help, please visit https://github.com/ThePhilgrim/MantaTail",
        ]

        reply_num = "375"  # Should be 375
        motd_suffix = "\r\n"
        # https://datatracker.ietf.org/doc/html/rfc1459#section-6.2

        for motd_line in motd:
            motd_prefix = f":mantatail {reply_num} {user_nick} :"
            message_to_send = bytes(
                motd_prefix + motd_line + motd_suffix, encoding="utf-8"
            )
            self.client_socket.sendall(message_to_send)
        self.client_socket.sendall(b"Last line with 376\r\n")

    def handle_join(self, message):
        print("JOIN MSG:", message)

    def handle_part(self, message):
        pass

    def handle_quit(self, message):
        print("Connection closed:", message)

    def handle_kick(self, message):
        pass

    def handle_nick(self, message):
        print("NICK MSG:", message)

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
            print(client_socket)
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
                if " " in line:
                    verb, message = line.split(" ", 1)
                else:
                    verb = line
                    message = verb
                print(verb)
                print(verb.lower())
                print("VERB:", verb)
                if verb.lower() == "nick":
                    print("INSIDE")
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
