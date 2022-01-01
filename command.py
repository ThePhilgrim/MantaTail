from __future__ import annotations
import re
import mantatail
import irc_responses

from typing import Optional, Dict, List


### Handlers
def handle_join(
    state: mantatail.ServerState, user: mantatail.UserConnection, channel_name: str
) -> None:
    channel_regex = (
        r"#[^ \x07,]{1,49}"  # TODO: Make more restrictive (currently valid: ###, #ö?!~ etc)
    )

    lower_channel_name = channel_name.lower()
    with state.lock:
        if not re.match(channel_regex, lower_channel_name):
            error_no_such_channel(user, channel_name)
        else:
            if lower_channel_name not in state.channels.keys():
                state.channels[lower_channel_name] = mantatail.Channel(channel_name, user.nick)

            lower_user_nick = user.nick.lower()

            if lower_user_nick not in state.channels[lower_channel_name].user_dict.keys():

                channel_user_keys = state.channels[lower_channel_name].user_dict.keys()
                channel_users = " ".join(
                    [
                        state.channels[lower_channel_name].user_dict[user_key].nick
                        for user_key in channel_user_keys
                    ]
                )

                state.channels[lower_channel_name].user_dict[lower_user_nick] = user

                for nick in channel_user_keys:
                    message = f"JOIN {channel_name}"
                    receiver = state.channels[lower_channel_name].user_dict[nick]
                    receiver.send_string_to_client(message, prefix=user.user_mask)

                # TODO: Implement topic functionality for existing channels & MODE for new ones

                message = f"353 {user.nick} = {channel_name} :{user.nick} {channel_users}"
                user.send_string_to_client(message)

                message = f"366 {user.nick} {channel_name} :End of /NAMES list."
                user.send_string_to_client(message)

        # TODO:
        #   * Send topic (332)
        #   * Optional/Later: (333) https://modern.ircdocs.horse/#rpltopicwhotime-333
        #   * Send Name list (353)
        #   * Send End of Name list (366)

        # TODO: Check for:
        #   * User invited to channel
        #   * Nick/user not matching bans
        #   * Eventual password matches
        #   * Not joined too many channels

        # TODO:
        #   * Forward to another channel (irc num 470) ex. #homebrew -> ##homebrew


def handle_part(
    state: mantatail.ServerState, user: mantatail.UserConnection, channel_name: str
) -> None:
    # TODO: Show part message to other users & Remove from user from channel user list.
    lower_channel_name = channel_name.lower()
    lower_user_nick = user.nick.lower()

    with state.lock:
        if lower_channel_name not in state.channels.keys():
            error_no_such_channel(user, channel_name)
        elif lower_user_nick not in state.channels[lower_channel_name].user_dict.keys():
            error_not_on_channel(user, channel_name)
        else:
            channel_users = state.channels[lower_channel_name].user_dict

            for nick in channel_users.keys():
                message = f"PART {channel_name}"
                receiver = channel_users[nick]
                receiver.send_string_to_client(message, prefix=user.user_mask)

            del channel_users[lower_user_nick]

            if len(state.channels[lower_channel_name].user_dict) == 0:
                del state.channels[lower_channel_name]


def handle_mode(
    state: mantatail.ServerState, user: mantatail.UserConnection, mode_args: str
) -> None:
    args = mode_args.split(" ")

    if args[0].startswith("#"):
        process_channel_modes(state, user, args)
    else:
        process_user_modes()


# !Not implemented
def _handle_kick(message: str) -> None:
    pass


def handle_quit(state: mantatail.ServerState, user: mantatail.UserConnection, command: str) -> None:
    # TODO: Implement logic for different reasons & disconnects.
    reason = "(Remote host closed the connection)"
    message = f"QUIT :Quit: {reason}"

    receivers = set()
    with state.lock:
        receivers.add(user)
        for channel_name, channel in state.channels.items():
            if user.nick.lower() in channel.user_dict.keys():
                for nick, receiver in channel.user_dict.items():
                    receivers.add(receiver)
                del state.channels[channel_name].user_dict[user.nick.lower()]

        for receiver in receivers:
            receiver.send_string_to_client(message, prefix=user.user_mask)

        user.closed_connection = True
        user.socket.close()


