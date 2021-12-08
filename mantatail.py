import socket


class Server:
    def __init__(self, port: int) -> None:
        self.host = "127.0.0.1"
        self.port = port

    def open_socket(self) -> None:
        socket_instance = socket.socket()
        socket_instance.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        socket_instance.bind((self.host, self.port))
        socket_instance.listen(5)
        while True:
            client, client_address = socket_instance.accept()
            print("Connection", client_address)
            self.server_echo(client)

    def server_echo(self, client) -> None:
        while True:
            request = client.recv(1000)
            if not request:
                break
            client.send("Received".encode("utf-8") + b"\n")
        print("Connection Closed")


if __name__ == "__main__":
    start_server = Server(25000)
    start_server.open_socket()
