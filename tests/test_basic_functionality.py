import os
import sys
import pytest
import random
import socket
import time

import server


def test_server_sends_ping(monkeypatch, user_alice, helpers):
    monkeypatch.setattr(server, "PING_TIMER_SECS", 2)
    user_alice.sendall(b"JOIN #foo\r\n")

    while helpers.receive_line(user_alice, 3) != b"PING :mantatail\r\n":
        pass

    user_alice.sendall(b"PONG :mantatail\r\n")


def test_client_sends_ping(user_alice, helpers):
    user_alice.sendall(b"PING :blah blah\r\n")
    assert helpers.receive_line(user_alice) == b":mantatail PONG mantatail :blah blah\r\n"

    user_alice.sendall(b"PING\r\n")
    assert helpers.receive_line(user_alice) == b":mantatail 461 Alice PING :Not enough parameters\r\n"


def test_join_channel(user_alice, user_bob, helpers):
    user_alice.sendall(b"JOIN #foo\r\n")
    time.sleep(0.1)
    user_bob.sendall(b"JOIN #foo\r\n")

    assert helpers.receive_line(user_bob) == b":Bob!BobUsr@127.0.0.1 JOIN #foo\r\n"

    while helpers.receive_line(user_bob) != b":mantatail 353 Bob = #foo :Bob @Alice\r\n":
        pass
    while helpers.receive_line(user_bob) != b":mantatail 366 Bob #foo :End of /NAMES list.\r\n":
        pass


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

    user_alice.sendall(b"NICK :newnick\r\n")
    assert helpers.receive_line(user_alice) == b":NewNick!AliceUsr@127.0.0.1 NICK :newnick\r\n"
    assert helpers.receive_line(user_bob) == b":NewNick!AliceUsr@127.0.0.1 NICK :newnick\r\n"

    user_alice.sendall(b"NICK :NEWNICK\r\n")
    assert helpers.receive_line(user_alice) == b":newnick!AliceUsr@127.0.0.1 NICK :NEWNICK\r\n"
    assert helpers.receive_line(user_bob) == b":newnick!AliceUsr@127.0.0.1 NICK :NEWNICK\r\n"

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


def test_who_command(user_alice, user_bob, user_charlie, helpers):
    user_alice.sendall(b"JOIN #foo\r\n")
    time.sleep(0.1)
    user_bob.sendall(b"JOIN #foo\r\n")

    while helpers.receive_line(user_alice) != b":Bob!BobUsr@127.0.0.1 JOIN #foo\r\n":
        pass
    while helpers.receive_line(user_bob) != b":mantatail 366 Bob #foo :End of /NAMES list.\r\n":
        pass

    user_bob.sendall(b"AWAY :I am away\r\n")
    assert helpers.receive_line(user_bob) == b":mantatail 306 Bob :You have been marked as being away\r\n"

    user_charlie.sendall(b"WHO #foo\r\n")
    assert helpers.receive_line(user_charlie) == b":mantatail 315 Charlie #foo :End of /WHO list.\r\n"

    user_charlie.sendall(b"JOIN #foo\r\n")
    while helpers.receive_line(user_charlie) != b":mantatail 366 Charlie #foo :End of /NAMES list.\r\n":
        pass

    WHO_MESSAGES = [
        b":mantatail 352 Charlie #foo AliceUsr 127.0.0.1 Mantatail Alice H@ :0 Alice's real name\r\n",
        b":mantatail 352 Charlie #foo BobUsr 127.0.0.1 Mantatail Bob G :0 Bob's real name\r\n",
        b":mantatail 352 Charlie #foo CharlieUsr 127.0.0.1 Mantatail Charlie H :0 Charlie's real name\r\n",
    ]
    user_charlie.sendall(b"WHO #foo\r\n")
    assert helpers.receive_line(user_charlie) in WHO_MESSAGES
    assert helpers.receive_line(user_charlie) in WHO_MESSAGES
    assert helpers.receive_line(user_charlie) in WHO_MESSAGES
    assert helpers.receive_line(user_charlie) == b":mantatail 315 Charlie #foo :End of /WHO list.\r\n"

    user_charlie.sendall(b"PART #foo\r\n")
    assert helpers.receive_line(user_charlie) == b":Charlie!CharlieUsr@127.0.0.1 PART #foo\r\n"

    user_charlie.sendall(b"WHO Alice\r\n")
    assert (
        helpers.receive_line(user_charlie)
        == b":mantatail 352 Charlie * AliceUsr 127.0.0.1 Mantatail Alice H :0 Alice's real name\r\n"
    )
    assert helpers.receive_line(user_charlie) == b":mantatail 315 Charlie Alice :End of /WHO list.\r\n"


