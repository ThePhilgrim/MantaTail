import os
import sys
import pytest
import random
import socket
import time

import server


def test_join_before_registering(run_server, helpers):
    user_socket = socket.socket()
    user_socket.connect(("localhost", 6667))
    user_socket.sendall(b"JOIN #foo\r\n")
    assert helpers.receive_line(user_socket) == b":mantatail 451 * :You have not registered\r\n"


def test_ping_message(monkeypatch, user_alice, helpers):
    monkeypatch.setattr(server, "TIMER_SECONDS", 2)
    user_alice.sendall(b"JOIN #foo\r\n")

    while helpers.receive_line(user_alice, 3) != b":mantatail PING :mantatail\r\n":
        pass

    user_alice.sendall(b"PONG :mantatail\r\n")


def test_join_channel(user_alice, user_bob, helpers):
    user_alice.sendall(b"JOIN #foo\r\n")
    time.sleep(0.1)
    user_bob.sendall(b"JOIN #foo\r\n")

    assert helpers.receive_line(user_bob) == b":Bob!BobUsr@127.0.0.1 JOIN #foo\r\n"

    while helpers.receive_line(user_bob) != b":mantatail 353 Bob = #foo :Bob @Alice\r\n":
        pass
    while helpers.receive_line(user_bob) != b":mantatail 366 Bob #foo :End of /NAMES list.\r\n":
        pass


def test_no_such_channel(user_alice, helpers):
    user_alice.sendall(b"PART #foo\r\n")
    assert helpers.receive_line(user_alice) == b":mantatail 403 Alice #foo :No such channel\r\n"


def test_youre_not_on_that_channel(user_alice, user_bob, helpers):
    user_alice.sendall(b"JOIN #foo\r\n")
    time.sleep(0.1)  # TODO: wait until server says that join is done
    user_bob.sendall(b"PART #foo\r\n")

    assert helpers.receive_line(user_bob) == b":mantatail 442 Bob #foo :You're not on that channel\r\n"


def test_nick_change(user_alice, user_bob, helpers):
    user_alice.sendall(b"JOIN #foo\r\n")
    time.sleep(0.1)
    user_bob.sendall(b"JOIN #foo\r\n")

    while helpers.receive_line(user_alice) != b":Bob!BobUsr@127.0.0.1 JOIN #foo\r\n":
        pass
    while helpers.receive_line(user_bob) != b":mantatail 366 Bob #foo :End of /NAMES list.\r\n":
        pass

    user_alice.sendall(b"NICK :NewNick\r\n")
    assert helpers.receive_line(user_alice) == b":Alice!AliceUsr@127.0.0.1 NICK :NewNick\r\n"
    assert helpers.receive_line(user_bob) == b":Alice!AliceUsr@127.0.0.1 NICK :NewNick\r\n"

    user_alice.sendall(b"PRIVMSG #foo :Alice should have a new user mask\r\n")
    assert (
        helpers.receive_line(user_bob)
        == b":NewNick!AliceUsr@127.0.0.1 PRIVMSG #foo :Alice should have a new user mask\r\n"
    )

    user_alice.sendall(b"NICK :NEWNICK\r\n")
    assert helpers.receive_line(user_alice) == b":NewNick!AliceUsr@127.0.0.1 NICK :NEWNICK\r\n"
    assert helpers.receive_line(user_bob) == b":NewNick!AliceUsr@127.0.0.1 NICK :NEWNICK\r\n"

    user_alice.sendall(b"NICK :NEWNICK\r\n")

    user_alice.sendall(b"PART #foo\r\n")

    # Assert instead of while helpers.receive_line() loop ensures nothing was sent from server after
    # changing to identical nick
    assert helpers.receive_line(user_alice) == b":NEWNICK!AliceUsr@127.0.0.1 PART #foo\r\n"


def test_send_privmsg(user_alice, user_bob, helpers):
    user_alice.sendall(b"JOIN #foo\r\n")
    time.sleep(0.1)
    user_bob.sendall(b"JOIN #foo\r\n")

    while helpers.receive_line(user_alice) != b":Bob!BobUsr@127.0.0.1 JOIN #foo\r\n":
        pass
    while helpers.receive_line(user_bob) != b":mantatail 366 Bob #foo :End of /NAMES list.\r\n":
        pass

    user_bob.sendall(b"PRIVMSG #foo :Foo\r\n")
    assert helpers.receive_line(user_alice) == b":Bob!BobUsr@127.0.0.1 PRIVMSG #foo :Foo\r\n"

    user_alice.sendall(b"PRIVMSG #foo Bar\r\n")
    assert helpers.receive_line(user_bob) == b":Alice!AliceUsr@127.0.0.1 PRIVMSG #foo :Bar\r\n"

    user_bob.sendall(b"PRIVMSG #foo :Foo Bar\r\n")
    assert helpers.receive_line(user_alice) == b":Bob!BobUsr@127.0.0.1 PRIVMSG #foo :Foo Bar\r\n"

    user_alice.sendall(b"PRIVMSG #foo Foo Bar\r\n")
    assert helpers.receive_line(user_bob) == b":Alice!AliceUsr@127.0.0.1 PRIVMSG #foo :Foo\r\n"


def test_away_status(user_alice, user_bob, helpers):
    user_alice.sendall(b"PRIVMSG Bob :Hello Bob\r\n")
    assert helpers.receive_line(user_bob) == b":Alice!AliceUsr@127.0.0.1 PRIVMSG Bob :Hello Bob\r\n"

    # Makes sure that Alice doesn't receive an away message from Bob
    with pytest.raises(socket.timeout):
        helpers.receive_line(user_alice)

    user_bob.sendall(b"AWAY\r\n")
    assert helpers.receive_line(user_bob) == b":mantatail 305 Bob :You are no longer marked as being away\r\n"

    # Makes sure UNAWAY (306) is only sent to Bob
    with pytest.raises(socket.timeout):
        helpers.receive_line(user_alice)

    user_bob.sendall(b"AWAY :This is an away status\r\n")
    assert helpers.receive_line(user_bob) == b":mantatail 306 Bob :You have been marked as being away\r\n"

    # Makes sure NOWAWAY (305) is only sent to Bob
    with pytest.raises(socket.timeout):
        helpers.receive_line(user_alice)

    user_alice.sendall(b"PRIVMSG Bob :Hello Bob\r\n")
    assert helpers.receive_line(user_bob) == b":Alice!AliceUsr@127.0.0.1 PRIVMSG Bob :Hello Bob\r\n"

    assert helpers.receive_line(user_alice) == b":mantatail 301 Alice Bob :This is an away status\r\n"

    user_bob.sendall(b"AWAY\r\n")
    assert helpers.receive_line(user_bob) == b":mantatail 305 Bob :You are no longer marked as being away\r\n"

    user_bob.sendall(b"AWAY This is an away status\r\n")
    assert helpers.receive_line(user_bob) == b":mantatail 306 Bob :You have been marked as being away\r\n"

    user_alice.sendall(b"PRIVMSG Bob :Hello Bob\r\n")
    assert helpers.receive_line(user_bob) == b":Alice!AliceUsr@127.0.0.1 PRIVMSG Bob :Hello Bob\r\n"

    assert helpers.receive_line(user_alice) == b":mantatail 301 Alice Bob :This\r\n"


