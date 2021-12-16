import pytest
import socket
import threading
from mantatail import Server

motd_dict_test = {
    "motd": [
        "- Hello {user_nick}, this is a test MOTD!",
        "-",
        "- Foo",
        "- Bar",
        "- Baz",
        "-",
        "- End test MOTD",
    ]
}


# Based on: https://gist.github.com/sbrugman/59b3535ebcd5aa0e2598293cfa58b6ab#gistcomment-3795790
@pytest.fixture(scope="function")
def fail_test_if_there_is_an_error_in_a_thread(monkeypatch):
    last_exception = None

    class ThreadWrapper(threading.Thread):
        def run(self):
            try:
                super().run()
            except Exception as e:
                nonlocal last_exception
                last_exception = e

    monkeypatch.setattr(threading, "Thread", ThreadWrapper)
    yield
    if last_exception:
        raise last_exception


@pytest.fixture(autouse=True, scope="function")
def run_server(fail_test_if_there_is_an_error_in_a_thread):
    server = Server(6667, motd_dict_test)

    def run_server(server):
        try:
            server.run_server_forever()
        except OSError:
            return

    threading.Thread(target=run_server, args=[server]).start()

    yield
    server.listener_socket.shutdown(socket.SHUT_RDWR)
    server.listener_socket.close()


@pytest.fixture(scope="function")
def user_alice(run_server):
    alice_socket = socket.socket()
    alice_socket.connect(("localhost", 6667))
    alice_socket.sendall(b"NICK foo\r\n")

    # Receiving everything the server is going to send helps prevent errors.
    # Otherwise it might not be fully started yet when the client quits.
    received = b""
    while not received.endswith(b"\r\n:mantatail 376 foo :End of /MOTD command\r\n"):
        received += alice_socket.recv(4096)

    yield
    alice_socket.sendall(b"QUIT\r\n")
    alice_socket.close()


@pytest.fixture(scope="function")
def user_bob(run_server):
    bob_socket = socket.socket()
    bob_socket.connect(("localhost", 6667))
    bob_socket.sendall(b"NICK foo\r\n")

    # Receiving everything the server is going to send helps prevent errors.
    # Otherwise it might not be fully started yet when the client quits.
    received = b""
    while not received.endswith(b"\r\n:mantatail 376 foo :End of /MOTD command\r\n"):
        received += bob_socket.recv(4096)

    yield
    bob_socket.sendall(b"QUIT\r\n")
    bob_socket.close()
