import os
import sys
import pytest
import random
import socket
import traceback
import threading
import time

import server
from server import ConnectionListener

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


def receive_line(sock, timeout=1):
    sock.settimeout(timeout)
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


def test_ping_message(monkeypatch, user_alice):
    monkeypatch.setattr(server, "TIMER_SECONDS", 2)
    user_alice.sendall(b"JOIN #foo\r\n")

    while receive_line(user_alice, 3) != b":mantatail PING :mantatail\r\n":
        pass

    user_alice.sendall(b"PONG :mantatail\r\n")


def test_join_channel(user_alice, user_bob):
    user_alice.sendall(b"JOIN #foo\r\n")
    time.sleep(0.1)
    user_bob.sendall(b"JOIN #foo\r\n")

    assert receive_line(user_bob) == b":Bob!BobUsr@127.0.0.1 JOIN #foo\r\n"

    while receive_line(user_bob) != b":mantatail 353 Bob = #foo :Bob @Alice\r\n":
        pass
    while receive_line(user_bob) != b":mantatail 366 Bob #foo :End of /NAMES list.\r\n":
        pass


def test_no_such_channel(user_alice):
    user_alice.sendall(b"PART #foo\r\n")
    assert receive_line(user_alice) == b":mantatail 403 Alice #foo :No such channel\r\n"


def test_youre_not_on_that_channel(user_alice, user_bob):
    user_alice.sendall(b"JOIN #foo\r\n")
    time.sleep(0.1)  # TODO: wait until server says that join is done
    user_bob.sendall(b"PART #foo\r\n")

    assert receive_line(user_bob) == b":mantatail 442 Bob #foo :You're not on that channel\r\n"


def test_nick_change(user_alice, user_bob):
    user_alice.sendall(b"JOIN #foo\r\n")
    time.sleep(0.1)
    user_bob.sendall(b"JOIN #foo\r\n")

    while receive_line(user_alice) != b":Bob!BobUsr@127.0.0.1 JOIN #foo\r\n":
        pass
    while receive_line(user_bob) != b":mantatail 366 Bob #foo :End of /NAMES list.\r\n":
        pass

    user_alice.sendall(b"NICK :NewNick\r\n")
    assert receive_line(user_alice) == b":Alice!AliceUsr@127.0.0.1 NICK :NewNick\r\n"
    assert receive_line(user_bob) == b":Alice!AliceUsr@127.0.0.1 NICK :NewNick\r\n"

    user_alice.sendall(b"PRIVMSG #foo :Alice should have a new user mask\r\n")
    assert receive_line(user_bob) == b":NewNick!AliceUsr@127.0.0.1 PRIVMSG #foo :Alice should have a new user mask\r\n"

    user_alice.sendall(b"NICK :NEWNICK\r\n")
    assert receive_line(user_alice) == b":NewNick!AliceUsr@127.0.0.1 NICK :NEWNICK\r\n"
    assert receive_line(user_bob) == b":NewNick!AliceUsr@127.0.0.1 NICK :NEWNICK\r\n"

    user_alice.sendall(b"NICK :NEWNICK\r\n")

    user_alice.sendall(b"PART #foo\r\n")

    # Assert instead of while receive_line() loop ensures nothing was sent from server after
    # changing to identical nick
    assert receive_line(user_alice) == b":NEWNICK!AliceUsr@127.0.0.1 PART #foo\r\n"


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

    user_alice.sendall(b"PRIVMSG #foo Bar\r\n")
    assert receive_line(user_bob) == b":Alice!AliceUsr@127.0.0.1 PRIVMSG #foo :Bar\r\n"

    user_bob.sendall(b"PRIVMSG #foo :Foo Bar\r\n")
    assert receive_line(user_alice) == b":Bob!BobUsr@127.0.0.1 PRIVMSG #foo :Foo Bar\r\n"

    user_alice.sendall(b"PRIVMSG #foo Foo Bar\r\n")
    assert receive_line(user_bob) == b":Alice!AliceUsr@127.0.0.1 PRIVMSG #foo :Foo\r\n"


def test_away_status(user_alice, user_bob):
    user_alice.sendall(b"PRIVMSG Bob :Hello Bob\r\n")
    assert receive_line(user_bob) == b":Alice!AliceUsr@127.0.0.1 PRIVMSG Bob :Hello Bob\r\n"

    # Makes sure that Alice doesn't receive an away message from Bob
    with pytest.raises(socket.timeout):
        receive_line(user_alice)

    user_bob.sendall(b"AWAY\r\n")
    assert receive_line(user_bob) == b":mantatail 305 Bob :You are no longer marked as being away\r\n"

    # Makes sure UNAWAY (306) is only sent to Bob
    with pytest.raises(socket.timeout):
        receive_line(user_alice)

    user_bob.sendall(b"AWAY :This is an away status\r\n")
    assert receive_line(user_bob) == b":mantatail 306 Bob :You have been marked as being away\r\n"

    # Makes sure NOWAWAY (305) is only sent to Bob
    with pytest.raises(socket.timeout):
        receive_line(user_alice)

    user_alice.sendall(b"PRIVMSG Bob :Hello Bob\r\n")
    assert receive_line(user_bob) == b":Alice!AliceUsr@127.0.0.1 PRIVMSG Bob :Hello Bob\r\n"

    assert receive_line(user_alice) == b":mantatail 301 Alice Bob :This is an away status\r\n"

    user_bob.sendall(b"AWAY\r\n")
    assert receive_line(user_bob) == b":mantatail 305 Bob :You are no longer marked as being away\r\n"

    user_bob.sendall(b"AWAY This is an away status\r\n")
    assert receive_line(user_bob) == b":mantatail 306 Bob :You have been marked as being away\r\n"

    user_alice.sendall(b"PRIVMSG Bob :Hello Bob\r\n")
    assert receive_line(user_bob) == b":Alice!AliceUsr@127.0.0.1 PRIVMSG Bob :Hello Bob\r\n"

    assert receive_line(user_alice) == b":mantatail 301 Alice Bob :This\r\n"