def test_channel_topics(user_alice, user_bob, user_charlie, helpers):
    user_alice.sendall(b"JOIN #foo\r\n")
    time.sleep(0.1)
    user_bob.sendall(b"JOIN #foo\r\n")

    while True:
        received = helpers.receive_line(user_alice)
        assert b"332" not in received
        assert b"333" not in received
        if received == b":Bob!BobUsr@127.0.0.1 JOIN #foo\r\n":
            break

    while helpers.receive_line(user_bob) != b":mantatail 366 Bob #foo :End of /NAMES list.\r\n":
        pass

    user_alice.sendall(b"TOPIC\r\n")
    assert helpers.receive_line(user_alice) == b":mantatail 461 Alice TOPIC :Not enough parameters\r\n"

    user_alice.sendall(b"TOPIC #foo\r\n")
    assert helpers.receive_line(user_alice) == b":mantatail 331 Alice #foo :No topic is set.\r\n"

    user_alice.sendall(b"TOPIC #foo :This is a topic\r\n")
    assert helpers.receive_line(user_alice) == b":Alice!AliceUsr@127.0.0.1 TOPIC #foo :This is a topic\r\n"
    assert helpers.receive_line(user_bob) == b":Alice!AliceUsr@127.0.0.1 TOPIC #foo :This is a topic\r\n"

    time.sleep(0.1)
    user_charlie.sendall(b"JOIN #foo\r\n")
    helpers.receive_line(user_charlie)
    assert helpers.receive_line(user_charlie) == b":mantatail 332 Charlie #foo :This is a topic\r\n"
    assert helpers.receive_line(user_charlie) == b":mantatail 333 Charlie #foo :Alice\r\n"

    user_alice.sendall(b"TOPIC #foo\r\n")
    helpers.receive_line(user_alice)  # Charlie's JOIN message
    assert helpers.receive_line(user_alice) == b":mantatail 332 Alice #foo :This is a topic\r\n"
    assert helpers.receive_line(user_alice) == b":mantatail 333 Alice #foo :Alice\r\n"

    user_bob.sendall(b"TOPIC #foo\r\n")
    helpers.receive_line(user_bob)  # Charlie's JOIN message
    assert helpers.receive_line(user_bob) == b":mantatail 332 Bob #foo :This is a topic\r\n"
    assert helpers.receive_line(user_bob) == b":mantatail 333 Bob #foo :Alice\r\n"

    user_bob.sendall(b"TOPIC #foo :Bob is setting a topic\r\n")
    assert helpers.receive_line(user_bob) == b":mantatail 482 Bob #foo :You're not channel operator\r\n"

    user_bob.sendall(b"TOPIC #foo :\r\n")
    assert helpers.receive_line(user_bob) == b":mantatail 482 Bob #foo :You're not channel operator\r\n"

    user_alice.sendall(b"TOPIC #foo :\r\n")
    assert helpers.receive_line(user_alice) == b":Alice!AliceUsr@127.0.0.1 TOPIC #foo :\r\n"
    assert helpers.receive_line(user_bob) == b":Alice!AliceUsr@127.0.0.1 TOPIC #foo :\r\n"

    user_alice.sendall(b"TOPIC #foo\r\n")
    assert helpers.receive_line(user_alice) == b":mantatail 331 Alice #foo :No topic is set.\r\n"
    user_bob.sendall(b"TOPIC #foo\r\n")
    assert helpers.receive_line(user_bob) == b":mantatail 331 Bob #foo :No topic is set.\r\n"


def test_send_privmsg_to_user(user_alice, user_bob, helpers):
    user_alice.sendall(b"PRIVMSG Bob :This is a private message\r\n")
    assert helpers.receive_line(user_bob) == b":Alice!AliceUsr@127.0.0.1 PRIVMSG Bob :This is a private message\r\n"

    user_bob.sendall(b"PRIVMSG alice :This is a reply\r\n")
    assert helpers.receive_line(user_alice) == b":Bob!BobUsr@127.0.0.1 PRIVMSG Alice :This is a reply\r\n"


def test_privmsg_error_messages(user_alice, user_bob, helpers):
    user_alice.sendall(b"JOIN #foo\r\n")
    while helpers.receive_line(user_alice) != b":mantatail 366 Alice #foo :End of /NAMES list.\r\n":
        pass
    time.sleep(0.1)

    user_bob.sendall(b"PRIVMSG #foo :Bar\r\n")
    assert helpers.receive_line(user_bob) == b":mantatail 442 Bob #foo :You're not on that channel\r\n"

    user_bob.sendall(b"PRIVMSG #bar :Baz\r\n")
    assert helpers.receive_line(user_bob) == b":mantatail 403 Bob #bar :No such channel\r\n"

    user_alice.sendall(b"PRIVMSG\r\n")
    assert helpers.receive_line(user_alice) == b":mantatail 411 Alice :No recipient given (PRIVMSG)\r\n"

    user_alice.sendall(b"PRIVMSG #foo\r\n")
    assert helpers.receive_line(user_alice) == b":mantatail 412 Alice :No text to send\r\n"

    user_alice.sendall(b"PRIVMSG Charlie :This is a private message\r\n")
    assert helpers.receive_line(user_alice) == b":mantatail 401 Alice Charlie :No such nick/channel\r\n"


