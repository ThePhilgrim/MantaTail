import pytest
import random
import socket
import traceback
import threading
import time
import mantatail

# from mantatail import Server

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
                traceback.print_exc()
                nonlocal last_exception
                last_exception = e

    monkeypatch.setattr(threading, "Thread", ThreadWrapper)
    yield
    if last_exception:
        raise last_exception


@pytest.fixture(autouse=True)
def run_server(fail_test_if_there_is_an_error_in_a_thread):
    server = mantatail.Server(6667, motd_dict_test)

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
    while receive_line(alice_socket) != b":mantatail 376 Alice :End of /MOTD command\r\n":
        pass

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
    while receive_line(bob_socket) != b":mantatail 376 Bob :End of /MOTD command\r\n":
        pass

    yield bob_socket
    bob_socket.sendall(b"QUIT\r\n")
    bob_socket.close()


##############
#    UTILS   #
##############


def receive_line(sock):
    sock.settimeout(1)
    received = b""
    while not received.endswith(b"\r\n"):
        received += sock.recv(1)
    return received


##############
#    TESTS   #
##############


def test_join_before_registering(run_server):
    user_socket = socket.socket()
    user_socket.connect(("localhost", 6667))
    user_socket.sendall(b"JOIN #foo\r\n")
    received = receive_line(user_socket)
    assert received == b":mantatail 451 * :You have not registered\r\n"


def test_join_channel(user_alice, user_bob):
    user_alice.sendall(b"JOIN #foo\r\n")
    time.sleep(1)
    user_bob.sendall(b"JOIN #foo\r\n")

    received = receive_line(user_bob)
    assert received == b":Bob!BobUsr@127.0.0.1 JOIN #foo\r\n"
    while receive_line(user_bob) != b":mantatail 353 Bob = #foo :Bob Alice\r\n":
        pass
    while receive_line(user_bob) != b":mantatail 366 Bob #foo :End of /NAMES list.\r\n":
        pass


def test_no_such_channel(user_alice):
    user_alice.sendall(b"PART #foo\r\n")
    received = receive_line(user_alice)
    assert received == b":mantatail 403 #foo :No such channel\r\n"


def test_youre_not_on_that_channel(user_alice, user_bob):
    user_alice.sendall(b"JOIN #foo\r\n")
    time.sleep(0.1)  # TODO: wait until server says that join is done
    user_bob.sendall(b"PART #foo\r\n")
    received = receive_line(user_bob)
    assert received == b":mantatail 442 #foo :You're not on that channel\r\n"


def test_send_privmsg(user_alice, user_bob):
    user_alice.sendall(b"JOIN #foo\r\n")
    time.sleep(0.1)
    user_bob.sendall(b"JOIN #foo\r\n")

    while receive_line(user_alice) != b":Bob!BobUsr@127.0.0.1 JOIN #foo\r\n":
        pass

    while receive_line(user_bob) != b":mantatail 366 Bob #foo :End of /NAMES list.\r\n":
        pass

    user_bob.sendall(b"PRIVMSG #foo :Foo\r\n")
    assert receive_line(user_alice) == b":Bob!BobUsr@127.0.0.1 PRIVMSG #foo :Foo\r\n"

    user_alice.sendall(b"PRIVMSG #foo :Bar\r\n")
    assert receive_line(user_bob) == b":Alice!AliceUsr@127.0.0.1 PRIVMSG #foo :Bar\r\n"

    user_bob.sendall(b"PRIVMSG #foo :Hello world\r\n")
    assert receive_line(user_alice) == b":Bob!BobUsr@127.0.0.1 PRIVMSG #foo :Hello world\r\n"


def test_privmsg_error_messages(user_alice, user_bob):
    user_alice.sendall(b"JOIN #foo\r\n")
    time.sleep(0.1)
    user_bob.sendall(b"PRIVMSG #foo :Bar\r\n")

    assert receive_line(user_bob) == b":mantatail 404 #foo :Cannot send to channel\r\n"

    user_bob.sendall(b"PRIVMSG #bar :Baz\r\n")

    assert receive_line(user_bob) == b":mantatail 401 #bar :No such nick/channel\r\n"


def test_send_unknown_commands(user_alice):
    user_alice.sendall(b"FOO\r\n")
    received = receive_line(user_alice)
    assert received == b":mantatail 421 foo :Unknown command\r\n"
    user_alice.sendall(b"FOO\r\n")
    received = receive_line(user_alice)
    assert received == b":mantatail 421 foo :Unknown command\r\n"
    user_alice.sendall(b"FOO\r\n")
    received = receive_line(user_alice)
    assert received == b":mantatail 421 foo :Unknown command\r\n"


# netcat sends \n line endings, but is fine receiving \r\n
def test_connect_via_netcat(run_server):
    with socket.socket() as nc:
        nc.connect(("localhost", 6667))  # nc localhost 6667
        nc.sendall(b"NICK nc\n")
        nc.sendall(b"USER nc 0 * :netcat\n")
        while receive_line(nc) != b":mantatail 376 nc :End of /MOTD command\r\n":
            pass


def test_join_part_race_condition(user_alice, user_bob):
    for i in range(100):
        user_alice.sendall(b"JOIN #foo\r\n")
        time.sleep(random.randint(0, 10) / 1000)
        user_alice.sendall(b"PART #foo\r\n")
        user_bob.sendall(b"JOIN #foo\r\n")
        time.sleep(random.randint(0, 10) / 1000)
        user_bob.sendall(b"PART #foo\r\n")