def test_channel_topics(user_alice, user_bob, user_charlie):
    user_alice.sendall(b"JOIN #foo\r\n")
    time.sleep(0.1)
    user_bob.sendall(b"JOIN #foo\r\n")

    while True:
        received = receive_line(user_alice)
        assert b"332" not in received
        assert b"333" not in received
        if received == b":Bob!BobUsr@127.0.0.1 JOIN #foo\r\n":
            break

    while receive_line(user_bob) != b":mantatail 366 Bob #foo :End of /NAMES list.\r\n":
        pass

    user_alice.sendall(b"TOPIC\r\n")
    assert receive_line(user_alice) == b":mantatail 461 Alice TOPIC :Not enough parameters\r\n"

    user_alice.sendall(b"TOPIC #foo\r\n")
    assert receive_line(user_alice) == b":mantatail 331 Alice #foo :No topic is set.\r\n"

    user_alice.sendall(b"TOPIC #foo :This is a topic\r\n")
    assert receive_line(user_alice) == b":Alice!AliceUsr@127.0.0.1 TOPIC #foo :This is a topic\r\n"
    assert receive_line(user_bob) == b":Alice!AliceUsr@127.0.0.1 TOPIC #foo :This is a topic\r\n"

    time.sleep(0.1)
    user_charlie.sendall(b"JOIN #foo\r\n")
    receive_line(user_charlie)
    assert receive_line(user_charlie) == b":mantatail 332 Charlie #foo :This is a topic\r\n"
    assert receive_line(user_charlie) == b":mantatail 333 Charlie #foo :Alice\r\n"

    user_alice.sendall(b"TOPIC #foo\r\n")
    receive_line(user_alice)  # Charlie's JOIN message
    assert receive_line(user_alice) == b":mantatail 332 Alice #foo :This is a topic\r\n"
    assert receive_line(user_alice) == b":mantatail 333 Alice #foo :Alice\r\n"

    user_bob.sendall(b"TOPIC #foo\r\n")
    receive_line(user_bob)  # Charlie's JOIN message
    assert receive_line(user_bob) == b":mantatail 332 Bob #foo :This is a topic\r\n"
    assert receive_line(user_bob) == b":mantatail 333 Bob #foo :Alice\r\n"

    user_bob.sendall(b"TOPIC #foo :Bob is setting a topic\r\n")
    assert receive_line(user_bob) == b":mantatail 482 Bob #foo :You're not channel operator\r\n"

    user_bob.sendall(b"TOPIC #foo :\r\n")
    assert receive_line(user_bob) == b":mantatail 482 Bob #foo :You're not channel operator\r\n"

    user_alice.sendall(b"TOPIC #foo :\r\n")
    assert receive_line(user_alice) == b":Alice!AliceUsr@127.0.0.1 TOPIC #foo :\r\n"
    assert receive_line(user_bob) == b":Alice!AliceUsr@127.0.0.1 TOPIC #foo :\r\n"

    user_alice.sendall(b"TOPIC #foo\r\n")
    assert receive_line(user_alice) == b":mantatail 331 Alice #foo :No topic is set.\r\n"
    user_bob.sendall(b"TOPIC #foo\r\n")
    assert receive_line(user_bob) == b":mantatail 331 Bob #foo :No topic is set.\r\n"


def test_send_privmsg_to_user(user_alice, user_bob):
    user_alice.sendall(b"PRIVMSG Bob :This is a private message\r\n")
    assert receive_line(user_bob) == b":Alice!AliceUsr@127.0.0.1 PRIVMSG Bob :This is a private message\r\n"

    user_bob.sendall(b"PRIVMSG alice :This is a reply\r\n")
    assert receive_line(user_alice) == b":Bob!BobUsr@127.0.0.1 PRIVMSG Alice :This is a reply\r\n"


def test_privmsg_error_messages(user_alice, user_bob):
    user_alice.sendall(b"JOIN #foo\r\n")
    while receive_line(user_alice) != b":mantatail 366 Alice #foo :End of /NAMES list.\r\n":
        pass
    time.sleep(0.1)

    user_bob.sendall(b"PRIVMSG #foo :Bar\r\n")
    assert receive_line(user_bob) == b":mantatail 442 Bob #foo :You're not on that channel\r\n"

    user_bob.sendall(b"PRIVMSG #bar :Baz\r\n")
    assert receive_line(user_bob) == b":mantatail 403 Bob #bar :No such channel\r\n"

    user_alice.sendall(b"PRIVMSG\r\n")
    assert receive_line(user_alice) == b":mantatail 411 Alice :No recipient given (PRIVMSG)\r\n"

    user_alice.sendall(b"PRIVMSG #foo\r\n")
    assert receive_line(user_alice) == b":mantatail 412 Alice :No text to send\r\n"

    user_alice.sendall(b"PRIVMSG Charlie :This is a private message\r\n")
    assert receive_line(user_alice) == b":mantatail 401 Alice Charlie :No such nick/channel\r\n"


def test_not_enough_params_error(user_alice):
    user_alice.sendall(b"JOIN\r\n")
    assert receive_line(user_alice) == b":mantatail 461 Alice JOIN :Not enough parameters\r\n"

    user_alice.sendall(b"JOIN #foo\r\n")
    while receive_line(user_alice) != b":mantatail 366 Alice #foo :End of /NAMES list.\r\n":
        pass

    user_alice.sendall(b"part\r\n")
    assert receive_line(user_alice) == b":mantatail 461 Alice PART :Not enough parameters\r\n"

    user_alice.sendall(b"Mode\r\n")
    assert receive_line(user_alice) == b":mantatail 461 Alice MODE :Not enough parameters\r\n"

    user_alice.sendall(b"KICK\r\n")
    assert receive_line(user_alice) == b":mantatail 461 Alice KICK :Not enough parameters\r\n"

    user_alice.sendall(b"KICK Bob\r\n")
    assert receive_line(user_alice) == b":mantatail 461 Alice KICK :Not enough parameters\r\n"

    nc = socket.socket()
    nc.connect(("localhost", 6667))

    nc.sendall(b"USER\n")
    assert receive_line(nc) == b":mantatail 461 * USER :Not enough parameters\r\n"

    nc.sendall(b"QUIT\r\n")
    while b"QUIT" not in receive_line(nc):
        pass
    nc.close()


