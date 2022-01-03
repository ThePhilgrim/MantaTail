import pytest
import random
import socket
import traceback
import threading
import time

from mantatail import Listener

# Tests that are known to fail can be decorated with:
# @pytest.mark.xfail(strict=True)

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
    listener = Listener(6667, motd_dict_test)

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
    while b"QUIT" not in receive_line(alice_socket):
        pass
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
    while b"QUIT" not in receive_line(bob_socket):
        pass
    bob_socket.close()


@pytest.fixture
def user_charlie(run_server):
    charlie_socket = socket.socket()
    charlie_socket.connect(("localhost", 6667))
    charlie_socket.sendall(b"NICK Charlie\r\n")
    charlie_socket.sendall(b"USER CharlieUsr 0 * :Charlie's real name\r\n")

    # Receiving everything the server is going to send helps prevent errors.
    # Otherwise it might not be fully started yet when the client quits.
    while receive_line(charlie_socket) != b":mantatail 376 Charlie :End of /MOTD command\r\n":
        pass

    yield charlie_socket
    charlie_socket.sendall(b"QUIT\r\n")
    while b"QUIT" not in receive_line(charlie_socket):
        pass
    charlie_socket.close()


##############
#    UTILS   #
##############


def receive_line(sock):
    sock.settimeout(1)
    received = b""
    while not received.endswith(b"\r\n"):
        received += sock.recv(1)
    return received


# Makes it easier to assert bytes received from Sets
def compare_if_word_match_in_any_order(received_bytes, compare_with):
    return set(received_bytes.split()) == set(compare_with.split())


##############
#    TESTS   #
##############


def test_join_before_registering(run_server):
    user_socket = socket.socket()
    user_socket.connect(("localhost", 6667))
    user_socket.sendall(b"JOIN #foo\r\n")
    assert receive_line(user_socket) == b":mantatail 451 * :You have not registered\r\n"


def test_join_channel(user_alice, user_bob):
    user_alice.sendall(b"JOIN #foo\r\n")
    time.sleep(1)
    user_bob.sendall(b"JOIN #foo\r\n")

    assert receive_line(user_bob) == b":Bob!BobUsr@127.0.0.1 JOIN #foo\r\n"

    while receive_line(user_bob) != b":mantatail 353 Bob = #foo :Bob ~Alice\r\n":
        pass
    while receive_line(user_bob) != b":mantatail 366 Bob #foo :End of /NAMES list.\r\n":
        pass


def test_no_such_channel(user_alice):
    user_alice.sendall(b"PART #foo\r\n")
    assert receive_line(user_alice) == b":mantatail 403 #foo :No such channel\r\n"


def test_youre_not_on_that_channel(user_alice, user_bob):
    user_alice.sendall(b"JOIN #foo\r\n")
    time.sleep(0.1)  # TODO: wait until server says that join is done
    user_bob.sendall(b"PART #foo\r\n")

    assert receive_line(user_bob) == b":mantatail 442 #foo :You're not on that channel\r\n"


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
    assert receive_line(user_alice) == b":mantatail 421 foo :Unknown command\r\n"
    user_alice.sendall(b"FOO\r\n")
    assert receive_line(user_alice) == b":mantatail 421 foo :Unknown command\r\n"
    user_alice.sendall(b"FOO\r\n")
    assert receive_line(user_alice) == b":mantatail 421 foo :Unknown command\r\n"


def test_unknown_mode(user_alice):
    user_alice.sendall(b"JOIN #foo\r\n")

    while receive_line(user_alice) != b":mantatail 366 Alice #foo :End of /NAMES list.\r\n":
        pass

    user_alice.sendall(b"MODE #foo ^g Bob\r\n")
    assert receive_line(user_alice) == b":mantatail 472 ^ :is unknown mode char to me\r\n"

    user_alice.sendall(b"MODE #foo +g Bob\r\n")
    assert receive_line(user_alice) == b":mantatail 472 g :is unknown mode char to me\r\n"


def test_op_deop_user(user_alice, user_bob):
    user_alice.sendall(b"JOIN #foo\r\n")
    time.sleep(0.1)
    user_bob.sendall(b"JOIN #foo\r\n")

    while receive_line(user_alice) != b":Bob!BobUsr@127.0.0.1 JOIN #foo\r\n":
        pass
    while receive_line(user_bob) != b":mantatail 366 Bob #foo :End of /NAMES list.\r\n":
        pass

    user_alice.sendall(b"MODE #foo +o Bob\r\n")
    assert receive_line(user_alice) == b":mantatail MODE #foo +o Bob\r\n"
    assert receive_line(user_bob) == b":mantatail MODE #foo +o Bob\r\n"

    user_alice.sendall(b"MODE #foo -o Bob\r\n")
    assert receive_line(user_alice) == b":mantatail MODE #foo -o Bob\r\n"
    assert receive_line(user_bob) == b":mantatail MODE #foo -o Bob\r\n"


