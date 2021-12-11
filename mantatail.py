import socket
import threading


class IrcCommandHandler:
    def __init__(self):
        pass

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
        print("USER MSG:", message)

    def handle_privmsg(self, message):
        pass


class Server:
    def __init__(self, port: int) -> None:
        self.host = "127.0.0.1"
        self.port = port

    def run_server_forever(self) -> None:
        server_socket = socket.socket()
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_socket.bind((self.host, self.port))
        server_socket.listen(5)
        while True:
            client_socket, client_address = server_socket.accept()
            print("Connection", client_address)
            client_thread = threading.Thread(
                target=self.recv_loop, args=[client_socket], daemon=True
            )
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
                handler_function_to_call = "handle_" + verb.lower()
                command_handler = IrcCommandHandler()
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