def test_send_unknown_commands(user_alice):
    user_alice.sendall(b"FOO\r\n")
    assert receive_line(user_alice) == b":mantatail 421 Alice FOO :Unknown command\r\n"
    user_alice.sendall(b"Bar\r\n")
    assert receive_line(user_alice) == b":mantatail 421 Alice Bar :Unknown command\r\n"
    user_alice.sendall(b"baz\r\n")
    assert receive_line(user_alice) == b":mantatail 421 Alice baz :Unknown command\r\n"
    user_alice.sendall(b"&/!\r\n")
    assert receive_line(user_alice) == b":mantatail 421 Alice &/! :Unknown command\r\n"


def test_channel_mode_is(user_alice):
    user_alice.sendall(b"JOIN #foo\r\n")

    while receive_line(user_alice) != b":mantatail 366 Alice #foo :End of /NAMES list.\r\n":
        pass

    user_alice.sendall(b"MODE #foo\r\n")
    assert receive_line(user_alice) == b":mantatail 324 Alice #foo +t\r\n"


def test_mode_several_flags(user_alice, user_bob, user_charlie):
    user_alice.sendall(b"JOIN #foo\r\n")
    time.sleep(0.1)
    user_bob.sendall(b"JOIN #foo\r\n")
    time.sleep(0.1)
    user_charlie.sendall(b"JOIN #foo\r\n")

    while receive_line(user_alice) != b":Charlie!CharlieUsr@127.0.0.1 JOIN #foo\r\n":
        pass
    while receive_line(user_bob) != b":Charlie!CharlieUsr@127.0.0.1 JOIN #foo\r\n":
        pass
    while receive_line(user_charlie) != b":mantatail 366 Charlie #foo :End of /NAMES list.\r\n":
        pass

    user_alice.sendall(b"MODE #foo +ob Bob\r\n")

    assert receive_line(user_alice) == b":Alice!AliceUsr@127.0.0.1 MODE #foo +o Bob\r\n"
    assert receive_line(user_alice) == b":mantatail 368 Alice #foo :End of Channel Ban List\r\n"

    user_alice.sendall(b"MODE #foo -o Bob\r\n")
    receive_line(user_alice)

    user_alice.sendall(b"MODE #foo +ob Bob Charlie\r\n")
    assert receive_line(user_alice) == b":Alice!AliceUsr@127.0.0.1 MODE #foo +o Bob\r\n"
    assert receive_line(user_alice) == b":Alice!AliceUsr@127.0.0.1 MODE #foo +b Charlie!*@*\r\n"

    user_alice.sendall(b"MODE #foo -o Bob\r\n")
    user_alice.sendall(b"MODE #foo -b Charlie\r\n")
    receive_line(user_alice)
    receive_line(user_alice)

    user_alice.sendall(b"MODE #foo +bo Bob\r\n")
    assert receive_line(user_alice) == b":Alice!AliceUsr@127.0.0.1 MODE #foo +b Bob!*@*\r\n"
    assert receive_line(user_alice) == b":mantatail 461 Alice MODE :Not enough parameters\r\n"


def test_repeated_mode_messages(user_alice, user_bob):
    user_alice.sendall(b"JOIN #foo\r\n")
    time.sleep(0.1)
    user_bob.sendall(b"JOIN #foo\r\n")

    while receive_line(user_alice) != b":Bob!BobUsr@127.0.0.1 JOIN #foo\r\n":
        pass
    while receive_line(user_bob) != b":mantatail 366 Bob #foo :End of /NAMES list.\r\n":
        pass

    user_alice.sendall(b"MODE #foo +o Bob\r\n")
    assert receive_line(user_alice) == b":Alice!AliceUsr@127.0.0.1 MODE #foo +o Bob\r\n"
    assert receive_line(user_bob) == b":Alice!AliceUsr@127.0.0.1 MODE #foo +o Bob\r\n"

    user_alice.sendall(b"MODE #foo +o Bob\r\n")
    with pytest.raises(socket.timeout):
        receive_line(user_alice)
    with pytest.raises(socket.timeout):
        receive_line(user_bob)

    user_alice.sendall(b"MODE #foo +b Bob\r\n")
    assert receive_line(user_alice) == b":Alice!AliceUsr@127.0.0.1 MODE #foo +b Bob!*@*\r\n"
    assert receive_line(user_bob) == b":Alice!AliceUsr@127.0.0.1 MODE #foo +b Bob!*@*\r\n"

    user_alice.sendall(b"MODE #foo +b Bob\r\n")
    with pytest.raises(socket.timeout):
        receive_line(user_alice)
    with pytest.raises(socket.timeout):
        receive_line(user_bob)

    user_alice.sendall(b"MODE #foo -b Bob\r\n")
    assert receive_line(user_alice) == b":Alice!AliceUsr@127.0.0.1 MODE #foo -b Bob!*@*\r\n"
    assert receive_line(user_bob) == b":Alice!AliceUsr@127.0.0.1 MODE #foo -b Bob!*@*\r\n"

    user_alice.sendall(b"MODE #foo +b *!*@*\r\n")
    assert receive_line(user_alice) == b":Alice!AliceUsr@127.0.0.1 MODE #foo +b *!*@*\r\n"
    assert receive_line(user_bob) == b":Alice!AliceUsr@127.0.0.1 MODE #foo +b *!*@*\r\n"

    user_alice.sendall(b"MODE #foo +b Bob\r\n")
    with pytest.raises(socket.timeout):
        receive_line(user_alice)
    with pytest.raises(socket.timeout):
        receive_line(user_bob)


