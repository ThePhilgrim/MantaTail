import pytest
import socket
import time


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


### Netcat tests
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