def test_not_enough_params_error(user_alice, helpers):
    user_alice.sendall(b"JOIN\r\n")
    assert helpers.receive_line(user_alice) == b":mantatail 461 Alice JOIN :Not enough parameters\r\n"

    user_alice.sendall(b"JOIN #foo\r\n")
    while helpers.receive_line(user_alice) != b":mantatail 366 Alice #foo :End of /NAMES list.\r\n":
        pass

    user_alice.sendall(b"part\r\n")
    assert helpers.receive_line(user_alice) == b":mantatail 461 Alice PART :Not enough parameters\r\n"

    user_alice.sendall(b"Mode\r\n")
    assert helpers.receive_line(user_alice) == b":mantatail 461 Alice MODE :Not enough parameters\r\n"

    user_alice.sendall(b"KICK\r\n")
    assert helpers.receive_line(user_alice) == b":mantatail 461 Alice KICK :Not enough parameters\r\n"

    user_alice.sendall(b"KICK Bob\r\n")
    assert helpers.receive_line(user_alice) == b":mantatail 461 Alice KICK :Not enough parameters\r\n"

    nc = socket.socket()
    nc.connect(("localhost", 6667))

    nc.sendall(b"USER\n")
    assert helpers.receive_line(nc) == b":mantatail 461 * USER :Not enough parameters\r\n"

    nc.sendall(b"QUIT\r\n")
    while b"QUIT" not in helpers.receive_line(nc):
        pass
    nc.close()


def test_send_unknown_commands(user_alice, helpers):
    user_alice.sendall(b"FOO\r\n")
    assert helpers.receive_line(user_alice) == b":mantatail 421 Alice FOO :Unknown command\r\n"
    user_alice.sendall(b"Bar\r\n")
    assert helpers.receive_line(user_alice) == b":mantatail 421 Alice Bar :Unknown command\r\n"
    user_alice.sendall(b"baz\r\n")
    assert helpers.receive_line(user_alice) == b":mantatail 421 Alice baz :Unknown command\r\n"
    user_alice.sendall(b"&/!\r\n")
    assert helpers.receive_line(user_alice) == b":mantatail 421 Alice &/! :Unknown command\r\n"


def test_channel_mode_is(user_alice, helpers):
    user_alice.sendall(b"JOIN #foo\r\n")

    while helpers.receive_line(user_alice) != b":mantatail 366 Alice #foo :End of /NAMES list.\r\n":
        pass

    user_alice.sendall(b"MODE #foo\r\n")
    assert helpers.receive_line(user_alice) == b":mantatail 324 Alice #foo +t\r\n"


def test_mode_several_flags(user_alice, user_bob, user_charlie, helpers):
    user_alice.sendall(b"JOIN #foo\r\n")
    time.sleep(0.1)
    user_bob.sendall(b"JOIN #foo\r\n")
    time.sleep(0.1)
    user_charlie.sendall(b"JOIN #foo\r\n")

    while helpers.receive_line(user_alice) != b":Charlie!CharlieUsr@127.0.0.1 JOIN #foo\r\n":
        pass
    while helpers.receive_line(user_bob) != b":Charlie!CharlieUsr@127.0.0.1 JOIN #foo\r\n":
        pass
    while helpers.receive_line(user_charlie) != b":mantatail 366 Charlie #foo :End of /NAMES list.\r\n":
        pass

    user_alice.sendall(b"MODE #foo +ob Bob\r\n")

    assert helpers.receive_line(user_alice) == b":Alice!AliceUsr@127.0.0.1 MODE #foo +o Bob\r\n"
    assert helpers.receive_line(user_alice) == b":mantatail 368 Alice #foo :End of Channel Ban List\r\n"

    user_alice.sendall(b"MODE #foo -o Bob\r\n")
    helpers.receive_line(user_alice)

    user_alice.sendall(b"MODE #foo +ob Bob Charlie\r\n")
    assert helpers.receive_line(user_alice) == b":Alice!AliceUsr@127.0.0.1 MODE #foo +o Bob\r\n"
    assert helpers.receive_line(user_alice) == b":Alice!AliceUsr@127.0.0.1 MODE #foo +b Charlie!*@*\r\n"

    user_alice.sendall(b"MODE #foo -o Bob\r\n")
    user_alice.sendall(b"MODE #foo -b Charlie\r\n")
    helpers.receive_line(user_alice)
    helpers.receive_line(user_alice)

    user_alice.sendall(b"MODE #foo +bo Bob\r\n")
    assert helpers.receive_line(user_alice) == b":Alice!AliceUsr@127.0.0.1 MODE #foo +b Bob!*@*\r\n"
    assert helpers.receive_line(user_alice) == b":mantatail 461 Alice MODE :Not enough parameters\r\n"


def test_repeated_mode_messages(user_alice, user_bob, helpers):
    user_alice.sendall(b"JOIN #foo\r\n")
    time.sleep(0.1)
    user_bob.sendall(b"JOIN #foo\r\n")

    while helpers.receive_line(user_alice) != b":Bob!BobUsr@127.0.0.1 JOIN #foo\r\n":
        pass
    while helpers.receive_line(user_bob) != b":mantatail 366 Bob #foo :End of /NAMES list.\r\n":
        pass

    user_alice.sendall(b"MODE #foo +o Bob\r\n")
    assert helpers.receive_line(user_alice) == b":Alice!AliceUsr@127.0.0.1 MODE #foo +o Bob\r\n"
    assert helpers.receive_line(user_bob) == b":Alice!AliceUsr@127.0.0.1 MODE #foo +o Bob\r\n"

    user_alice.sendall(b"MODE #foo +o Bob\r\n")
    with pytest.raises(socket.timeout):
        helpers.receive_line(user_alice)
    with pytest.raises(socket.timeout):
        helpers.receive_line(user_bob)

    user_alice.sendall(b"MODE #foo +b Bob\r\n")
    assert helpers.receive_line(user_alice) == b":Alice!AliceUsr@127.0.0.1 MODE #foo +b Bob!*@*\r\n"
    assert helpers.receive_line(user_bob) == b":Alice!AliceUsr@127.0.0.1 MODE #foo +b Bob!*@*\r\n"

    user_alice.sendall(b"MODE #foo +b Bob\r\n")
    with pytest.raises(socket.timeout):
        helpers.receive_line(user_alice)
    with pytest.raises(socket.timeout):
        helpers.receive_line(user_bob)

    user_alice.sendall(b"MODE #foo -b Bob\r\n")
    assert helpers.receive_line(user_alice) == b":Alice!AliceUsr@127.0.0.1 MODE #foo -b Bob!*@*\r\n"
    assert helpers.receive_line(user_bob) == b":Alice!AliceUsr@127.0.0.1 MODE #foo -b Bob!*@*\r\n"

    user_alice.sendall(b"MODE #foo +b *!*@*\r\n")
    assert helpers.receive_line(user_alice) == b":Alice!AliceUsr@127.0.0.1 MODE #foo +b *!*@*\r\n"
    assert helpers.receive_line(user_bob) == b":Alice!AliceUsr@127.0.0.1 MODE #foo +b *!*@*\r\n"

    user_alice.sendall(b"MODE #foo +b Bob\r\n")
    with pytest.raises(socket.timeout):
        helpers.receive_line(user_alice)
    with pytest.raises(socket.timeout):
        helpers.receive_line(user_bob)