def test_mode_errors(user_alice, user_bob):
    user_alice.sendall(b"JOIN #foo\r\n")

    while receive_line(user_alice) != b":mantatail 366 Alice #foo :End of /NAMES list.\r\n":
        pass

    user_alice.sendall(b"MODE #foo ^g Bob\r\n")
    assert receive_line(user_alice) == b":mantatail 472 Alice ^ :is an unknown mode char to me\r\n"

    user_alice.sendall(b"MODE #foo +g Bob\r\n")
    assert receive_line(user_alice) == b":mantatail 472 Alice g :is an unknown mode char to me\r\n"

    user_bob.sendall(b"JOIN #foo\r\n")
    time.sleep(0.1)
    user_alice.sendall(b"MODE +o #foo Bob\r\n")
    while receive_line(user_alice) != b":mantatail 403 Alice +o :No such channel\r\n":
        pass

    user_alice.sendall(b"MODE Bob #foo +o\r\n")

    # TODO: The actual IRC error for this should be "502 Can't change mode for other users"
    # This will be implemented when MODE becomes more widely supported
    assert receive_line(user_alice) == b":mantatail 403 Alice Bob :No such channel\r\n"


def test_op_deop_user(user_alice, user_bob):
    user_alice.sendall(b"JOIN #foo\r\n")
    time.sleep(0.1)
    user_bob.sendall(b"JOIN #foo\r\n")

    while receive_line(user_alice) != b":Bob!BobUsr@127.0.0.1 JOIN #foo\r\n":
        pass
    while receive_line(user_bob) != b":mantatail 366 Bob #foo :End of /NAMES list.\r\n":
        pass

    user_alice.sendall(b"MODE #foo +o Bob\r\n")
    assert receive_line(user_alice) == b":Alice!AliceUsr@127.0.0.1 MODE #foo +o Bob\r\n"
    assert receive_line(user_bob) == b":Alice!AliceUsr@127.0.0.1 MODE #foo +o Bob\r\n"

    user_alice.sendall(b"MODE #foo -o Bob\r\n")
    assert receive_line(user_alice) == b":Alice!AliceUsr@127.0.0.1 MODE #foo -o Bob\r\n"
    assert receive_line(user_bob) == b":Alice!AliceUsr@127.0.0.1 MODE #foo -o Bob\r\n"


def test_channel_owner(user_alice, user_bob):
    user_alice.sendall(b"JOIN #foo\r\n")
    time.sleep(0.1)
    user_bob.sendall(b"JOIN #foo\r\n")

    while receive_line(user_alice) != b":mantatail 366 Alice #foo :End of /NAMES list.\r\n":
        pass

    while True:
        received = receive_line(user_bob)
        if b"353" in received:
            assert compare_if_word_match_in_any_order(received, b":mantatail 353 Bob = #foo :Bob @Alice\r\n")
            break

    user_alice.sendall(b"PART #foo\r\n")
    user_bob.sendall(b"PART #foo\r\n")
    time.sleep(0.1)
    user_bob.sendall(b"JOIN #foo\r\n")
    time.sleep(0.1)
    user_alice.sendall(b"JOIN #foo\r\n")

    while True:
        received = receive_line(user_alice)
        if b"353" in received:
            assert compare_if_word_match_in_any_order(received, b":mantatail 353 Alice = #foo :Alice @Bob\r\n")
            break


def test_operator_prefix(user_alice, user_bob, user_charlie):
    user_alice.sendall(b"JOIN #foo\r\n")
    receive_line(user_alice)  # JOIN message from server

    assert receive_line(user_alice) == b":mantatail 353 Alice = #foo :@Alice\r\n"

    user_bob.sendall(b"JOIN #foo\r\n")
    time.sleep(0.1)
    user_alice.sendall(b"MODE #foo +o Bob\r\n")
    time.sleep(0.1)
    user_charlie.sendall(b"JOIN #foo\r\n")

    while True:
        received = receive_line(user_charlie)
        if b"353" in received:
            assert compare_if_word_match_in_any_order(
                received, b":mantatail 353 Charlie = #foo :Charlie @Alice @Bob\r\n"
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
                received, b":mantatail 353 Charlie = #foo :Charlie @Alice Bob\r\n"
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
                received, b":mantatail 353 Charlie = #foo :Charlie @Alice @Bob\r\n"
            )
            break


def operator_nickchange_then_kick(user_alice, user_bob):
    user_alice.sendall(b"JOIN #foo\r\n")
    time.sleep(0.1)
    user_bob.sendall(b"JOIN #foo\r\n")

    while receive_line(user_alice) != b":Bob!BobUsr@127.0.0.1 JOIN #foo\r\n":
        pass
    while receive_line(user_bob) != b":mantatail 366 Bob #foo :End of /NAMES list.\r\n":
        pass

    user_alice.sendall(b"NICK :NewNick\r\n")
    receive_line(user_bob)
    user_alice.sendall(b"KICK #foo Bob")

    assert receive_line(user_bob) == b":NewNick!AliceUsr@127.0.0.1 KICK #foo Bob :Bob\r\n"

    user_bob.sendall(b"PRIVMSG #foo :Foo\r\n")
    assert receive_line(user_bob) == b":mantatail 442 #foo :You're not on that channel\r\n"


def test_operator_no_such_channel(user_alice):
    user_alice.sendall(b"MODE #foo +o Bob\r\n")
    assert receive_line(user_alice) == b":mantatail 403 Alice #foo :No such channel\r\n"


