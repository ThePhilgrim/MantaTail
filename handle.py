import re
import mantatail
import irc_responses


### Handlers
def motd(server: mantatail.Server, user: mantatail.User) -> None:
    (start_num, start_info) = irc_responses.RPL_MOTDSTART
    motd_num = irc_responses.RPL_MOTD
    (end_num, end_info) = irc_responses.RPL_ENDOFMOTD

    motd_start_and_end = {
        "start_msg": f"{start_num} {user.nick} :- mantatail {start_info}",
        "end_msg": f"{end_num} {user.nick} {end_info}",
    }

    start_message_as_bytes = convert_string_to_server_message(motd_start_and_end["start_msg"])
    end_message_as_bytes = convert_string_to_server_message(motd_start_and_end["end_msg"])

    send_bytes_to_user(user, start_message_as_bytes)

    if server.motd_content:
        motd = server.motd_content["motd"]
        for motd_line in motd:
            motd_message = f"{motd_num} {user.nick} :{motd_line.format(user_nick=user.nick)}"
            motd_message_as_bytes = convert_string_to_server_message(motd_message)
            send_bytes_to_user(user, motd_message_as_bytes)
    # If motd.json could not be found
    else:
        error_no_motd(user)

    send_bytes_to_user(user, end_message_as_bytes)


def join(server: mantatail.Server, user: mantatail.User, channel_name: str) -> None:
    channel_regex = r"#[^ \x07,]{1,49}"  # TODO: Make more restrictive (currently valid: ###, #ö?!~ etc)

    lower_channel_name = channel_name.lower()
    with server.channels_and_users_thread_lock:
        if not re.match(channel_regex, lower_channel_name):
            error_no_such_channel(user, channel_name)
        else:
            if lower_channel_name not in server.channels.keys():
                server.channels[lower_channel_name] = mantatail.Channel(channel_name, user.nick)

            lower_user_nick = user.nick.lower()

            if lower_user_nick not in server.channels[lower_channel_name].user_dict.keys():

                channel_user_keys = server.channels[lower_channel_name].user_dict.keys()
                channel_users = " ".join(
                    [server.channels[lower_channel_name].user_dict[user_key].nick for user_key in channel_user_keys]
                )

                server.channels[lower_channel_name].user_dict[lower_user_nick] = user

                for nick in channel_user_keys:
                    message = f"JOIN {channel_name}"
                    message_as_bytes = convert_string_to_server_message(message, user.user_mask)
                    receiver = server.channels[lower_channel_name].user_dict[nick]
                    send_bytes_to_user(receiver, message_as_bytes)

                # TODO: Implement topic functionality for existing channels & MODE for new ones

                message = f"353 {user.nick} = {channel_name} :{user.nick} {channel_users}"
                message_as_bytes = convert_string_to_server_message(message)
                send_bytes_to_user(user, message_as_bytes)

                message = f"366 {user.nick} {channel_name} :End of /NAMES list."
                message_as_bytes = convert_string_to_server_message(message)
                send_bytes_to_user(user, message_as_bytes)

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


def part(server: mantatail.Server, user: mantatail.User, channel_name: str) -> None:
    # TODO: Show part message to other users & Remove from user from channel user list.
    lower_channel_name = channel_name.lower()
    lower_user_nick = user.nick.lower()

    with server.channels_and_users_thread_lock:
        if lower_channel_name not in server.channels.keys():
            error_no_such_channel(user, channel_name)
        elif lower_user_nick not in server.channels[lower_channel_name].user_dict.keys():
            error_not_on_channel(user, channel_name)
        else:
            del server.channels[lower_channel_name].user_dict[lower_user_nick]
            if len(server.channels[lower_channel_name].user_dict) == 0:
                del server.channels[lower_channel_name]


# !Not implemented
def _kick(self, message: str) -> None:
    pass


def quit(server: mantatail.Server, user: mantatail.User, channel_name: str) -> None:
    user.closed_connection = True
    user.socket.close()


