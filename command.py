from __future__ import annotations
import re
import mantatail
import irc_responses

from typing import Optional, Dict, List


### Handlers
def handle_join(state: mantatail.ServerState, user: mantatail.UserConnection, channel_name: str) -> None:
    channel_regex = r"#[^ \x07,]{1,49}"  # TODO: Make more restrictive (currently valid: ###, #ö?!~ etc)
    lower_channel_name = channel_name.lower()

    with state.lock:
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
                    elif usr.nick.lower() in channel.operators:
                        nick = f"@{usr.nick}"
                    else:
                        nick = usr.nick
                    channel_users_str += f" {nick}"

                channel.users.add(user)

                for usr in channel.users:
                    message = f"JOIN {channel_name}"
                    usr.send_string_to_client(message, prefix=user.user_mask)

                # TODO: Implement topic functionality for existing channels & MODE for new ones

                message = f"353 {user.nick} = {channel_name} :{user.nick} {channel_users_str.strip()}"
                user.send_string_to_client(message)

                message = f"366 {user.nick} {channel_name} :End of /NAMES list."
                user.send_string_to_client(message)

        # TODO:
        #   * Send topic (332)
        #   * Optional/Later: (333) https://modern.ircdocs.horse/#rpltopicwhotime-333
        #   * Forward to another channel (irc num 470) ex. #homebrew -> ##homebrew


def handle_part(state: mantatail.ServerState, user: mantatail.UserConnection, channel_name: str) -> None:
    with state.lock:
        try:
            channel = state.channels[channel_name.lower()]
        except KeyError:
            error_no_such_channel(user, channel_name)
            return

        if user not in channel.users:
            error_not_on_channel(user, channel_name)
        else:
            if user.nick.lower() in channel.operators:
                channel.remove_operator(user.nick.lower())

            for usr in channel.users:
                message = f"PART {channel_name}"
                usr.send_string_to_client(message, prefix=user.user_mask)

            channel.users.discard(user)
            if len(channel.users) == 0:
                del state.channels[channel_name.lower()]


def handle_mode(state: mantatail.ServerState, user: mantatail.UserConnection, mode_args: str) -> None:
    args = mode_args.split(" ")

    if args[0].startswith("#"):
        process_channel_modes(state, user, args)
    else:
        process_user_modes()


def handle_kick(state: mantatail.ServerState, user: mantatail.UserConnection, arg: str) -> None:
    args = arg.split()

    if len(args) == 1:
        error_not_enough_params(user, user.nick, "KICK")
    elif args[0].lower() not in state.channels.keys():
        error_no_such_channel(user, args[0])
    elif user.nick.lower() not in state.channels[args[0].lower()].operators:
        error_no_operator_privileges(user, state.channels[args[0].lower()])
    elif len(args) >= 2 and args[1].lower() not in state.connected_users.keys():
        error_no_such_nick_channel(user, args[-1])
    elif (
        len(args) >= 2
        and args[1].lower() in state.connected_users.keys()
        and state.connected_users[args[1].lower()] not in state.channels[args[0].lower()].users
    ):
        error_user_not_in_channel(user, state.connected_users[args[1].lower()], state.channels[args[0].lower()])
    else:
        if len(args) == 2:
            message = f"KICK {state.channels[args[0].lower()].name} {state.connected_users[args[1].lower()].nick}\r\n"
        elif len(args) >= 3:
            if not args[2].startswith(":"):
                reason = f":{args[2]}"
            else:
                reason = " ".join(args[2:])
            message = f"KICK {state.channels[args[0].lower()].name} {state.connected_users[args[1].lower()].nick} {reason}\r\n"
        state.channels[args[0].lower()].kick_user(user, state.connected_users[args[1].lower()], message)


