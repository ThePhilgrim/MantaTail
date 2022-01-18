"""
Contains handler functions that handle commands received from a client, as well as appropriate errors.

All public functions must start with "handle_"
"""
from __future__ import annotations
import re
import mantatail
import irc_responses

from typing import Optional, Dict, List, Tuple


### Handlers
def handle_join(state: mantatail.ServerState, user: mantatail.UserConnection, args: List[str]) -> None:
    """
    Handles clien't command to join a channel on the server.
    Command format: "JOIN #foo"

    If the channel already exists, the user is put to the appropriate channel's
    Dict of connected users.
    If the channel does not exist, the channel is created by instantiating mantatail.Channel.

    Finally, sends a message to all users on the channel, notifying them that
    User has joined the channel.
    """
    if not args:
        error_not_enough_params(user, "JOIN")
        return

    channel_regex = r"#[^ \x07,]{1,49}"  # TODO: Make more restrictive (currently valid: ###, #ö?!~ etc)
    channel_name = args[0]
    lower_channel_name = channel_name.lower()

    if not re.match(channel_regex, lower_channel_name):
        error_no_such_channel(user, channel_name)
    else:
        if lower_channel_name not in state.channels.keys():
            state.channels[lower_channel_name] = mantatail.Channel(channel_name, user)

        channel = state.channels[lower_channel_name]

        if user not in channel.users:
            channel_users_str = ""
            for usr in channel.users:
                if usr.user_name == channel.founder:
                    nick = f"~{usr.nick}"
                elif channel.is_operator(usr):
                    nick = f"@{usr.nick}"
                else:
                    nick = usr.nick
                channel_users_str += f" {nick}"

            channel.users.add(user)

            for usr in channel.users:
                message = f"JOIN {channel_name}"
                usr.send_que.put((message, user.get_user_mask()))

            # TODO: Implement topic functionality for existing channels & MODE for new ones

            message = f"353 {user.nick} = {channel_name} :{user.nick} {channel_users_str.strip()}"
            user.send_que.put((message, "mantatail"))

            message = f"366 {user.nick} {channel_name} :End of /NAMES list."
            user.send_que.put((message, "mantatail"))

        # TODO:
        #   * Send topic (332)
        #   * Optional/Later: (333) https://modern.ircdocs.horse/#rpltopicwhotime-333
        #   * Forward to another channel (irc num 470) ex. #homebrew -> ##homebrew


def handle_part(state: mantatail.ServerState, user: mantatail.UserConnection, args: List[str]) -> None:
    """
    Handles clien't command to disconnect from a channel on the server.
    Command format: "PART #foo"

    Finally, sends a message to all users on the channel, notifying them that
    User has left the channel.
    """
    if not args:
        error_not_enough_params(user, "PART")
        return

    channel_name = args[0]

    try:
        channel = state.find_channel(channel_name)
    except KeyError:
        error_no_such_channel(user, channel_name)
        return

    if user not in channel.users:
        error_not_on_channel(user, channel_name)
    else:
        if channel.is_operator(user):
            channel.remove_operator(user)

        for usr in channel.users:
            message = f"PART {channel_name}"
            usr.send_que.put((message, user.get_user_mask()))

        channel.users.discard(user)
        if len(channel.users) == 0:
            state.delete_channel(channel_name)


def handle_mode(state: mantatail.ServerState, user: mantatail.UserConnection, args: List[str]) -> None:
    """
    Handles clien't command to set a channel/user mode.
    Command format: "MODE #channel/user.nick +/-flag <args>"
    """
    if not args:
        error_not_enough_params(user, "MODE")
        return

    if args[0].startswith("#"):
        process_channel_modes(state, user, args)
    else:
        process_user_modes()