def test_channel_owner(user_alice, user_bob):
    user_alice.sendall(b"JOIN #foo\r\n")
    time.sleep(0.1)
    user_bob.sendall(b"JOIN #foo\r\n")

    while receive_line(user_alice) != b":mantatail 366 Alice #foo :End of /NAMES list.\r\n":
        pass

    while True:
        received = receive_line(user_bob)
        if b"353" in received:
            assert compare_if_word_match_in_any_order(received, b":mantatail 353 Bob = #foo :Bob ~Alice\r\n")
            break

    user_alice.sendall(b"PART #foo\r\n")
    user_bob.sendall(b"PART #foo\r\n")

    user_bob.sendall(b"JOIN #foo\r\n")
    time.sleep(0.1)
    user_alice.sendall(b"JOIN #foo\r\n")

    while True:
        received = receive_line(user_alice)
        if b"353" in received:
            assert compare_if_word_match_in_any_order(received, b":mantatail 353 Alice = #foo :Alice ~Bob\r\n")
            break


def test_operator_prefix(user_alice, user_bob, user_charlie):
    user_alice.sendall(b"JOIN #foo\r\n")
    time.sleep(0.1)
    user_bob.sendall(b"JOIN #foo\r\n")
    time.sleep(0.1)
    user_alice.sendall(b"MODE #foo +o Bob\r\n")
    time.sleep(0.1)
    user_charlie.sendall(b"JOIN #foo\r\n")

    while True:
        received = receive_line(user_charlie)
        if b"353" in received:
            assert compare_if_word_match_in_any_order(
                received, b":mantatail 353 Charlie = #foo :Charlie ~Alice @Bob\r\n"
            )
            break

    user_charlie.sendall(b"PART #foo\r\n")
    user_alice.sendall(b"MODE #foo -o Bob\r\n")
    time.sleep(0.1)
    user_charlie.sendall(b"JOIN #foo\r\n")

    while True:
        received = receive_line(user_charlie)
        if b"353" in received:
            assert compare_if_word_match_in_any_order(
                received, b":mantatail 353 Charlie = #foo :Charlie ~Alice Bob\r\n"
            )
            break

    user_charlie.sendall(b"PART #foo\r\n")
    user_alice.sendall(b"MODE #foo +o Bob\r\n")
    time.sleep(0.1)
    user_charlie.sendall(b"JOIN #foo\r\n")

    while True:
        received = receive_line(user_charlie)
        if b"353" in received:
            assert compare_if_word_match_in_any_order(
                received, b":mantatail 353 Charlie = #foo :Charlie ~Alice @Bob\r\n"
            )
            break


def test_operator_no_such_channel(user_alice):
    user_alice.sendall(b"MODE #foo +o Bob\r\n")
    assert receive_line(user_alice) == b":mantatail 403 #foo :No such channel\r\n"


def test_operator_no_privileges(user_alice, user_bob):
    user_alice.sendall(b"JOIN #foo\r\n")
    time.sleep(0.1)
    user_bob.sendall(b"JOIN #foo\r\n")

    while receive_line(user_alice) != b":Bob!BobUsr@127.0.0.1 JOIN #foo\r\n":
        pass
    while receive_line(user_bob) != b":mantatail 366 Bob #foo :End of /NAMES list.\r\n":
        pass

    user_bob.sendall(b"MODE #foo +o Alice\r\n")
    assert receive_line(user_bob) == b":mantatail 482 #foo :You're not channel operator\r\n"


def test_operator_user_not_in_channel(user_alice, user_bob):
    user_alice.sendall(b"JOIN #foo\r\n")

    while receive_line(user_alice) != b":mantatail 366 Alice #foo :End of /NAMES list.\r\n":
        pass

    user_alice.sendall(b"MODE #foo +o Bob\r\n")
    assert receive_line(user_alice) == b":mantatail 441 Bob #foo :They aren't on that channel\r\n"


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


def test_nick_already_taken(run_server):
    nc = socket.socket()
    nc.connect(("localhost", 6667))
    nc.sendall(b"NICK nc\n")
    nc.sendall(b"USER nc 0 * :netcat\n")

    while receive_line(nc) != b":mantatail 376 nc :End of /MOTD command\r\n":
        pass

    nc2 = socket.socket()
    nc2.connect(("localhost", 6667))
    nc2.sendall(b"NICK nc\n")
    assert receive_line(nc2) == b":mantatail 433 nc :Nickname is already in use\r\n"

    nc.sendall(b"QUIT\r\n")
    while b"QUIT" not in receive_line(nc):
        pass
    nc.close()

    time.sleep(0.1)

    nc2.sendall(b"NICK nc\n")
    nc2.sendall(b"USER nc\n")

    while receive_line(nc2) != b":mantatail 376 nc :End of /MOTD command\r\n":
        pass

    nc2.sendall(b"QUIT\r\n")
    while b"QUIT" not in receive_line(nc2):
        pass
    nc2.close()