def test_operator_no_privileges(user_alice, user_bob):
    user_alice.sendall(b"JOIN #foo\r\n")
    time.sleep(0.1)
    user_bob.sendall(b"JOIN #foo\r\n")

    while receive_line(user_alice) != b":Bob!BobUsr@127.0.0.1 JOIN #foo\r\n":
        pass
    while receive_line(user_bob) != b":mantatail 366 Bob #foo :End of /NAMES list.\r\n":
        pass

    user_bob.sendall(b"MODE #foo +o Alice\r\n")
    assert receive_line(user_bob) == b":mantatail 482 Bob #foo :You're not channel operator\r\n"


def test_operator_user_not_in_channel(user_alice, user_bob):
    user_alice.sendall(b"JOIN #foo\r\n")

    while receive_line(user_alice) != b":mantatail 366 Alice #foo :End of /NAMES list.\r\n":
        pass

    user_alice.sendall(b"MODE #foo +o Bob\r\n")
    assert receive_line(user_alice) == b":mantatail 441 Alice Bob #foo :They aren't on that channel\r\n"


def test_kick_user(user_alice, user_bob):
    user_alice.sendall(b"JOIN #foo\r\n")
    time.sleep(0.1)
    user_bob.sendall(b"JOIN #foo\r\n")

    while receive_line(user_alice) != b":Bob!BobUsr@127.0.0.1 JOIN #foo\r\n":
        pass
    while receive_line(user_bob) != b":mantatail 366 Bob #foo :End of /NAMES list.\r\n":
        pass

    user_alice.sendall(b"KICK #foo Bob\r\n")

    assert receive_line(user_alice) == b":Alice!AliceUsr@127.0.0.1 KICK #foo Bob :Bob\r\n"
    assert receive_line(user_bob) == b":Alice!AliceUsr@127.0.0.1 KICK #foo Bob :Bob\r\n"

    user_bob.sendall(b"PRIVMSG #foo :Foo\r\n")
    assert receive_line(user_bob) == b":mantatail 442 Bob #foo :You're not on that channel\r\n"

    user_bob.sendall(b"JOIN #foo\r\n")

    while receive_line(user_alice) != b":Bob!BobUsr@127.0.0.1 JOIN #foo\r\n":
        pass
    while receive_line(user_bob) != b":mantatail 366 Bob #foo :End of /NAMES list.\r\n":
        pass

    user_alice.sendall(b"KICK #foo Bob Bye bye\r\n")

    assert receive_line(user_alice) == b":Alice!AliceUsr@127.0.0.1 KICK #foo Bob :Bye\r\n"
    assert receive_line(user_bob) == b":Alice!AliceUsr@127.0.0.1 KICK #foo Bob :Bye\r\n"

    user_bob.sendall(b"JOIN #foo\r\n")

    while receive_line(user_alice) != b":Bob!BobUsr@127.0.0.1 JOIN #foo\r\n":
        pass
    while receive_line(user_bob) != b":mantatail 366 Bob #foo :End of /NAMES list.\r\n":
        pass

    user_alice.sendall(b"KICK #foo Bob :Reason with many words\r\n")

    assert receive_line(user_alice) == b":Alice!AliceUsr@127.0.0.1 KICK #foo Bob :Reason with many words\r\n"
    assert receive_line(user_bob) == b":Alice!AliceUsr@127.0.0.1 KICK #foo Bob :Reason with many words\r\n"

    user_alice.sendall(b"KICK #foo Alice\r\n")

    assert receive_line(user_alice) == b":Alice!AliceUsr@127.0.0.1 KICK #foo Alice :Alice\r\n"

    user_alice.sendall(b"PRIVMSG #foo :Foo\r\n")

    while receive_line(user_alice) != b":mantatail 403 Alice #foo :No such channel\r\n":
        pass


def test_kick_operator(user_alice, user_bob):
    user_alice.sendall(b"JOIN #foo\r\n")
    time.sleep(0.1)
    user_bob.sendall(b"JOIN #foo\r\n")
    time.sleep(0.1)

    user_alice.sendall(b"MODE #foo +o Bob\r\n")
    while receive_line(user_alice) != b":Alice!AliceUsr@127.0.0.1 MODE #foo +o Bob\r\n":
        pass
    while receive_line(user_bob) != b":Alice!AliceUsr@127.0.0.1 MODE #foo +o Bob\r\n":
        pass

    user_alice.sendall(b"KICK #foo Bob\r\n")

    assert receive_line(user_alice) == b":Alice!AliceUsr@127.0.0.1 KICK #foo Bob :Bob\r\n"
    assert receive_line(user_bob) == b":Alice!AliceUsr@127.0.0.1 KICK #foo Bob :Bob\r\n"

    user_bob.sendall(b"PRIVMSG #foo :Foo\r\n")
    while receive_line(user_bob) != b":mantatail 442 Bob #foo :You're not on that channel\r\n":
        pass

    user_bob.sendall(b"JOIN #foo\r\n")

    while receive_line(user_alice) != b":Bob!BobUsr@127.0.0.1 JOIN #foo\r\n":
        pass
    while receive_line(user_bob) != b":mantatail 366 Bob #foo :End of /NAMES list.\r\n":
        pass

    user_bob.sendall(b"KICK #foo Alice\r\n")
    assert receive_line(user_bob) == b":mantatail 482 Bob #foo :You're not channel operator\r\n"