def handle_kick(state: mantatail.ServerState, user: mantatail.UserConnection, args: List[str]) -> None:
    """
    Handles client's command to kick a user from a channel.
    Command format: "KICK #foo user_to_kick (:Reason for kicking)"

    The user kicking somebody must be an operator on that channel
    (see mantatail.Channel.operators)

    Fnally, sends a message to all users on the channel,
    notifying them that an operator has kicked a user.
    """
    if not args or len(args) == 1:
        error_not_enough_params(user, "KICK")
        return

    try:
        channel = state.find_channel(args[0])
    except KeyError:
        error_no_such_channel(user, args[0])
        return
    try:
        target_usr = state.find_user(args[1])
    except KeyError:
        error_no_such_nick_channel(user, args[1])
        return

    if not channel.is_operator(user):
        error_no_operator_privileges(user, channel)
        return

    if target_usr not in channel.users:
        error_user_not_in_channel(user, target_usr, channel)
        return

    if len(args) == 2:
        message = f"KICK {channel.name} {target_usr.nick} :{target_usr.nick}\r\n"
    elif len(args) >= 3:
        reason = args[2]
        message = f"KICK {channel.name} {target_usr.nick} :{reason}\r\n"

    channel.kick_user(user, target_usr, message)


def handle_quit(state: mantatail.ServerState, user: mantatail.UserConnection, args: List[str]) -> None:
    """
    Handles a user's command to disconnect from the server.
    Command format: "QUIT"

    Puts a tuple (None, None) to the user's send_que, which the server
    interprets as the user wanting to disconnect
    (see mantatail.UserConection.send_queue_thread).
    """
    # TODO "if args: set args to reason"
    user.send_que.put((None, None))


def handle_privmsg(state: mantatail.ServerState, user: mantatail.UserConnection, args: List[str]) -> None:
    """
    Handles client's command to send a message to a channel or a private message to a user.
    Command format: "PRIVMSG #channel/user.nick :This is a message"

    Private message's to users are handled in privmsg_to_user().
    """
    if not args:
        error_no_recipient(user, "PRIVMSG")
        return
    elif len(args) == 1:
        error_no_text_to_send(user)
        return

    (receiver, privmsg) = args[0], args[1]

    if receiver.startswith("#"):
        try:
            channel = state.find_channel(receiver)
        except KeyError:
            error_no_such_nick_channel(user, receiver)
            return
    else:
        privmsg_to_user(receiver, privmsg)
        return

    if user not in channel.users:
        error_not_on_channel(user, receiver)
    else:
        for usr in channel.users:
            if usr.nick != user.nick:
                message = f"PRIVMSG {receiver} :{privmsg}"
                usr.send_que.put((message, user.get_user_mask()))


def handle_pong(state: mantatail.ServerState, user: mantatail.UserConnection, args: List[str]) -> None:
    """
    Handles client's PONG resonse to a PING message sent from the server.

    The PONG message notifies the server that the client still has an open connection to it.
    """
    if args and args[0] == "mantatail":
        user.pong_received = True
    else:
        error_no_origin(user)


# Private functions

# !Not implemented
def privmsg_to_user(receiver: str, privmsg: str) -> None:
    pass


def motd(motd_content: Optional[Dict[str, List[str]]], user: mantatail.UserConnection) -> None:
    (start_num, start_info) = irc_responses.RPL_MOTDSTART
    motd_num = irc_responses.RPL_MOTD
    (end_num, end_info) = irc_responses.RPL_ENDOFMOTD

    motd_start_and_end = {
        "start_msg": f"{start_num} {user.nick} :- mantatail {start_info}",
        "end_msg": f"{end_num} {user.nick} {end_info}",
    }

    user.send_que.put((motd_start_and_end["start_msg"], "mantatail"))

    if motd_content:
        motd = motd_content["motd"]
        for motd_line in motd:
            motd_message = f"{motd_num} {user.nick} :{motd_line.format(user_nick=user.nick)}"
            user.send_que.put((motd_message, "mantatail"))
    # If motd.json could not be found
    else:
        error_no_motd(user)

    user.send_que.put((motd_start_and_end["end_msg"], "mantatail"))


