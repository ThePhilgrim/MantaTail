import socket
import time


def test_join_before_registering(run_server, helpers):
    user_socket = socket.socket()
    user_socket.connect(("localhost", 6667))
    user_socket.sendall(b"JOIN #foo\r\n")
    assert helpers.receive_line(user_socket) == b":mantatail 451 * :You have not registered\r\n"


def test_no_such_channel(user_alice, helpers):
    user_alice.sendall(b"PART #foo\r\n")
    assert helpers.receive_line(user_alice) == b":mantatail 403 Alice #foo :No such channel\r\n"


def test_youre_not_on_that_channel(user_alice, user_bob, helpers):
    user_alice.sendall(b"JOIN #foo\r\n")
    time.sleep(0.1)  # TODO: wait until server says that join is done
    user_bob.sendall(b"PART #foo\r\n")

    assert helpers.receive_line(user_bob) == b":mantatail 442 Bob #foo :You're not on that channel\r\n"


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


### Netcat tests
def test_no_nickname_given(run_server, helpers):
    with socket.socket() as nc:
        nc.connect(("localhost", 6667))
        nc.sendall(b"NICK\r\n")
        assert helpers.receive_line(nc) == b":mantatail 431 :No nickname given\r\n"


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
