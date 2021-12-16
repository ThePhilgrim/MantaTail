import pytest
import socket
import threading
from mantatail import Server


def test_motd():
    server = Server(6667)

    def run_server(server):
        try:
            server.run_server_forever()
        except OSError:
            return

    threading.Thread(target=run_server, args=[server]).start()

    client_socket = socket.socket()
    client_socket.connect(("localhost", 6667))
    client_socket.sendall(b"NICK foo\r\n")
    client_socket.recv(4096)

    server.listener_socket.close()
    server.listener_socket.shutdown(socket.SHUT_RDWR)