def process_channel_modes(state: mantatail.ServerState, user: mantatail.UserConnection, args: List[str]) -> None:
    if args[1][0] not in ["+", "-"]:
        error_unknown_mode(user, args[1][0])
        return
    supported_modes = ["o"]
    for mode in args[1][1:]:
        if mode not in supported_modes:
            error_unknown_mode(user, mode)
            return

    try:
        channel = state.find_channel(args[0])
    except KeyError:
        error_no_such_channel(user, args[0])
        return

    if len(args) == 1:
        message = f'{irc_responses.RPL_CHANNELMODEIS} {channel.name} {" ".join(channel.modes)}'
        user.send_que.put((message, "mantatail"))
    elif len(args) == 2:
        error_not_enough_params(user, "MODE")
    else:
        mode_command, flags = args[1][0], args[1][1:]
        try:
            target_usr = state.find_user(args[2])
        except KeyError:
            error_no_such_nick_channel(user, args[2])
            return

        for flag in flags:
            if flag == "o":
                if not channel.is_operator(user):
                    error_no_operator_privileges(user, channel)
                    return
                elif target_usr not in channel.users:
                    error_user_not_in_channel(user, target_usr, channel)
                    return

                if mode_command == "+":
                    channel.set_operator(target_usr)
                elif mode_command[0] == "-":
                    channel.remove_operator(target_usr)

                message = f"MODE {channel.name} {mode_command}o {target_usr.nick}"
                for usr in channel.users:
                    usr.send_que.put((message, "mantatail"))


# !Not implemented
def process_user_modes() -> None:
    pass


def parse_received_args(msg: str) -> Tuple[str, List[str]]:
    split_msg = msg.split(" ")

    for num, arg in enumerate(split_msg):
        if arg.startswith(":"):
            parsed_msg = split_msg[:num]
            parsed_msg.append(" ".join(split_msg[num:]).lstrip(":"))
            command = parsed_msg[0]
            return command, parsed_msg[1:]

    command = split_msg[0]
    return command, split_msg[1:]


### Error Messages
def error_unknown_command(user: mantatail.UserConnection, command: str) -> None:
    """Sent when server does not recognize a command user sent to server."""
    (unknown_cmd_num, unknown_cmd_info) = irc_responses.ERR_UNKNOWNCOMMAND

    message = f"{unknown_cmd_num} {command} {unknown_cmd_info}"
    user.send_que.put((message, "mantatail"))


def error_not_registered(user: mantatail.UserConnection) -> None:
    """Sent when a user sends a command before establishing a Nick and User."""
    (not_registered_num, not_registered_info) = irc_responses.ERR_NOTREGISTERED

    message = f":mantatail {not_registered_num} * {not_registered_info}"
    user.send_que.put((message, "mantatail"))


def error_no_motd(user: mantatail.UserConnection) -> None:
    """Sent when server cannot find the Message of the Day."""
    (no_motd_num, no_motd_info) = irc_responses.ERR_NOMOTD

    message = f"{no_motd_num} {no_motd_info}"
    user.send_que.put((message, "mantatail"))


def error_nick_in_use(user: mantatail.UserConnection, nick: str) -> None:
    """Sent when a Nick that a user tries to establish is already in use."""
    (nick_in_use_num, nick_in_use_info) = irc_responses.ERR_NICKNAMEINUSE

    message = f"{nick_in_use_num} {nick} {nick_in_use_info}"
    user.send_que.put((message, "mantatail"))


def error_no_such_nick_channel(user: mantatail.UserConnection, channel_or_nick: str) -> None:
    """Sent when a user provides a non-existing user or channel as an argument in a command."""
    (no_nick_num, no_nick_info) = irc_responses.ERR_NOSUCHNICK

    message = f"{no_nick_num} {channel_or_nick} {no_nick_info}"
    user.send_que.put((message, "mantatail"))