def test_ban_functionality(user_alice, user_bob, user_charlie):
    user_alice.sendall(b"JOIN #foo\r\n")
    time.sleep(0.1)
    user_bob.sendall(b"JOIN #foo\r\n")

    while receive_line(user_alice) != b":Bob!BobUsr@127.0.0.1 JOIN #foo\r\n":
        pass
    while receive_line(user_bob) != b":mantatail 366 Bob #foo :End of /NAMES list.\r\n":
        pass

    user_alice.sendall(b"MODE #foo +b Bob\r\n")
    assert receive_line(user_alice) == b":Alice!AliceUsr@127.0.0.1 MODE #foo +b Bob!*@*\r\n"
    assert receive_line(user_bob) == b":Alice!AliceUsr@127.0.0.1 MODE #foo +b Bob!*@*\r\n"

    user_bob.sendall(b"PRIVMSG #foo :This is a message\r\n")
    assert receive_line(user_bob) == b":mantatail 404 Bob #foo :Cannot send to nick/channel\r\n"

    user_bob.sendall(b"PART #foo\r\n")
    assert receive_line(user_bob) == b":Bob!BobUsr@127.0.0.1 PART #foo\r\n"
    assert receive_line(user_alice) == b":Bob!BobUsr@127.0.0.1 PART #foo\r\n"

    user_bob.sendall(b"JOIN #foo\r\n")
    assert receive_line(user_bob) == b":mantatail 474 Bob #foo :Cannot join channel (+b) - you are banned\r\n"
    time.sleep(0.1)

    user_alice.sendall(b"MODE #foo +b\r\n")
    assert receive_line(user_alice) == b":mantatail 367 Alice #foo Bob!*@* Alice!AliceUsr@127.0.0.1\r\n"
    assert receive_line(user_alice) == b":mantatail 368 Alice #foo :End of Channel Ban List\r\n"

    user_alice.sendall(b"MODE #foo -b Bob\r\n")
    assert receive_line(user_alice) == b":Alice!AliceUsr@127.0.0.1 MODE #foo -b Bob!*@*\r\n"

    user_bob.sendall(b"JOIN #foo\r\n")
    while receive_line(user_alice) != b":Bob!BobUsr@127.0.0.1 JOIN #foo\r\n":
        pass
    while receive_line(user_bob) != b":mantatail 366 Bob #foo :End of /NAMES list.\r\n":
        pass

    user_bob.sendall(b"MODE #foo +b Alice\r\n")
    assert receive_line(user_bob) == b":mantatail 482 Bob #foo :You're not channel operator\r\n"

    user_alice.sendall(b"MODE #foo +b BobUsr@\r\n")
    assert receive_line(user_alice) == b":Alice!AliceUsr@127.0.0.1 MODE #foo +b *!BobUsr@*\r\n"
    assert receive_line(user_bob) == b":Alice!AliceUsr@127.0.0.1 MODE #foo +b *!BobUsr@*\r\n"

    user_bob.sendall(b"PRIVMSG #foo :This is a message\r\n")
    assert receive_line(user_bob) == b":mantatail 404 Bob #foo :Cannot send to nick/channel\r\n"

    user_alice.sendall(b"MODE #foo +b @127.0.0.1\r\n")
    assert receive_line(user_alice) == b":Alice!AliceUsr@127.0.0.1 MODE #foo +b *!*@127.0.0.1\r\n"
    assert receive_line(user_bob) == b":Alice!AliceUsr@127.0.0.1 MODE #foo +b *!*@127.0.0.1\r\n"

    user_charlie.sendall(b"JOIN #foo\r\n")
    assert receive_line(user_charlie) == b":mantatail 474 Charlie #foo :Cannot join channel (+b) - you are banned\r\n"


# netcat sends \n line endings, but is fine receiving \r\n
def test_connect_via_netcat(run_server):
    with socket.socket() as nc:
        nc.connect(("localhost", 6667))  # nc localhost 6667
        nc.sendall(b"NICK nc\n")
        nc.sendall(b"USER nc 0 * :netcat\n")
        while receive_line(nc) != b":mantatail 376 nc :End of /MOTD command\r\n":
            pass


def test_cap_commands(run_server):
    nc = socket.socket()
    nc.connect(("localhost", 6667))

    nc.sendall(b"CAP\n")
    assert receive_line(nc) == b":mantatail 461 * CAP :Not enough parameters\r\n"

    nc.sendall(b"CAP LS\n")
    assert receive_line(nc) == b":mantatail CAP * LS :away-notify cap-notify\r\n"

    nc.sendall(b"CAP LIST\n")
    assert receive_line(nc) == b":mantatail CAP * LIST :\r\n"

    nc.sendall(b"CAP LS 302\n")
    assert receive_line(nc) == b":mantatail CAP * LS :away-notify cap-notify\r\n"

    nc.sendall(b"CAP LIST\n")
    assert receive_line(nc) == b":mantatail CAP * LIST :cap-notify\r\n"

    nc.sendall(b"NICK nc\n")
    nc.sendall(b"USER nc 0 * :netcat\n")

    with pytest.raises(socket.timeout):
        receive_line(nc)

    nc.sendall(b"CAP END\n")
    while receive_line(nc) != b":mantatail 376 nc :End of /MOTD command\r\n":
        pass


def test_cap_req(run_server):
    nc = socket.socket()
    nc.connect(("localhost", 6667))
    nc.sendall(b"CAP LS\n")
    assert receive_line(nc) == b":mantatail CAP * LS :away-notify cap-notify\r\n"

    nc.sendall(b"CAP REQ\n")
    with pytest.raises(socket.timeout):
        receive_line(nc)

    nc.sendall(b"CAP REQ foo\n")
    assert receive_line(nc) == b":mantatail CAP * NAK :foo\r\n"

    nc.sendall(b"CAP REQ foo bar\n")
    assert receive_line(nc) == b":mantatail CAP * NAK :foo\r\n"

    nc.sendall(b"CAP REQ :foo bar\n")
    assert receive_line(nc) == b":mantatail CAP * NAK :foo bar\r\n"

    nc.sendall(b"CAP REQ :foo cap-notify\n")
    assert receive_line(nc) == b":mantatail CAP * NAK :foo cap-notify\r\n"

    nc.sendall(b"CAP REQ :cap-notify\n")
    assert receive_line(nc) == b":mantatail CAP * ACK :cap-notify\r\n"

    nc.sendall(b"CAP LIST\n")
    assert receive_line(nc) == b":mantatail CAP * LIST :cap-notify\r\n"

    nc.sendall(b"CAP REQ :away-notify\n")
    assert receive_line(nc) == b":mantatail CAP * ACK :away-notify\r\n"

    nc.sendall(b"CAP LIST\n")

    while True:
        received = receive_line(nc)
        if b"LIST" in received:
            received_no_colons = received.replace(b":", b"")
            assert compare_if_word_match_in_any_order(
                received_no_colons, b"mantatail CAP * LIST cap-notify away-notify\r\n"
            )
            break