def handle_quit(state: mantatail.ServerState, user: mantatail.UserConnection, command: str) -> None:
    # TODO: Implement logic for different reasons & disconnects.
    reason = "(Remote host closed the connection)"
    message = f"QUIT :Quit: {reason}"

    receivers = set()
    with state.lock:
        receivers.add(user)
        for channel in state.channels.values():
            if user in channel.users:
                for usr in channel.users:
                    receivers.add(usr)
                channel.users.discard(user)

            if user.nick.lower() in channel.operators:
                channel.remove_operator(user.nick.lower())

        for receiver in receivers:
            receiver.send_string_to_client(message, prefix=user.user_mask)

        del state.connected_users[user.nick.lower()]

        user.closed_connection = True
        user.socket.close()


def handle_privmsg(state: mantatail.ServerState, user: mantatail.UserConnection, msg: str) -> None:
    with state.lock:
        (receiver, colon_privmsg) = msg.split(" ", 1)
        assert colon_privmsg.startswith(":")

        if receiver.startswith("#"):
            try:
                channel = state.channels[receiver.lower()]
            except KeyError:
                error_no_such_nick_channel(user, receiver)
                return
        else:
            privmsg_to_user(receiver, colon_privmsg)
            return

        if user not in channel.users:
            error_not_on_channel(user, receiver)
        else:
            for usr in channel.users:
                if usr.nick != user.nick:
                    message = f"PRIVMSG {receiver} {colon_privmsg}"
                    usr.send_string_to_client(message, prefix=user.user_mask)


# Private functions

# !Not implemented
def privmsg_to_user(receiver: str, colon_privmsg: str) -> None:
    pass


def motd(motd_content: Optional[Dict[str, List[str]]], user: mantatail.UserConnection) -> None:
    (start_num, start_info) = irc_responses.RPL_MOTDSTART
    motd_num = irc_responses.RPL_MOTD
    (end_num, end_info) = irc_responses.RPL_ENDOFMOTD

    motd_start_and_end = {
        "start_msg": f"{start_num} {user.nick} :- mantatail {start_info}",
        "end_msg": f"{end_num} {user.nick} {end_info}",
    }

    user.send_string_to_client(motd_start_and_end["start_msg"])

    if motd_content:
        motd = motd_content["motd"]
        for motd_line in motd:
            motd_message = f"{motd_num} {user.nick} :{motd_line.format(user_nick=user.nick)}"
            user.send_string_to_client(motd_message)
    # If motd.json could not be found
    else:
        error_no_motd(user)

    user.send_string_to_client(motd_start_and_end["end_msg"])


def process_channel_modes(state: mantatail.ServerState, user: mantatail.UserConnection, args: List[str]) -> None:
    if args[1][0] not in ["+", "-"]:
        error_unknown_mode(user, args[1][0])
        return
    supported_modes = ["o"]
    for mode in args[1][1:]:
        if mode not in supported_modes:
            error_unknown_mode(user, mode)
            return

    with state.lock:
        if args[0].lower() not in state.channels.keys():
            error_no_such_channel(user, args[0])
        elif len(args) == 1:
            message = f'{irc_responses.RPL_CHANNELMODEIS} {args[0]} {" ".join(state.channels[args[0].lower()].modes)}'
            user.send_string_to_client(message)
        elif len(args) == 2:
            error_not_enough_params(user, args[0], "MODE")
        else:
            channel = state.channels[args[0].lower()]
            mode_command, flags = args[1][0], args[1][1:]
            try:
                target_usr = state.connected_users[args[2].lower()]
            except KeyError:
                error_no_such_nick_channel(user, args[2])
                return

            for flag in flags:
                if flag == "o":
                    if user.nick.lower() not in channel.operators:
                        error_no_operator_privileges(user, channel)
                        return
                    elif target_usr not in channel.users:
                        error_user_not_in_channel(user, target_usr, channel)
                        return

                    if mode_command == "+":
                        channel.set_operator(target_usr.nick.lower())
                    elif mode_command[0] == "-":
                        channel.remove_operator(target_usr.nick.lower())

                    message = f"MODE {channel.name} {mode_command}o {target_usr.nick}"
                    for usr in channel.users:
                        usr.send_string_to_client(message)