def test_mode_errors(user_alice, user_bob, helpers):
    user_alice.sendall(b"JOIN #foo\r\n")

    while helpers.receive_line(user_alice) != b":mantatail 366 Alice #foo :End of /NAMES list.\r\n":
        pass

    user_alice.sendall(b"MODE #foo ^g Bob\r\n")
    assert helpers.receive_line(user_alice) == b":mantatail 472 Alice ^ :is an unknown mode char to me\r\n"

    user_alice.sendall(b"MODE #foo +g Bob\r\n")
    assert helpers.receive_line(user_alice) == b":mantatail 472 Alice g :is an unknown mode char to me\r\n"

    user_bob.sendall(b"JOIN #foo\r\n")
    time.sleep(0.1)
    user_alice.sendall(b"MODE +o #foo Bob\r\n")
    while helpers.receive_line(user_alice) != b":mantatail 403 Alice +o :No such channel\r\n":
        pass

    user_alice.sendall(b"MODE Bob #foo +o\r\n")

    # TODO: The actual IRC error for this should be "502 Can't change mode for other users"
    # This will be implemented when MODE becomes more widely supported
    assert helpers.receive_line(user_alice) == b":mantatail 403 Alice Bob :No such channel\r\n"


def test_op_deop_user(user_alice, user_bob, helpers):
    user_alice.sendall(b"JOIN #foo\r\n")
    time.sleep(0.1)
    user_bob.sendall(b"JOIN #foo\r\n")

    while helpers.receive_line(user_alice) != b":Bob!BobUsr@127.0.0.1 JOIN #foo\r\n":
        pass
    while helpers.receive_line(user_bob) != b":mantatail 366 Bob #foo :End of /NAMES list.\r\n":
        pass

    user_alice.sendall(b"MODE #foo +o Bob\r\n")
    assert helpers.receive_line(user_alice) == b":Alice!AliceUsr@127.0.0.1 MODE #foo +o Bob\r\n"
    assert helpers.receive_line(user_bob) == b":Alice!AliceUsr@127.0.0.1 MODE #foo +o Bob\r\n"

    user_alice.sendall(b"MODE #foo -o Bob\r\n")
    assert helpers.receive_line(user_alice) == b":Alice!AliceUsr@127.0.0.1 MODE #foo -o Bob\r\n"
    assert helpers.receive_line(user_bob) == b":Alice!AliceUsr@127.0.0.1 MODE #foo -o Bob\r\n"


def test_channel_owner(user_alice, user_bob, helpers):
    user_alice.sendall(b"JOIN #foo\r\n")
    time.sleep(0.1)
    user_bob.sendall(b"JOIN #foo\r\n")

    while helpers.receive_line(user_alice) != b":mantatail 366 Alice #foo :End of /NAMES list.\r\n":
        pass

    while True:
        received = helpers.receive_line(user_bob)
        if b"353" in received:
            assert helpers.compare_if_word_match_in_any_order(received, b":mantatail 353 Bob = #foo :Bob @Alice\r\n")
            break

    user_alice.sendall(b"PART #foo\r\n")
    user_bob.sendall(b"PART #foo\r\n")
    time.sleep(0.1)
    user_bob.sendall(b"JOIN #foo\r\n")
    time.sleep(0.1)
    user_alice.sendall(b"JOIN #foo\r\n")

    while True:
        received = helpers.receive_line(user_alice)
        if b"353" in received:
            assert helpers.compare_if_word_match_in_any_order(received, b":mantatail 353 Alice = #foo :Alice @Bob\r\n")
            break


def test_operator_prefix(user_alice, user_bob, user_charlie, helpers):
    user_alice.sendall(b"JOIN #foo\r\n")
    helpers.receive_line(user_alice)  # JOIN message from server

    assert helpers.receive_line(user_alice) == b":mantatail 353 Alice = #foo :@Alice\r\n"

    user_bob.sendall(b"JOIN #foo\r\n")
    time.sleep(0.1)
    user_alice.sendall(b"MODE #foo +o Bob\r\n")
    time.sleep(0.1)
    user_charlie.sendall(b"JOIN #foo\r\n")

    while True:
        received = helpers.receive_line(user_charlie)
        if b"353" in received:
            assert helpers.compare_if_word_match_in_any_order(
                received, b":mantatail 353 Charlie = #foo :Charlie @Alice @Bob\r\n"
            )
            break

    user_charlie.sendall(b"PART #foo\r\n")
    user_alice.sendall(b"MODE #foo -o Bob\r\n")
    time.sleep(0.1)
    user_charlie.sendall(b"JOIN #foo\r\n")

    while True:
        received = helpers.receive_line(user_charlie)
        if b"353" in received:
            assert helpers.compare_if_word_match_in_any_order(
                received, b":mantatail 353 Charlie = #foo :Charlie @Alice Bob\r\n"
            )
            break

    user_charlie.sendall(b"PART #foo\r\n")
    user_alice.sendall(b"MODE #foo +o Bob\r\n")
    time.sleep(0.1)
    user_charlie.sendall(b"JOIN #foo\r\n")

    while True:
        received = helpers.receive_line(user_charlie)
        if b"353" in received:
            assert helpers.compare_if_word_match_in_any_order(
                received, b":mantatail 353 Charlie = #foo :Charlie @Alice @Bob\r\n"
            )
            break


def operator_nickchange_then_kick(user_alice, user_bob, helpers):
    user_alice.sendall(b"JOIN #foo\r\n")
    time.sleep(0.1)
    user_bob.sendall(b"JOIN #foo\r\n")

    while helpers.receive_line(user_alice) != b":Bob!BobUsr@127.0.0.1 JOIN #foo\r\n":
        pass
    while helpers.receive_line(user_bob) != b":mantatail 366 Bob #foo :End of /NAMES list.\r\n":
        pass

    user_alice.sendall(b"NICK :NewNick\r\n")
    helpers.receive_line(user_bob)
    user_alice.sendall(b"KICK #foo Bob")

    assert helpers.receive_line(user_bob) == b":NewNick!AliceUsr@127.0.0.1 KICK #foo Bob :Bob\r\n"

    user_bob.sendall(b"PRIVMSG #foo :Foo\r\n")
    assert helpers.receive_line(user_bob) == b":mantatail 442 #foo :You're not on that channel\r\n"


def test_operator_no_such_channel(user_alice, helpers):
    user_alice.sendall(b"MODE #foo +o Bob\r\n")
    assert helpers.receive_line(user_alice) == b":mantatail 403 Alice #foo :No such channel\r\n"