def error_not_on_channel(user: mantatail.UserConnection, channel_name: str) -> None:
    """Sent when a user tries to send a message to, or part from a channel that they are not connected to."""
    (not_on_channel_num, not_on_channel_info) = irc_responses.ERR_NOTONCHANNEL

    message = f"{not_on_channel_num} {channel_name} {not_on_channel_info}"
    user.send_que.put((message, "mantatail"))


def error_user_not_in_channel(
    user: mantatail.UserConnection, target_usr: mantatail.UserConnection, channel: mantatail.Channel
) -> None:
    """
    Sent when a user sends a channel-specific command with a user as an argument,
    and this user is connected to the server but not to the channel.
    """
    (not_in_chan_num, not_in_chan_info) = irc_responses.ERR_USERNOTINCHANNEL
    message = f"{not_in_chan_num} {target_usr.nick} {channel.name} {not_in_chan_info}"
    user.send_que.put((message, "mantatail"))


def error_cannot_send_to_channel(user: mantatail.UserConnection, channel_name: str) -> None:
    # TODO: Figure out when this is sent and make docstring
    (cant_send_num, cant_send_info) = irc_responses.ERR_CANNOTSENDTOCHAN

    message = f"{cant_send_num} {channel_name} {cant_send_info}"
    user.send_que.put((message, "mantatail"))


def error_no_such_channel(user: mantatail.UserConnection, channel_name: str) -> None:
    """Sent when a user provides a non-existing channel as an argument in a command."""
    (no_channel_num, no_channel_info) = irc_responses.ERR_NOSUCHCHANNEL
    message = f"{no_channel_num} {channel_name} {no_channel_info}"
    user.send_que.put((message, "mantatail"))


def error_no_operator_privileges(user: mantatail.UserConnection, channel: mantatail.Channel) -> None:
    """
    Sent when a user is trying to perform an action reserved to channel operators,
    but is not an operator on that channel.
    """
    (not_operator_num, not_operator_info) = irc_responses.ERR_CHANOPRIVSNEEDED
    message = f"{not_operator_num} {channel.name} {not_operator_info}"
    user.send_que.put((message, "mantatail"))


def error_no_recipient(user: mantatail.UserConnection, command: str) -> None:
    """Sent when a user sends a PRIVMSG but without providing a recipient."""
    (no_recipient_num, no_recipient_info) = irc_responses.ERR_NORECIPIENT

    message = f"{no_recipient_num} {no_recipient_info} ({command.upper()})"
    user.send_que.put((message, "mantatail"))


def error_no_text_to_send(user: mantatail.UserConnection) -> None:
    """
    Sent when a user tries to send a PRIVMSG but without providing any message to send.
    Ex. "PRIVMSG #foo"
    """
    (no_text_num, no_text_info) = irc_responses.ERR_NOTEXTTOSEND

    message = f"{no_text_num} {no_text_info}"
    user.send_que.put((message, "mantatail"))


def error_unknown_mode(user: mantatail.UserConnection, unknown_command: str) -> None:
    """Sent when a user tries to set a channel/user mode that the server does not recognize."""
    (unknown_mode_num, unknown_mode_info) = irc_responses.ERR_UNKNOWNMODE
    message = f"{unknown_mode_num} {unknown_command} {unknown_mode_info}"
    user.send_que.put((message, "mantatail"))


def error_no_origin(user: mantatail.UserConnection) -> None:
    """
    Sent when the argument of a PONG message sent as a response to the server's
    PING message does not correspond to the argument sent in the PING message.
    """
    (no_origin_num, no_origin_info) = irc_responses.ERR_NOORIGIN

    message = f"{no_origin_num} {no_origin_info}"
    user.send_que.put((message, "mantatail"))


def error_not_enough_params(user: mantatail.UserConnection, command: str) -> None:
    """Sent when a user sends a command to the server that does not contain all required arguments."""
    (not_enough_params_num, not_enough_params_info) = irc_responses.ERR_NEEDMOREPARAMS
    message = f"{not_enough_params_num} {command} {not_enough_params_info}"
    user.send_que.put((message, "mantatail"))