def privmsg(server: mantatail.Server, user: mantatail.User, msg: str) -> None:
    print("NEW")
    with server.channels_and_users_thread_lock:
        (receiver, colon_privmsg) = msg.split(" ", 1)

        assert colon_privmsg.startswith(":")

        lower_sender_nick = user.nick.lower()
        lower_channel_name = receiver.lower()

        if not receiver.startswith("#"):
            privmsg_to_user(receiver, colon_privmsg)
        elif lower_channel_name not in server.channels.keys():
            error_no_such_nick_channel(user, receiver)

        elif lower_sender_nick not in server.channels[lower_channel_name].user_dict.keys():
            error_cannot_send_to_channel(user, receiver)
        else:
            sender_user_mask = server.channels[lower_channel_name].user_dict[lower_sender_nick].user_mask

            for user_nick, user in server.channels[lower_channel_name].user_dict.items():
                if user_nick != lower_sender_nick:
                    message = f"PRIVMSG {receiver} {colon_privmsg}"
                    message_as_bytes = convert_string_to_server_message(message, sender_user_mask)

                    send_bytes_to_user(user, message_as_bytes)


# !Not implemented
def privmsg_to_user(receiver, colon_privmsg) -> None:
    pass


### Error Messages
def error_unknown_command(user: mantatail.User, command: str) -> None:
    (unknown_cmd_num, unknown_cmd_info) = irc_responses.ERR_UNKNOWNCOMMAND

    message = f"{unknown_cmd_num} {command} {unknown_cmd_info}"
    error_message_as_bytes = convert_string_to_server_message(message)
    send_bytes_to_user(user, error_message_as_bytes)


def error_no_motd(user: mantatail.User) -> None:
    (no_motd_num, no_motd_info) = irc_responses.ERR_NOMOTD

    message = f"{no_motd_num} {no_motd_info}"
    error_message_as_bytes = convert_string_to_server_message(message)
    send_bytes_to_user(user, error_message_as_bytes)


def error_no_such_nick_channel(user: mantatail.User, channel_name) -> None:
    (no_nick_num, no_nick_info) = irc_responses.ERR_NOSUCHNICK

    message = f"{no_nick_num} {channel_name} {no_nick_info}"
    error_message_as_bytes = convert_string_to_server_message(message)
    send_bytes_to_user(user, error_message_as_bytes)


def error_not_on_channel(user: mantatail.User, channel_name: str) -> None:
    (not_on_channel_num, not_on_channel_info) = irc_responses.ERR_NOTONCHANNEL

    message = f"{not_on_channel_num} {channel_name} {not_on_channel_info}"
    error_message_as_bytes = convert_string_to_server_message(message)
    send_bytes_to_user(user, error_message_as_bytes)


def error_cannot_send_to_channel(user: mantatail.User, channel_name) -> None:
    (cant_send_num, cant_send_info) = irc_responses.ERR_CANNOTSENDTOCHAN

    message = f"{cant_send_num} {channel_name} {cant_send_info}"
    error_message_as_bytes = convert_string_to_server_message(message)
    send_bytes_to_user(user, error_message_as_bytes)


def error_no_such_channel(user: mantatail.User, channel_name: str) -> None:
    (no_channel_num, no_channel_info) = irc_responses.ERR_NOSUCHCHANNEL

    message = f"{no_channel_num} {channel_name} {no_channel_info}"
    error_message_as_bytes = convert_string_to_server_message(message)
    send_bytes_to_user(user, error_message_as_bytes)


### Actions
def convert_string_to_server_message(message: str, prefix="mantatail") -> bytes:
    utf_8 = "utf-8"
    suffix = "\r\n"
    return bytes(f":{prefix} {message}{suffix}", encoding=utf_8)


def send_bytes_to_user(receiver: mantatail.User, message: bytes) -> None:
    receiver.socket.sendall(message)
