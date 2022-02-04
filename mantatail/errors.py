"""
Responses to invalid actions by the user, for example,leaving a channel that
does not exist or not providing enough parameters in their commands.
"""

from __future__ import annotations
from . import mantatail


def unknown_command(user: mantatail.UserConnection, command: str) -> None:
    """Sent when server does not recognize a command user sent to server."""
    message = f"421 {user.nick} {command} :Unknown command"
    user.send_que.put((message, "mantatail"))


def not_registered(user: mantatail.UserConnection) -> None:
    """
    Sent when a user sends a command before registering to the server.
    Registering is done with commands NICK & USER.
    """
    message = f"451 {user.nick} :You have not registered"
    user.send_que.put((message, "mantatail"))


def no_motd(user: mantatail.UserConnection) -> None:
    """Sent when server cannot find the Message of the Day."""
    message = f"422 {user.nick} :MOTD File is missing"
    user.send_que.put((message, "mantatail"))


def erroneus_nickname(user: mantatail.UserConnection, new_nick: str) -> None:
    message = f"432 {new_nick} :Erroneous Nickname"
    user.send_que.put((message, "mantatail"))


def nick_in_use(user: mantatail.UserConnection, nick: str) -> None:
    """Sent when a Nick that a user tries to establish is already in use."""
    message = f"433 {user.nick} {nick} :Nickname is already in use"
    user.send_que.put((message, "mantatail"))


def no_nickname_given(user: mantatail.UserConnection) -> None:
    message = "431 :No nickname given"
    user.send_que.put((message, "mantatail"))


def no_such_nick_channel(user: mantatail.UserConnection, channel_or_nick: str) -> None:
    """Sent when a user provides a non-existing user or channel as an argument in a command."""
    message = f"401 {user.nick} {channel_or_nick} :No such nick/channel"
    user.send_que.put((message, "mantatail"))


def not_on_channel(user: mantatail.UserConnection, channel_name: str) -> None:
    """Sent when a user tries to send a message to, or part from a channel that they are not connected to."""
    message = f"442 {user.nick} {channel_name} :You're not on that channel"
    user.send_que.put((message, "mantatail"))


def user_not_in_channel(
    user: mantatail.UserConnection, target_usr: mantatail.UserConnection, channel: mantatail.Channel
) -> None:
    """
    Sent when a user sends a channel-specific command with a user as an argument,
    and this user is connected to the server but has not joined the channel.
    """
    message = f"441 {user.nick} {target_usr.nick} {channel.name} :They aren't on that channel"
    user.send_que.put((message, "mantatail"))


def cannot_send_to_channel(user: mantatail.UserConnection, channel_name: str) -> None:
    """
    Sent when privmsg/notice cannot be sent to channel.

    This is generally sent in response to channel modes, such as a channel being moderated
    and the client not having permission to speak on the channel, or not being joined to
    a channel with the no external messages mode set.
    """
    message = f"404 {user.nick} {channel_name} :Cannot send to nick/channel"
    user.send_que.put((message, "mantatail"))


def banned_from_chan(user: mantatail.UserConnection, channel: mantatail.Channel) -> None:
    """Notifies the user trying to join a channel that they are banned from that channel."""
    message = f"474 {user.nick} {channel.name} :Cannot join channel (+b) - you are banned"
    user.send_que.put((message, "mantatail"))


def no_such_channel(user: mantatail.UserConnection, channel_name: str) -> None:
    """Sent when a user provides a non-existing channel as an argument in a command."""
    message = f"403 {user.nick} {channel_name} :No such channel"
    user.send_que.put((message, "mantatail"))


def no_operator_privileges(user: mantatail.UserConnection, channel: mantatail.Channel) -> None:
    """
    Sent when a user is trying to perform an action reserved to channel operators,
    but is not an operator on that channel.
    """
    message = f"482 {user.nick} {channel.name} :You're not channel operator"
    user.send_que.put((message, "mantatail"))


def no_recipient(user: mantatail.UserConnection, command: str) -> None:
    """Sent when a user sends a PRIVMSG but without providing a recipient."""
    message = f"411 {user.nick} :No recipient given ({command.upper()})"
    user.send_que.put((message, "mantatail"))


def no_text_to_send(user: mantatail.UserConnection) -> None:
    """
    Sent when a user tries to send a PRIVMSG but without providing any message to send.
    Ex. "PRIVMSG #foo"
    """
    message = f"412 {user.nick} :No text to send"
    user.send_que.put((message, "mantatail"))


def unknown_mode(user: mantatail.UserConnection, unknown_command: str) -> None:
    """Sent when a user tries to set a channel/user mode that the server does not recognize."""
    message = f"472 {user.nick} {unknown_command} :is an unknown mode char to me"
    user.send_que.put((message, "mantatail"))


def no_origin(user: mantatail.UserConnection) -> None:
    """
    Sent when the argument of a PONG message sent as a response to the server's
    PING message does not correspond to the argument sent in the PING message.
    """
    message = f"409 {user.nick} :No origin specified"
    user.send_que.put((message, "mantatail"))


def not_enough_params(user: mantatail.UserConnection, command: str) -> None:
    """Sent when a user sends a command to the server that does not contain all required arguments."""
    message = f"461 {user.nick} {command} :Not enough parameters"
    user.send_que.put((message, "mantatail"))