def test_operator_no_privileges(user_alice, user_bob, helpers):
    user_alice.sendall(b"JOIN #foo\r\n")
    time.sleep(0.1)
    user_bob.sendall(b"JOIN #foo\r\n")

    while helpers.receive_line(user_alice) != b":Bob!BobUsr@127.0.0.1 JOIN #foo\r\n":
        pass
    while helpers.receive_line(user_bob) != b":mantatail 366 Bob #foo :End of /NAMES list.\r\n":
        pass

    user_bob.sendall(b"MODE #foo +o Alice\r\n")
    assert helpers.receive_line(user_bob) == b":mantatail 482 Bob #foo :You're not channel operator\r\n"


def test_operator_user_not_in_channel(user_alice, user_bob, helpers):
    user_alice.sendall(b"JOIN #foo\r\n")

    while helpers.receive_line(user_alice) != b":mantatail 366 Alice #foo :End of /NAMES list.\r\n":
        pass

    user_alice.sendall(b"MODE #foo +o Bob\r\n")
    assert helpers.receive_line(user_alice) == b":mantatail 441 Alice Bob #foo :They aren't on that channel\r\n"


def test_kick_user(user_alice, user_bob, helpers):
    user_alice.sendall(b"JOIN #foo\r\n")
    time.sleep(0.1)
    user_bob.sendall(b"JOIN #foo\r\n")

    while helpers.receive_line(user_alice) != b":Bob!BobUsr@127.0.0.1 JOIN #foo\r\n":
        pass
    while helpers.receive_line(user_bob) != b":mantatail 366 Bob #foo :End of /NAMES list.\r\n":
        pass

    user_alice.sendall(b"KICK #foo Bob\r\n")

    assert helpers.receive_line(user_alice) == b":Alice!AliceUsr@127.0.0.1 KICK #foo Bob :Bob\r\n"
    assert helpers.receive_line(user_bob) == b":Alice!AliceUsr@127.0.0.1 KICK #foo Bob :Bob\r\n"

    user_bob.sendall(b"PRIVMSG #foo :Foo\r\n")
    assert helpers.receive_line(user_bob) == b":mantatail 442 Bob #foo :You're not on that channel\r\n"

    user_bob.sendall(b"JOIN #foo\r\n")

    while helpers.receive_line(user_alice) != b":Bob!BobUsr@127.0.0.1 JOIN #foo\r\n":
        pass
    while helpers.receive_line(user_bob) != b":mantatail 366 Bob #foo :End of /NAMES list.\r\n":
        pass

    user_alice.sendall(b"KICK #foo Bob Bye bye\r\n")

    assert helpers.receive_line(user_alice) == b":Alice!AliceUsr@127.0.0.1 KICK #foo Bob :Bye\r\n"
    assert helpers.receive_line(user_bob) == b":Alice!AliceUsr@127.0.0.1 KICK #foo Bob :Bye\r\n"

    user_bob.sendall(b"JOIN #foo\r\n")

    while helpers.receive_line(user_alice) != b":Bob!BobUsr@127.0.0.1 JOIN #foo\r\n":
        pass
    while helpers.receive_line(user_bob) != b":mantatail 366 Bob #foo :End of /NAMES list.\r\n":
        pass

    user_alice.sendall(b"KICK #foo Bob :Reason with many words\r\n")

    assert helpers.receive_line(user_alice) == b":Alice!AliceUsr@127.0.0.1 KICK #foo Bob :Reason with many words\r\n"
    assert helpers.receive_line(user_bob) == b":Alice!AliceUsr@127.0.0.1 KICK #foo Bob :Reason with many words\r\n"

    user_alice.sendall(b"KICK #foo Alice\r\n")

    assert helpers.receive_line(user_alice) == b":Alice!AliceUsr@127.0.0.1 KICK #foo Alice :Alice\r\n"

    user_alice.sendall(b"PRIVMSG #foo :Foo\r\n")

    while helpers.receive_line(user_alice) != b":mantatail 403 Alice #foo :No such channel\r\n":
        pass


def test_kick_operator(user_alice, user_bob, helpers):
    user_alice.sendall(b"JOIN #foo\r\n")
    time.sleep(0.1)
    user_bob.sendall(b"JOIN #foo\r\n")
    time.sleep(0.1)

    user_alice.sendall(b"MODE #foo +o Bob\r\n")
    while helpers.receive_line(user_alice) != b":Alice!AliceUsr@127.0.0.1 MODE #foo +o Bob\r\n":
        pass
    while helpers.receive_line(user_bob) != b":Alice!AliceUsr@127.0.0.1 MODE #foo +o Bob\r\n":
        pass

    user_alice.sendall(b"KICK #foo Bob\r\n")

    assert helpers.receive_line(user_alice) == b":Alice!AliceUsr@127.0.0.1 KICK #foo Bob :Bob\r\n"
    assert helpers.receive_line(user_bob) == b":Alice!AliceUsr@127.0.0.1 KICK #foo Bob :Bob\r\n"

    user_bob.sendall(b"PRIVMSG #foo :Foo\r\n")
    while helpers.receive_line(user_bob) != b":mantatail 442 Bob #foo :You're not on that channel\r\n":
        pass

    user_bob.sendall(b"JOIN #foo\r\n")

    while helpers.receive_line(user_alice) != b":Bob!BobUsr@127.0.0.1 JOIN #foo\r\n":
        pass
    while helpers.receive_line(user_bob) != b":mantatail 366 Bob #foo :End of /NAMES list.\r\n":
        pass

    user_bob.sendall(b"KICK #foo Alice\r\n")
    assert helpers.receive_line(user_bob) == b":mantatail 482 Bob #foo :You're not channel operator\r\n"


