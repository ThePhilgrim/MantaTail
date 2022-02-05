import pytest
import threading
import traceback
import socket

import server
from server import ConnectionListener

# fmt: off
motd_dict_test = {
    "motd": [
        "- Hello {user_nick}, this is a test MOTD!",
        "-",
        "- Foo",
        "- Bar",
        "- Baz",
        "-",
        "- End test MOTD"
        ]
}

# fmt: on

# Based on: https://gist.github.com/sbrugman/59b3535ebcd5aa0e2598293cfa58b6ab#gistcomment-3795790
@pytest.fixture(scope="function")
def fail_test_if_there_is_an_error_in_a_thread(monkeypatch):
    last_exception = None

    class ThreadWrapper(threading.Thread):
        def run(self):
            try:
                super().run()
            except Exception as e:
                traceback.print_exc()
                nonlocal last_exception
                last_exception = e

    monkeypatch.setattr(threading, "Thread", ThreadWrapper)
    yield
    if last_exception:
        raise last_exception


@pytest.fixture()
def run_server(fail_test_if_there_is_an_error_in_a_thread):
    listener = ConnectionListener(6667, motd_dict_test)

    def run_server():
        try:
            listener.run_server_forever()
        except OSError:
            return

    threading.Thread(target=run_server).start()

    yield

    # .shutdown() raises an OSError on mac, removing it makes the test suite freeze on linux.
    try:
        listener.listener_socket.shutdown(socket.SHUT_RDWR)
    except OSError:
        pass
    listener.listener_socket.close()


@pytest.fixture
def user_alice(run_server, helpers):
    alice_socket = socket.socket()
    alice_socket.connect(("localhost", 6667))
    alice_socket.sendall(b"NICK Alice\r\n")
    alice_socket.sendall(b"USER AliceUsr 0 * :Alice's real name\r\n")

    # Receiving everything the server is going to send helps prevent errors.
    # Otherwise it might not be fully started yet when the client quits.
    while helpers.receive_line(alice_socket) != b":mantatail 376 Alice :End of /MOTD command\r\n":
        pass

    yield alice_socket
    alice_socket.sendall(b"QUIT\r\n")
    while b"QUIT" not in helpers.receive_line(alice_socket):
        pass
    alice_socket.close()


@pytest.fixture
def user_bob(run_server, helpers):
    bob_socket = socket.socket()
    bob_socket.connect(("localhost", 6667))
    bob_socket.sendall(b"NICK Bob\r\n")
    bob_socket.sendall(b"USER BobUsr 0 * :Bob's real name\r\n")

    # Receiving everything the server is going to send helps prevent errors.
    # Otherwise it might not be fully started yet when the client quits.
    while helpers.receive_line(bob_socket) != b":mantatail 376 Bob :End of /MOTD command\r\n":
        pass

    yield bob_socket
    bob_socket.sendall(b"QUIT\r\n")
    while b"QUIT" not in helpers.receive_line(bob_socket):
        pass
    bob_socket.close()


@pytest.fixture
def user_charlie(run_server, helpers):
    charlie_socket = socket.socket()
    charlie_socket.connect(("localhost", 6667))
    charlie_socket.sendall(b"NICK Charlie\r\n")
    charlie_socket.sendall(b"USER CharlieUsr 0 * :Charlie's real name\r\n")

    # Receiving everything the server is going to send helps prevent errors.
    # Otherwise it might not be fully started yet when the client quits.
    while helpers.receive_line(charlie_socket) != b":mantatail 376 Charlie :End of /MOTD command\r\n":
        pass

    yield charlie_socket
    charlie_socket.sendall(b"QUIT\r\n")
    while b"QUIT" not in helpers.receive_line(charlie_socket):
        pass
    charlie_socket.close()


# Based on https://stackoverflow.com/a/42156088/15382873
class Helpers:
    def receive_line(sock, timeout=1):
        sock.settimeout(timeout)
        received = b""
        while not received.endswith(b"\r\n"):
            received += sock.recv(1)
        return received

    # Makes it easier to assert bytes received from Sets
    def compare_if_word_match_in_any_order(received_bytes, compare_with):
        return set(received_bytes.split()) == set(compare_with.split())


@pytest.fixture
def helpers():
    return Helpers


# @pytest.fixture
# def receive_line():
#     def execute_receive_line(sock, timeout=1):
#         sock.settimeout(timeout)
#         received = b""
#         while not received.endswith(b"\r\n"):
#             received += sock.recv(1)
#         return received

#     return execute_receive_line


# Makes it easier to assert bytes received from Sets
# @pytest.fixture
# def compare_if_word_match_in_any_order():
#     def compare_words(received_bytes, compare_with):
#         return set(received_bytes.split()) == set(compare_with.split())

#     return compare_words