def handle_privmsg(state: mantatail.ServerState, user: mantatail.UserConnection, msg: str) -> None:
    with state.lock:
        (receiver, colon_privmsg) = msg.split(" ", 1)

        assert colon_privmsg.startswith(":")

        lower_sender_nick = user.nick.lower()
        lower_channel_name = receiver.lower()

        if not receiver.startswith("#"):
            privmsg_to_user(receiver, colon_privmsg)
        elif lower_channel_name not in state.channels.keys():
            error_no_such_nick_channel(user, receiver)

        elif lower_sender_nick not in state.channels[lower_channel_name].user_dict.keys():
            error_cannot_send_to_channel(user, receiver)
        else:
            sender = state.channels[lower_channel_name].user_dict[lower_sender_nick]

            for user_nick, user in state.channels[lower_channel_name].user_dict.items():
                if user_nick != lower_sender_nick:
                    message = f"PRIVMSG {receiver} {colon_privmsg}"
                    user.send_string_to_client(message, prefix=sender.user_mask)


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


def process_channel_modes(
    state: mantatail.ServerState, user: mantatail.UserConnection, args: List[str]
) -> None:
    supported_channel_modes = ["o"]
    if args[0].lower() not in state.channels.keys():

        error_no_such_channel(user, args[0])
    elif len(args) == 1:

        message = f'{irc_responses.RPL_CHANNELMODEIS} {args[0]} {" ".join(state.channels[args[0].lower()].modes)}'
        user.send_string_to_client(message)
    else:
        assert len(args) == 3
        target_chan = args[0]
        mode_command = list(args[1])
        target_user = args[2]

        command_contains_unsupported_modes = False

        for mode in mode_command[1:]:
            if mode not in supported_channel_modes:
                command_contains_unsupported_modes = True
            else:
                if mode == "o":
                    if user.nick != state.channels[target_chan.lower()].founder:
                        error_no_operator_privileges(user, target_chan)
                    elif target_user.lower() not in state.channels[target_chan].user_dict.keys():
                        error_user_not_in_channel(user, target_user, target_chan)
                        pass
                    elif mode_command[0] == "+":
                        state.channels[target_chan.lower()].set_operator(target_user)
                        message = f"MODE {target_chan} {args[1]} {target_user}"
                        for receiver in [
                            user,
                            state.channels[target_chan.lower()].user_dict[target_user.lower()],
                        ]:
                            receiver.send_string_to_client(message)
                    elif mode_command[0] == "-":
                        state.channels[target_chan.lower()].remove_operator(target_user)
                        message = f"MODE {target_chan} {args[1]} {target_user}"
                        for receiver in [
                            user,
                            state.channels[target_chan.lower()].user_dict[target_user.lower()],
                        ]:
                            receiver.send_string_to_client(message)

        if command_contains_unsupported_modes:
            error_unknown_mode_flag(user)


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


def error_no_such_nick_channel(user: mantatail.UserConnection, channel_name: str) -> None:
    (no_nick_num, no_nick_info) = irc_responses.ERR_NOSUCHNICK

    message = f"{no_nick_num} {channel_name} {no_nick_info}"
    user.send_string_to_client(message)


def error_not_on_channel(user: mantatail.UserConnection, channel_name: str) -> None:
    (not_on_channel_num, not_on_channel_info) = irc_responses.ERR_NOTONCHANNEL

    message = f"{not_on_channel_num} {channel_name} {not_on_channel_info}"
    user.send_string_to_client(message)


def error_user_not_in_channel(
    user: mantatail.UserConnection, target_user: str, target_chan: str
) -> None:
    (not_in_chan_num, not_in_chan_info) = irc_responses.ERR_USERNOTINCHANNEL
    message = f"{not_in_chan_num} {target_user} {target_chan} {not_in_chan_info}"
    user.send_string_to_client(message)


def error_cannot_send_to_channel(user: mantatail.UserConnection, channel_name: str) -> None:
    (cant_send_num, cant_send_info) = irc_responses.ERR_CANNOTSENDTOCHAN

    message = f"{cant_send_num} {channel_name} {cant_send_info}"
    user.send_string_to_client(message)


def error_no_such_channel(user: mantatail.UserConnection, channel_name: str) -> None:
    (no_channel_num, no_channel_info) = irc_responses.ERR_NOSUCHCHANNEL
    message = f"{no_channel_num} {channel_name} {no_channel_info}"
    user.send_string_to_client(message)


def error_no_operator_privileges(user: mantatail.UserConnection, target_channel: str) -> None:
    (not_operator_num, not_operator_info) = irc_responses.ERR_CHANOPRIVSNEEDED
    message = f"{not_operator_num} {target_channel} {not_operator_info}"
    user.send_string_to_client(message)


def error_unknown_mode_flag(user: mantatail.UserConnection) -> None:
    (unknown_flag_num, unknown_flag_info) = irc_responses.ERR_UMODEUNKNOWNFLAG
    message = f"{unknown_flag_num} {unknown_flag_info}"
    user.send_string_to_client(message)