def test_ban_functionality(user_alice, user_bob, user_charlie, helpers):
    user_alice.sendall(b"JOIN #foo\r\n")
    time.sleep(0.1)
    user_bob.sendall(b"JOIN #foo\r\n")

    while helpers.receive_line(user_alice) != b":Bob!BobUsr@127.0.0.1 JOIN #foo\r\n":
        pass
    while helpers.receive_line(user_bob) != b":mantatail 366 Bob #foo :End of /NAMES list.\r\n":
        pass

    user_alice.sendall(b"MODE #foo +b Bob\r\n")
    assert helpers.receive_line(user_alice) == b":Alice!AliceUsr@127.0.0.1 MODE #foo +b Bob!*@*\r\n"
    assert helpers.receive_line(user_bob) == b":Alice!AliceUsr@127.0.0.1 MODE #foo +b Bob!*@*\r\n"

    user_bob.sendall(b"PRIVMSG #foo :This is a message\r\n")
    assert helpers.receive_line(user_bob) == b":mantatail 404 Bob #foo :Cannot send to nick/channel\r\n"

    user_bob.sendall(b"PART #foo\r\n")
    assert helpers.receive_line(user_bob) == b":Bob!BobUsr@127.0.0.1 PART #foo\r\n"
    assert helpers.receive_line(user_alice) == b":Bob!BobUsr@127.0.0.1 PART #foo\r\n"

    user_bob.sendall(b"JOIN #foo\r\n")
    assert helpers.receive_line(user_bob) == b":mantatail 474 Bob #foo :Cannot join channel (+b) - you are banned\r\n"
    time.sleep(0.1)

    user_alice.sendall(b"MODE #foo +b\r\n")
    assert helpers.receive_line(user_alice) == b":mantatail 367 Alice #foo Bob!*@* Alice!AliceUsr@127.0.0.1\r\n"
    assert helpers.receive_line(user_alice) == b":mantatail 368 Alice #foo :End of Channel Ban List\r\n"

    user_alice.sendall(b"MODE #foo -b Bob\r\n")
    assert helpers.receive_line(user_alice) == b":Alice!AliceUsr@127.0.0.1 MODE #foo -b Bob!*@*\r\n"

    user_bob.sendall(b"JOIN #foo\r\n")
    while helpers.receive_line(user_alice) != b":Bob!BobUsr@127.0.0.1 JOIN #foo\r\n":
        pass
    while helpers.receive_line(user_bob) != b":mantatail 366 Bob #foo :End of /NAMES list.\r\n":
        pass

    user_bob.sendall(b"MODE #foo +b Alice\r\n")
    assert helpers.receive_line(user_bob) == b":mantatail 482 Bob #foo :You're not channel operator\r\n"

    user_alice.sendall(b"MODE #foo +b BobUsr@\r\n")
    assert helpers.receive_line(user_alice) == b":Alice!AliceUsr@127.0.0.1 MODE #foo +b *!BobUsr@*\r\n"
    assert helpers.receive_line(user_bob) == b":Alice!AliceUsr@127.0.0.1 MODE #foo +b *!BobUsr@*\r\n"

    user_bob.sendall(b"PRIVMSG #foo :This is a message\r\n")
    assert helpers.receive_line(user_bob) == b":mantatail 404 Bob #foo :Cannot send to nick/channel\r\n"

    user_alice.sendall(b"MODE #foo +b @127.0.0.1\r\n")
    assert helpers.receive_line(user_alice) == b":Alice!AliceUsr@127.0.0.1 MODE #foo +b *!*@127.0.0.1\r\n"
    assert helpers.receive_line(user_bob) == b":Alice!AliceUsr@127.0.0.1 MODE #foo +b *!*@127.0.0.1\r\n"

    user_charlie.sendall(b"JOIN #foo\r\n")
    assert (
        helpers.receive_line(user_charlie)
        == b":mantatail 474 Charlie #foo :Cannot join channel (+b) - you are banned\r\n"
    )


# netcat sends \n line endings, but is fine receiving \r\n
def test_connect_via_netcat(run_server, helpers):
    with socket.socket() as nc:
        nc.connect(("localhost", 6667))  # nc localhost 6667
        nc.sendall(b"NICK nc\n")
        nc.sendall(b"USER nc 0 * :netcat\n")
        while helpers.receive_line(nc) != b":mantatail 376 nc :End of /MOTD command\r\n":
            pass


def test_cap_commands(run_server, helpers):
    nc = socket.socket()
    nc.connect(("localhost", 6667))

    nc.sendall(b"CAP\n")
    assert helpers.receive_line(nc) == b":mantatail 461 * CAP :Not enough parameters\r\n"

    nc.sendall(b"CAP LS\n")
    assert helpers.receive_line(nc) == b":mantatail CAP * LS :away-notify cap-notify\r\n"

    nc.sendall(b"CAP LIST\n")
    assert helpers.receive_line(nc) == b":mantatail CAP * LIST :\r\n"

    nc.sendall(b"CAP LS 302\n")
    assert helpers.receive_line(nc) == b":mantatail CAP * LS :away-notify cap-notify\r\n"

    nc.sendall(b"CAP LIST\n")
    assert helpers.receive_line(nc) == b":mantatail CAP * LIST :cap-notify\r\n"

    nc.sendall(b"NICK nc\n")
    nc.sendall(b"USER nc 0 * :netcat\n")

    with pytest.raises(socket.timeout):
        helpers.receive_line(nc)

    nc.sendall(b"CAP END\n")
    while helpers.receive_line(nc) != b":mantatail 376 nc :End of /MOTD command\r\n":
        pass


def test_cap_req(run_server, helpers):
    nc = socket.socket()
    nc.connect(("localhost", 6667))
    nc.sendall(b"CAP LS\n")
    assert helpers.receive_line(nc) == b":mantatail CAP * LS :away-notify cap-notify\r\n"

    nc.sendall(b"CAP REQ\n")
    with pytest.raises(socket.timeout):
        helpers.receive_line(nc)

    nc.sendall(b"CAP REQ foo\n")
    assert helpers.receive_line(nc) == b":mantatail CAP * NAK :foo\r\n"

    nc.sendall(b"CAP REQ foo bar\n")
    assert helpers.receive_line(nc) == b":mantatail CAP * NAK :foo\r\n"

    nc.sendall(b"CAP REQ :foo bar\n")
    assert helpers.receive_line(nc) == b":mantatail CAP * NAK :foo bar\r\n"

    nc.sendall(b"CAP REQ :foo cap-notify\n")
    assert helpers.receive_line(nc) == b":mantatail CAP * NAK :foo cap-notify\r\n"

    nc.sendall(b"CAP REQ :cap-notify\n")
    assert helpers.receive_line(nc) == b":mantatail CAP * ACK :cap-notify\r\n"

    nc.sendall(b"CAP LIST\n")
    assert helpers.receive_line(nc) == b":mantatail CAP * LIST :cap-notify\r\n"

    nc.sendall(b"CAP REQ :away-notify\n")
    assert helpers.receive_line(nc) == b":mantatail CAP * ACK :away-notify\r\n"

    nc.sendall(b"CAP LIST\n")

    while True:
        received = helpers.receive_line(nc)
        if b"LIST" in received:
            received_no_colons = received.replace(b":", b"")
            assert helpers.compare_if_word_match_in_any_order(
                received_no_colons, b"mantatail CAP * LIST cap-notify away-notify\r\n"
            )
            break