# !Not implemented
def process_user_modes() -> None:
    pass


### Error Messages
def error_unknown_command(user: mantatail.UserConnection, command: str) -> None:
    (unknown_cmd_num, unknown_cmd_info) = irc_responses.ERR_UNKNOWNCOMMAND

    message = f"{unknown_cmd_num} {command} {unknown_cmd_info}"
    user.send_string_to_client(message)


def error_not_registered() -> bytes:
    (not_registered_num, not_registered_info) = irc_responses.ERR_NOTREGISTERED

    return bytes(f":mantatail {not_registered_num} * {not_registered_info}\r\n", encoding="utf-8")


def error_no_motd(user: mantatail.UserConnection) -> None:
    (no_motd_num, no_motd_info) = irc_responses.ERR_NOMOTD

    message = f"{no_motd_num} {no_motd_info}"
    user.send_string_to_client(message)


def error_nick_in_use(nick: str) -> bytes:
    (nick_in_use_num, nick_in_use_info) = irc_responses.ERR_NICKNAMEINUSE

    return bytes(f":mantatail {nick_in_use_num} {nick} {nick_in_use_info}\r\n", encoding="utf-8")


def error_no_such_nick_channel(user: mantatail.UserConnection, channel_or_nick: str) -> None:
    (no_nick_num, no_nick_info) = irc_responses.ERR_NOSUCHNICK

    message = f"{no_nick_num} {channel_or_nick} {no_nick_info}"
    user.send_string_to_client(message)


def error_not_on_channel(user: mantatail.UserConnection, channel_name: str) -> None:
    (not_on_channel_num, not_on_channel_info) = irc_responses.ERR_NOTONCHANNEL

    message = f"{not_on_channel_num} {channel_name} {not_on_channel_info}"
    user.send_string_to_client(message)


def error_user_not_in_channel(
    user: mantatail.UserConnection, target_usr: mantatail.UserConnection, channel: mantatail.Channel
) -> None:
    (not_in_chan_num, not_in_chan_info) = irc_responses.ERR_USERNOTINCHANNEL
    message = f"{not_in_chan_num} {target_usr.nick} {channel.name} {not_in_chan_info}"
    user.send_string_to_client(message)


def error_cannot_send_to_channel(user: mantatail.UserConnection, channel_name: str) -> None:
    (cant_send_num, cant_send_info) = irc_responses.ERR_CANNOTSENDTOCHAN

    message = f"{cant_send_num} {channel_name} {cant_send_info}"
    user.send_string_to_client(message)


def error_no_such_channel(user: mantatail.UserConnection, channel_name: str) -> None:
    (no_channel_num, no_channel_info) = irc_responses.ERR_NOSUCHCHANNEL
    message = f"{no_channel_num} {channel_name} {no_channel_info}"
    user.send_string_to_client(message)


def error_no_operator_privileges(user: mantatail.UserConnection, channel: mantatail.Channel) -> None:
    (not_operator_num, not_operator_info) = irc_responses.ERR_CHANOPRIVSNEEDED
    message = f"{not_operator_num} {channel.name} {not_operator_info}"
    user.send_string_to_client(message)


def error_unknown_mode(user: mantatail.UserConnection, unknown_command: str) -> None:
    (unknown_mode_num, unknown_mode_info) = irc_responses.ERR_UNKNOWNMODE
    message = f"{unknown_mode_num} {unknown_command} {unknown_mode_info}"
    user.send_string_to_client(message)


def error_not_enough_params(user: mantatail.UserConnection, target_chan_nick: str, command: str) -> None:
    (not_enough_params_num, not_enough_params_info) = irc_responses.ERR_NEEDMOREPARAMS
    message = f"{not_enough_params_num} {target_chan_nick} {command} {not_enough_params_info}"
    user.send_string_to_client(message)