def test_whois_command(user_alice, user_bob, user_charlie, helpers):
    user_alice.sendall(b"WHOIS\r\n")
    assert helpers.receive_line(user_alice) == b":mantatail 461 Alice WHOIS :Not enough parameters\r\n"

    user_alice.sendall(b"WHOIS Debora\r\n")
    assert helpers.receive_line(user_alice) == b":mantatail 401 Alice Debora :No such nick/channel\r\n"

    user_alice.sendall(b"WHOIS Bob\r\n")
    assert helpers.receive_line(user_alice) == b":mantatail 311 Alice Bob BobUsr 127.0.0.1 * :Bob's real name\r\n"
    assert helpers.receive_line(user_alice) == b":mantatail 318 Alice Bob :End of /WHOIS list.\r\n"

    user_alice.sendall(b"WHOIS Bob Debora\r\n")
    assert helpers.receive_line(user_alice) == b":mantatail 401 Alice Debora :No such nick/channel\r\n"

    user_alice.sendall(b"WHOIS Debora Bob\r\n")
    assert helpers.receive_line(user_alice) == b":mantatail 402 Alice Debora :No such server\r\n"

    user_alice.sendall(b"WHOIS Charlie Bob\r\n")
    assert helpers.receive_line(user_alice) == b":mantatail 311 Alice Bob BobUsr 127.0.0.1 * :Bob's real name\r\n"
    assert helpers.receive_line(user_alice) == b":mantatail 318 Alice Bob :End of /WHOIS list.\r\n"


def test_send_privmsg_to_user(user_alice, user_bob, helpers):
    user_alice.sendall(b"PRIVMSG Bob :This is a private message\r\n")
    assert helpers.receive_line(user_bob) == b":Alice!AliceUsr@127.0.0.1 PRIVMSG Bob :This is a private message\r\n"

    user_bob.sendall(b"PRIVMSG alice :This is a reply\r\n")
    assert helpers.receive_line(user_alice) == b":Bob!BobUsr@127.0.0.1 PRIVMSG Alice :This is a reply\r\n"


def test_channel_mode_is(user_alice, helpers):
    user_alice.sendall(b"JOIN #foo\r\n")

    while helpers.receive_line(user_alice) != b":mantatail 366 Alice #foo :End of /NAMES list.\r\n":
        pass

    user_alice.sendall(b"MODE #foo\r\n")
    assert helpers.receive_line(user_alice) == b":mantatail 324 Alice #foo +t\r\n"


def test_join_part_race_condition(user_alice, user_bob, helpers):
    for i in range(100):
        user_alice.sendall(b"JOIN #foo\r\n")
        time.sleep(random.randint(0, 10) / 1000)
        user_alice.sendall(b"PART #foo\r\n")
        user_bob.sendall(b"JOIN #foo\r\n")
        time.sleep(random.randint(0, 10) / 1000)
        user_bob.sendall(b"PART #foo\r\n")


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


def test_whois_reply(user_alice, user_bob, helpers):
    user_alice.sendall(b"WHOIS Alice\r\n")
    assert helpers.receive_line(user_alice) == b":mantatail 311 Alice Alice AliceUsr 127.0.0.1 * :Alice's real name\r\n"
    assert helpers.receive_line(user_alice) == b":mantatail 312 Alice Alice Mantatail :Running locally\r\n"
    assert helpers.receive_line(user_alice) == b":mantatail 318 Alice Alice :End of /WHOIS list.\r\n"

    user_alice.sendall(b"WHOIS Bob\r\n")
    assert helpers.receive_line(user_alice) == b":mantatail 311 Bob Bob BobUsr 127.0.0.1 * :Bob's real name\r\n"
    assert helpers.receive_line(user_alice) == b":mantatail 312 Bob Bob Mantatail :Running locally\r\n"
    assert helpers.receive_line(user_alice) == b":mantatail 318 Bob Bob :End of /WHOIS list.\r\n"


### Netcat tests
# netcat sends \n line endings, but is fine receiving \r\n
def test_connect_via_netcat(run_server, helpers):
    with socket.socket() as nc:
        nc.connect(("localhost", 6667))  # nc localhost 6667
        nc.sendall(b"NICK nc\n")
        nc.sendall(b"USER nc 0 * :netcat\n")
        while helpers.receive_line(nc) != b":mantatail 376 nc :End of /MOTD command\r\n":
            pass


def test_on_registration_messages(run_server, helpers):
    nc = socket.socket()
    nc.connect(("localhost", 6667))
    nc.sendall(b"NICK nc\n")
    nc.sendall(b"USER nc 0 * :netcat\n")

    assert helpers.receive_line(nc) == b":mantatail 001 nc :Welcome to Mantatail nc!nc@127.0.0.1\r\n"
    assert b":mantatail 002 nc :Your host is Mantatail[" in helpers.receive_line(nc)
    assert b":mantatail 003 nc :This server was created" in helpers.receive_line(nc)
    assert b":mantatail 004 nc Mantatail 0.0.1" in helpers.receive_line(nc)
    line = helpers.receive_line(nc)
    assert b":mantatail 005 nc" in line
    assert b":are supported by this server" in line

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
        assert helpers.receive_line(nc) == b"QUIT :Quit: Client quit\r\n"


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