def test_away_notify(run_server, helpers):
    nc = socket.socket()
    nc.connect(("localhost", 6667))
    nc.sendall(b"CAP LS\n")
    assert helpers.receive_line(nc) == b":mantatail CAP * LS :away-notify cap-notify\r\n"

    nc.sendall(b"NICK nc\n")
    nc.sendall(b"USER nc 0 * :netcat\n")
    nc.sendall(b"CAP END\n")
    nc.sendall(b"JOIN #foo\n")

    while helpers.receive_line(nc) != b":mantatail 366 nc #foo :End of /NAMES list.\r\n":
        pass

    # Negotiates away-notify with server
    nc2 = socket.socket()
    nc2.connect(("localhost", 6667))
    nc2.sendall(b"CAP REQ away-notify\n")
    assert helpers.receive_line(nc2) == b":mantatail CAP * ACK :away-notify\r\n"
    nc2.sendall(b"NICK nc2\n")
    nc2.sendall(b"USER nc2 0 * :netcat\n")
    nc2.sendall(b"CAP END\n")
    nc2.sendall(b"JOIN #foo\n")

    while helpers.receive_line(nc2) != b":mantatail 366 nc2 #foo :End of /NAMES list.\r\n":
        pass

    # Does not negotiate with server
    nc3 = socket.socket()
    nc3.connect(("localhost", 6667))
    nc3.sendall(b"NICK nc3\n")
    nc3.sendall(b"USER nc3 0 * :netcat\n")
    nc3.sendall(b"JOIN #foo\n")

    while helpers.receive_line(nc3) != b":mantatail 366 nc3 #foo :End of /NAMES list.\r\n":
        pass

    # Join messages from other clients
    helpers.receive_line(nc)
    helpers.receive_line(nc2)

    time.sleep(0.1)

    nc.sendall(b"AWAY :This is an away message\n")

    assert helpers.receive_line(nc2) == b":nc!nc@127.0.0.1 AWAY :This is an away message\r\n"

    # Makes sure that nc3 doesn't receive an away message from nc
    with pytest.raises(socket.timeout):
        helpers.receive_line(nc3)

    nc4 = socket.socket()
    nc4.connect(("localhost", 6667))
    nc4.sendall(b"NICK nc4\n")
    nc4.sendall(b"USER nc4 0 * :netcat\n")

    nc4.sendall(b"AWAY :I am away\n")

    nc4.sendall(b"JOIN #foo\n")

    while helpers.receive_line(nc2) != b":nc4!nc4@127.0.0.1 AWAY :I am away\r\n":
        pass

    assert b"JOIN" in helpers.receive_line(nc3)  # nc4 JOIN message

    # Makes sure that nc3 doesn't receive an away message from nc
    with pytest.raises(socket.timeout):
        helpers.receive_line(nc3)


def test_quit_before_registering(run_server, helpers):
    with socket.socket() as nc:
        nc.connect(("localhost", 6667))  # nc localhost 6667
        nc.sendall(b"QUIT\n")
        assert helpers.receive_line(nc) == b":QUIT :Quit: Client quit\r\n"


def test_quit_reasons(run_server, helpers):
    nc = socket.socket()
    nc.connect(("localhost", 6667))
    nc.sendall(b"NICK nc\n")
    nc.sendall(b"USER nc 0 * :netcat\n")
    nc.sendall(b"JOIN #foo\n")

    while helpers.receive_line(nc) != b":mantatail 366 nc #foo :End of /NAMES list.\r\n":
        pass

    nc2 = socket.socket()
    nc2.connect(("localhost", 6667))
    nc2.sendall(b"NICK nc2\n")
    nc2.sendall(b"USER nc2 0 * :netcat\n")
    nc2.sendall(b"JOIN #foo\n")

    while helpers.receive_line(nc2) != b":mantatail 366 nc2 #foo :End of /NAMES list.\r\n":
        pass

    nc3 = socket.socket()
    nc3.connect(("localhost", 6667))
    nc3.sendall(b"NICK nc3\n")
    nc3.sendall(b"USER nc3 0 * :netcat\n")
    nc3.sendall(b"JOIN #foo\n")

    while helpers.receive_line(nc3) != b":mantatail 366 nc3 #foo :End of /NAMES list.\r\n":
        pass

    nc4 = socket.socket()
    nc4.connect(("localhost", 6667))
    nc4.sendall(b"NICK nc4\n")
    nc4.sendall(b"USER nc4 0 * :netcat\n")
    nc4.sendall(b"JOIN #foo\n")

    while helpers.receive_line(nc4) != b":mantatail 366 nc4 #foo :End of /NAMES list.\r\n":
        pass

    time.sleep(0.1)

    nc.sendall(b"QUIT\n")
    assert helpers.receive_line(nc4) == b":nc!nc@127.0.0.1 QUIT :Quit: Client quit\r\n"

    nc2.sendall(b"QUIT :Reason\n")
    assert helpers.receive_line(nc4) == b":nc2!nc2@127.0.0.1 QUIT :Quit: Reason\r\n"

    nc3.sendall(b"QUIT :Reason with many words\n")
    assert helpers.receive_line(nc4) == b":nc3!nc3@127.0.0.1 QUIT :Quit: Reason with many words\r\n"

    nc4.sendall(b"QUIT Many words but no colon\n")
    assert helpers.receive_line(nc4) == b":nc4!nc4@127.0.0.1 QUIT :Quit: Many\r\n"


def test_no_nickname_given(run_server, helpers):
    with socket.socket() as nc:
        nc.connect(("localhost", 6667))
        nc.sendall(b"NICK\r\n")
        assert helpers.receive_line(nc) == b":mantatail 431 :No nickname given\r\n"


def test_channel_owner_kick_self(run_server, helpers):
    """Checks that a channel is properly removed when a channel's last user (operator) kicks themselves."""
    with socket.socket() as nc:
        nc.connect(("localhost", 6667))
        nc.sendall(b"NICK nc\n")
        nc.sendall(b"USER nc 0 * :netcat\n")
        nc.sendall(b"JOIN #foo\n")

        while helpers.receive_line(nc) != b":mantatail 366 nc #foo :End of /NAMES list.\r\n":
            pass

        nc.sendall(b"KICK #foo nc\n")
        assert helpers.receive_line(nc) == b":nc!nc@127.0.0.1 KICK #foo nc :nc\r\n"

        nc.sendall(b"QUIT\n")

    with socket.socket() as nc:
        nc.connect(("localhost", 6667))
        nc.sendall(b"NICK nc\n")
        nc.sendall(b"USER nc 0 * :netcat\n")

        while helpers.receive_line(nc) != b":mantatail 376 nc :End of /MOTD command\r\n":
            pass

        nc.sendall(b"PART #foo\n")
        assert helpers.receive_line(nc) == b":mantatail 403 nc #foo :No such channel\r\n"

        nc.sendall(b"JOIN #foo\n")

        while helpers.receive_line(nc) != b":mantatail 366 nc #foo :End of /NAMES list.\r\n":
            pass

        nc.sendall(b"KICK #foo nc\n")
        assert helpers.receive_line(nc) == b":nc!nc@127.0.0.1 KICK #foo nc :nc\r\n"

        nc.sendall(b"QUIT\n")