def test_away_notify(run_server):
    nc = socket.socket()
    nc.connect(("localhost", 6667))
    nc.sendall(b"CAP LS\n")
    assert receive_line(nc) == b":mantatail CAP * LS :away-notify cap-notify\r\n"

    nc.sendall(b"NICK nc\n")
    nc.sendall(b"USER nc 0 * :netcat\n")
    nc.sendall(b"CAP END\n")
    nc.sendall(b"JOIN #foo\n")

    while receive_line(nc) != b":mantatail 366 nc #foo :End of /NAMES list.\r\n":
        pass

    # Negotiates away-notify with server
    nc2 = socket.socket()
    nc2.connect(("localhost", 6667))
    nc2.sendall(b"CAP REQ away-notify\n")
    assert receive_line(nc2) == b":mantatail CAP * ACK :away-notify\r\n"
    nc2.sendall(b"NICK nc2\n")
    nc2.sendall(b"USER nc2 0 * :netcat\n")
    nc2.sendall(b"CAP END\n")
    nc2.sendall(b"JOIN #foo\n")

    while receive_line(nc2) != b":mantatail 366 nc2 #foo :End of /NAMES list.\r\n":
        pass

    # Does not negotiate with server
    nc3 = socket.socket()
    nc3.connect(("localhost", 6667))
    nc3.sendall(b"NICK nc3\n")
    nc3.sendall(b"USER nc3 0 * :netcat\n")
    nc3.sendall(b"JOIN #foo\n")

    while receive_line(nc3) != b":mantatail 366 nc3 #foo :End of /NAMES list.\r\n":
        pass

    # Join messages from other clients
    receive_line(nc)
    receive_line(nc2)

    time.sleep(0.1)

    nc.sendall(b"AWAY :This is an away message\n")

    assert receive_line(nc2) == b":nc!nc@127.0.0.1 AWAY :This is an away message\r\n"

    # Makes sure that nc3 doesn't receive an away message from nc
    with pytest.raises(socket.timeout):
        receive_line(nc3)

    nc4 = socket.socket()
    nc4.connect(("localhost", 6667))
    nc4.sendall(b"NICK nc4\n")
    nc4.sendall(b"USER nc4 0 * :netcat\n")

    nc4.sendall(b"AWAY :I am away\n")

    nc4.sendall(b"JOIN #foo\n")

    while receive_line(nc2) != b":nc4!nc4@127.0.0.1 AWAY :I am away\r\n":
        pass

    assert b"JOIN" in receive_line(nc3)  # nc4 JOIN message

    # Makes sure that nc3 doesn't receive an away message from nc
    with pytest.raises(socket.timeout):
        receive_line(nc3)


def test_quit_before_registering(run_server):
    with socket.socket() as nc:
        nc.connect(("localhost", 6667))  # nc localhost 6667
        nc.sendall(b"QUIT\n")
        assert receive_line(nc) == b":QUIT :Quit: Client quit\r\n"


def test_quit_reasons(run_server):
    nc = socket.socket()
    nc.connect(("localhost", 6667))
    nc.sendall(b"NICK nc\n")
    nc.sendall(b"USER nc 0 * :netcat\n")
    nc.sendall(b"JOIN #foo\n")

    while receive_line(nc) != b":mantatail 366 nc #foo :End of /NAMES list.\r\n":
        pass

    nc2 = socket.socket()
    nc2.connect(("localhost", 6667))
    nc2.sendall(b"NICK nc2\n")
    nc2.sendall(b"USER nc2 0 * :netcat\n")
    nc2.sendall(b"JOIN #foo\n")

    while receive_line(nc2) != b":mantatail 366 nc2 #foo :End of /NAMES list.\r\n":
        pass

    nc3 = socket.socket()
    nc3.connect(("localhost", 6667))
    nc3.sendall(b"NICK nc3\n")
    nc3.sendall(b"USER nc3 0 * :netcat\n")
    nc3.sendall(b"JOIN #foo\n")

    while receive_line(nc3) != b":mantatail 366 nc3 #foo :End of /NAMES list.\r\n":
        pass

    nc4 = socket.socket()
    nc4.connect(("localhost", 6667))
    nc4.sendall(b"NICK nc4\n")
    nc4.sendall(b"USER nc4 0 * :netcat\n")
    nc4.sendall(b"JOIN #foo\n")

    while receive_line(nc4) != b":mantatail 366 nc4 #foo :End of /NAMES list.\r\n":
        pass

    time.sleep(0.1)

    nc.sendall(b"QUIT\n")
    assert receive_line(nc4) == b":nc!nc@127.0.0.1 QUIT :Quit: Client quit\r\n"

    nc2.sendall(b"QUIT :Reason\n")
    assert receive_line(nc4) == b":nc2!nc2@127.0.0.1 QUIT :Quit: Reason\r\n"

    nc3.sendall(b"QUIT :Reason with many words\n")
    assert receive_line(nc4) == b":nc3!nc3@127.0.0.1 QUIT :Quit: Reason with many words\r\n"

    nc4.sendall(b"QUIT Many words but no colon\n")
    assert receive_line(nc4) == b":nc4!nc4@127.0.0.1 QUIT :Quit: Many\r\n"


def test_no_nickname_given(run_server):
    with socket.socket() as nc:
        nc.connect(("localhost", 6667))
        nc.sendall(b"NICK\r\n")
        assert receive_line(nc) == b":mantatail 431 :No nickname given\r\n"


