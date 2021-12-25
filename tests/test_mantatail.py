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

##############
#  FIXTURES  #
##############

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


@pytest.fixture(autouse=True)
def run_server(fail_test_if_there_is_an_error_in_a_thread):
    server = Server(6667, motd_dict_test)

    def run_server(server):
        try:
            server.run_server_forever()
        except OSError:
            return

    threading.Thread(target=run_server, args=[server]).start()

    yield
    # .shutdown() raises an OSError on mac, removing it makes the test suite freeze on linux.
    try:
        server.listener_socket.shutdown(socket.SHUT_RDWR)
    except OSError:
        pass

    server.listener_socket.close()


@pytest.fixture
def user_alice(run_server):
    alice_socket = socket.socket()
    alice_socket.connect(("localhost", 6667))
    alice_socket.sendall(b"NICK Alice\r\n")
    alice_socket.sendall(b"USER AliceUsr 0 * :Alice's real name\r\n")

    # Receiving everything the server is going to send helps prevent errors.
    # Otherwise it might not be fully started yet when the client quits.
    received = b""
    while not received.endswith(b"\r\n:mantatail 376 Alice :End of /MOTD command\r\n"):
        received += alice_socket.recv(1)

    yield alice_socket
    alice_socket.sendall(b"QUIT\r\n")
    alice_socket.close()


@pytest.fixture
def user_bob(run_server):
    bob_socket = socket.socket()
    bob_socket.connect(("localhost", 6667))
    bob_socket.sendall(b"NICK Bob\r\n")
    bob_socket.sendall(b"USER BobUsr 0 * :Bob's real name\r\n")

    # Receiving everything the server is going to send helps prevent errors.
    # Otherwise it might not be fully started yet when the client quits.
    received = b""
    while not received.endswith(b"\r\n:mantatail 376 Bob :End of /MOTD command\r\n"):
        received += bob_socket.recv(1)

    yield bob_socket
    bob_socket.sendall(b"QUIT\r\n")
    bob_socket.close()


##############
#    UTILS   #
##############


def recv_loop(user):
    received = b""
    while not received.endswith(b"\r\n"):
        received += user.recv(1)
    return received


##############
#    TESTS   #
##############


def test_join_before_registering(run_server):
    user_socket = socket.socket()
    user_socket.connect(("localhost", 6667))
    user_socket.sendall(b"JOIN #foo\r\n")
    received = b""
    while not received.endswith(b"\r\n"):
        received += user_socket.recv(1)
    assert received == b":mantatail 451 * :You have not registered\r\n"


def test_no_such_channel(user_alice):
    user_alice.sendall(b"PART #foo\r\n")
    received = recv_loop(user_alice)
    assert received == b":mantatail 403 #foo :No such channel\r\n"


def test_youre_not_on_that_channel(user_alice, user_bob):
    user_alice.sendall(b"JOIN #foo\r\n")
    user_bob.sendall(b"PART #foo\r\n")
    received = recv_loop(user_bob)
    assert received == b":mantatail 442 #foo :You're not on that channel\r\n"