def test_join_part_race_condition(user_alice, user_bob, helpers):
    for i in range(100):
        user_alice.sendall(b"JOIN #foo\r\n")
        time.sleep(random.randint(0, 10) / 1000)
        user_alice.sendall(b"PART #foo\r\n")
        user_bob.sendall(b"JOIN #foo\r\n")
        time.sleep(random.randint(0, 10) / 1000)
        user_bob.sendall(b"PART #foo\r\n")


def test_nick_already_taken(run_server, helpers):
    nc = socket.socket()
    nc.connect(("localhost", 6667))
    nc.sendall(b"NICK nc\n")
    nc.sendall(b"USER nc 0 * :netcat\n")

    while helpers.receive_line(nc) != b":mantatail 376 nc :End of /MOTD command\r\n":
        pass

    nc2 = socket.socket()
    nc2.connect(("localhost", 6667))
    nc2.sendall(b"NICK nc\n")
    assert helpers.receive_line(nc2) == b":mantatail 433 * nc :Nickname is already in use\r\n"

    nc.sendall(b"QUIT\r\n")
    while b"QUIT" not in helpers.receive_line(nc):
        pass
    nc.close()

    time.sleep(0.1)

    nc2.sendall(b"NICK nc\n")
    nc2.sendall(b"USER nc\n")

    while helpers.receive_line(nc2) != b":mantatail 376 nc :End of /MOTD command\r\n":
        pass

    nc2.sendall(b"QUIT\r\n")
    while b"QUIT" not in helpers.receive_line(nc2):
        pass
    nc2.close()

    nc3 = socket.socket()
    nc3.connect(("localhost", 6667))
    nc3.sendall(b"NICK nc3\n")

    time.sleep(0.1)

    nc4 = socket.socket()
    nc4.connect(("localhost", 6667))
    nc4.sendall(b"NICK nc3\n")

    assert helpers.receive_line(nc4) == b":mantatail 433 * nc3 :Nickname is already in use\r\n"

    nc3.sendall(b"QUIT\r\n")
    while b"QUIT" not in helpers.receive_line(nc3):
        pass
    nc3.close()

    nc4.sendall(b"QUIT\r\n")
    while b"QUIT" not in helpers.receive_line(nc4):
        pass
    nc4.close()


def test_erroneus_nick(run_server, helpers):
    nc = socket.socket()
    nc.connect(("localhost", 6667))

    nc.sendall(b"NICK 123newnick\n")
    assert helpers.receive_line(nc) == b":mantatail 432 123newnick :Erroneous Nickname\r\n"

    nc.sendall(b"NICK /newnick\n")
    assert helpers.receive_line(nc) == b":mantatail 432 /newnick :Erroneous Nickname\r\n"

    nc.sendall(b"NICK newnick*\n")
    assert helpers.receive_line(nc) == b":mantatail 432 newnick* :Erroneous Nickname\r\n"


def test_sudden_disconnect(run_server, helpers):
    nc = socket.socket()
    nc.connect(("localhost", 6667))
    nc.sendall(b"NICK nc\n")
    nc.sendall(b"USER nc 0 * :netcat\n")
    nc.sendall(b"JOIN #foo\n")

    while helpers.receive_line(nc) != b":mantatail 366 nc #foo :End of /NAMES list.\r\n":
        pass

    nc2 = socket.socket()
    nc2.connect(("localhost", 6667))
    nc2.sendall(b"NICK nc2\n")
    nc2.sendall(b"USER nc2 0 * :netcat\n")
    nc2.sendall(b"JOIN #foo\n")

    while helpers.receive_line(nc2) != b":mantatail 366 nc2 #foo :End of /NAMES list.\r\n":
        pass

    nc.close()

    if sys.platform == "win32":
        # strerror is platform-specific, and also language specific on windows
        assert helpers.receive_line(nc2).startswith(b":nc!nc@127.0.0.1 QUIT :Quit: ")
    else:
        assert helpers.receive_line(nc2) == b":nc!nc@127.0.0.1 QUIT :Quit: Connection reset by peer\r\n"


# Issue #77
def test_disconnecting_without_sending_anything(user_alice):
    user_alice.send(b"JOIN #foo\r\n")
    time.sleep(0.1)
    nc = socket.socket()
    nc.connect(("localhost", 6667))
    nc.close()


def test_invalid_utf8(user_alice, user_bob, helpers):
    user_alice.sendall(b"JOIN #foo\r\n")
    time.sleep(0.1)
    user_bob.sendall(b"JOIN #foo\r\n")

    while helpers.receive_line(user_alice) != b":Bob!BobUsr@127.0.0.1 JOIN #foo\r\n":
        pass
    while helpers.receive_line(user_bob) != b":mantatail 366 Bob #foo :End of /NAMES list.\r\n":
        pass

    random_message = os.urandom(100).replace(b"\n", b"")
    user_alice.sendall(b"PRIVMSG #foo :" + random_message + b"\r\n")
    assert helpers.receive_line(user_bob) == b":Alice!AliceUsr@127.0.0.1 PRIVMSG #foo :" + random_message + b"\r\n"


def test_message_starting_with_colon(user_alice, user_bob, helpers):
    user_alice.sendall(b"JOIN #foo\r\n")
    time.sleep(0.1)
    user_bob.sendall(b"JOIN #foo\r\n")

    while helpers.receive_line(user_alice) != b":Bob!BobUsr@127.0.0.1 JOIN #foo\r\n":
        pass
    while helpers.receive_line(user_bob) != b":mantatail 366 Bob #foo :End of /NAMES list.\r\n":
        pass

    # Alice sends ":O lolwat" to Bob.
    # It is prefixed with a second ":" because of how IRC works.
    user_alice.sendall(b"PRIVMSG #foo ::O lolwat\r\n")
    assert helpers.receive_line(user_bob) == b":Alice!AliceUsr@127.0.0.1 PRIVMSG #foo ::O lolwat\r\n"

    # Alice sends ":O"
    user_alice.sendall(b"PRIVMSG #foo ::O\r\n")
    assert helpers.receive_line(user_bob) == b":Alice!AliceUsr@127.0.0.1 PRIVMSG #foo ::O\r\n"