def test_channel_owner_kick_self(run_server):
    """Checks that a channel is properly removed when a channel's last user (operator) kicks themselves."""
    with socket.socket() as nc:
        nc.connect(("localhost", 6667))
        nc.sendall(b"NICK nc\n")
        nc.sendall(b"USER nc 0 * :netcat\n")
        nc.sendall(b"JOIN #foo\n")

        while receive_line(nc) != b":mantatail 366 nc #foo :End of /NAMES list.\r\n":
            pass

        nc.sendall(b"KICK #foo nc\n")
        assert receive_line(nc) == b":nc!nc@127.0.0.1 KICK #foo nc :nc\r\n"

        nc.sendall(b"QUIT\n")

    with socket.socket() as nc:
        nc.connect(("localhost", 6667))
        nc.sendall(b"NICK nc\n")
        nc.sendall(b"USER nc 0 * :netcat\n")

        while receive_line(nc) != b":mantatail 376 nc :End of /MOTD command\r\n":
            pass

        nc.sendall(b"PART #foo\n")
        assert receive_line(nc) == b":mantatail 403 nc #foo :No such channel\r\n"

        nc.sendall(b"JOIN #foo\n")

        while receive_line(nc) != b":mantatail 366 nc #foo :End of /NAMES list.\r\n":
            pass

        nc.sendall(b"KICK #foo nc\n")
        assert receive_line(nc) == b":nc!nc@127.0.0.1 KICK #foo nc :nc\r\n"

        nc.sendall(b"QUIT\n")


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
    assert receive_line(nc2) == b":mantatail 433 * nc :Nickname is already in use\r\n"

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

    nc3 = socket.socket()
    nc3.connect(("localhost", 6667))
    nc3.sendall(b"NICK nc3\n")

    time.sleep(0.1)

    nc4 = socket.socket()
    nc4.connect(("localhost", 6667))
    nc4.sendall(b"NICK nc3\n")

    assert receive_line(nc4) == b":mantatail 433 * nc3 :Nickname is already in use\r\n"

    nc3.sendall(b"QUIT\r\n")
    while b"QUIT" not in receive_line(nc3):
        pass
    nc3.close()

    nc4.sendall(b"QUIT\r\n")
    while b"QUIT" not in receive_line(nc4):
        pass
    nc4.close()


def test_erroneus_nick(run_server):
    nc = socket.socket()
    nc.connect(("localhost", 6667))

    nc.sendall(b"NICK 123newnick\n")
    assert receive_line(nc) == b":mantatail 432 123newnick :Erroneous Nickname\r\n"

    nc.sendall(b"NICK /newnick\n")
    assert receive_line(nc) == b":mantatail 432 /newnick :Erroneous Nickname\r\n"

    nc.sendall(b"NICK newnick*\n")
    assert receive_line(nc) == b":mantatail 432 newnick* :Erroneous Nickname\r\n"


def test_sudden_disconnect(run_server):
    nc = socket.socket()
    nc.connect(("localhost", 6667))
    nc.sendall(b"NICK nc\n")
    nc.sendall(b"USER nc 0 * :netcat\n")
    nc.sendall(b"JOIN #foo\n")

    while receive_line(nc) != b":mantatail 366 nc #foo :End of /NAMES list.\r\n":
        pass

    nc2 = socket.socket()
    nc2.connect(("localhost", 6667))
    nc2.sendall(b"NICK nc2\n")
    nc2.sendall(b"USER nc2 0 * :netcat\n")
    nc2.sendall(b"JOIN #foo\n")

    while receive_line(nc2) != b":mantatail 366 nc2 #foo :End of /NAMES list.\r\n":
        pass

    nc.close()

    if sys.platform == "win32":
        # strerror is platform-specific, and also language specific on windows
        assert receive_line(nc2).startswith(b":nc!nc@127.0.0.1 QUIT :Quit: ")
    else:
        assert receive_line(nc2) == b":nc!nc@127.0.0.1 QUIT :Quit: Connection reset by peer\r\n"


# Issue #77
def test_disconnecting_without_sending_anything(user_alice):
    user_alice.send(b"JOIN #foo\r\n")
    time.sleep(0.1)
    nc = socket.socket()
    nc.connect(("localhost", 6667))
    nc.close()


def test_invalid_utf8(user_alice, user_bob):
    user_alice.sendall(b"JOIN #foo\r\n")
    time.sleep(0.1)
    user_bob.sendall(b"JOIN #foo\r\n")

    while receive_line(user_alice) != b":Bob!BobUsr@127.0.0.1 JOIN #foo\r\n":
        pass
    while receive_line(user_bob) != b":mantatail 366 Bob #foo :End of /NAMES list.\r\n":
        pass

    random_message = os.urandom(100).replace(b"\n", b"")
    user_alice.sendall(b"PRIVMSG #foo :" + random_message + b"\r\n")
    assert receive_line(user_bob) == b":Alice!AliceUsr@127.0.0.1 PRIVMSG #foo :" + random_message + b"\r\n"


def test_message_starting_with_colon(user_alice, user_bob):
    user_alice.sendall(b"JOIN #foo\r\n")
    time.sleep(0.1)
    user_bob.sendall(b"JOIN #foo\r\n")

    while receive_line(user_alice) != b":Bob!BobUsr@127.0.0.1 JOIN #foo\r\n":
        pass
    while receive_line(user_bob) != b":mantatail 366 Bob #foo :End of /NAMES list.\r\n":
        pass

    # Alice sends ":O lolwat" to Bob.
    # It is prefixed with a second ":" because of how IRC works.
    user_alice.sendall(b"PRIVMSG #foo ::O lolwat\r\n")
    assert receive_line(user_bob) == b":Alice!AliceUsr@127.0.0.1 PRIVMSG #foo ::O lolwat\r\n"

    # Alice sends ":O"
    user_alice.sendall(b"PRIVMSG #foo ::O\r\n")
    assert receive_line(user_bob) == b":Alice!AliceUsr@127.0.0.1 PRIVMSG #foo ::O\r\n"
