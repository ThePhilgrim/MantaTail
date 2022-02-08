"""
Contains handler functions that handle commands received from a client, as well as appropriate errors.

Each command can include:
    - Source: Optional note of where the message came from, starting with ':'.
        * This is usually the server name or the user mask
    - Command: The specific command this message represents.
    - Parameters: Optional data relevant to this specific command – a series of values
        separated by one or more spaces. Parameters have different meanings for every single message.

    Ex:
        :Alice!AliceUsr@127.0.0.1  PRIVMSG  #foo :This is a message.

        |_______ SOURCE ________| |COMMAND| |_____ PARAMETERS ______|


All public functions start with "handle_".

To read how handler functions are called: see server.recv_loop() documentation.
"""
from __future__ import annotations
import re
import socket

import server, errors


from typing import Optional, Dict, List


### Handlers
def handle_cap(state: server.State, user: server.UserConnection, args: List[str]) -> None:
    """
    Command formats:
        Starts capability negotiation: "CAP LS 302" ("302" indicates
            support for IRCv3.2. Number in command can differ.)
        Requires a capability to be enabled: "CAP REQ :capability"
        Get enabled capabilities: "CAP LIST"
    """
    # TODO: Implement invalid cap command: 410 :Invalid CAP command
    if not args:
        errors.not_enough_params(user, "CAP")
        return

    user.capneg_in_progress = True
    low_cap_command = args[0].lower()

    if low_cap_command == "ls":
        message = f"CAP {user.nick} LS :{' '.join(server.CAP_LS)}"
        user.send_que.put((message, "mantatail"))
        if len(args) > 1:
            try:
                if int(args[1]) >= 302:
                    user.cap_list.add("cap-notify")
            except ValueError:
                return
        return

    if low_cap_command == "list":
        message = f"CAP {user.nick} LIST :{' '.join(user.cap_list)}"
        user.send_que.put((message, "mantatail"))
        return

    if low_cap_command == "req":
        # CAP REQ without specified capability
        if len(args) == 1:
            return

        capabilities = args[1].split(" ")
        unsupported_caps = [cap for cap in capabilities if cap not in server.CAP_LS]

        if unsupported_caps:
            message = f"CAP {user.nick} NAK :{args[1]}"
        else:
            message = f"CAP {user.nick} ACK :{args[1]}"

            for capability in capabilities:
                user.cap_list.add(capability)

        user.send_que.put((message, "mantatail"))
        return

    if low_cap_command == "end":
        user.capneg_in_progress = False
        return


def handle_join(state: server.State, user: server.UserConnection, args: List[str]) -> None:
    """
    Command format: "JOIN #foo"

    If the channel already exists, the user is added to the channel.
    If the channel does not exist, the channel is created.

    Finally, sends a message to all users on the channel, notifying them that
    User has joined the channel.
    """

    if not args:
        errors.not_enough_params(user, "JOIN")
        return

    channel_regex = r"#[^ \x07,]{1,49}"  # TODO: Make more restrictive (currently valid: ###, #ö?!~ etc)
    channel_name = args[0]
    lower_channel_name = channel_name.lower()

    if not re.match(channel_regex, lower_channel_name):
        errors.no_such_channel(user, channel_name)
    else:
        if lower_channel_name not in state.channels.keys():
            state.channels[lower_channel_name] = server.Channel(channel_name, user)

        channel = state.find_channel(channel_name)

        assert channel

        is_banned = channel.check_if_banned(user.get_user_mask())

        if is_banned:
            errors.banned_from_chan(user, channel)
            return

        if user not in channel.users:
            channel_users_str = ""
            for usr in channel.users:
                channel_users_str += f" {usr.get_prefix(channel)}{usr.nick}"

            channel.users.add(user)

            join_msg = f"JOIN {channel_name}"
            channel.queue_message_to_chan_users(join_msg, user)

            if channel.topic:
                channel.send_topic_to_user(user)

            message = f"353 {user.nick} = {channel_name} :{user.get_prefix(channel)}{user.nick}{channel_users_str}"
            user.send_que.put((message, "mantatail"))

            message = f"366 {user.nick} {channel_name} :End of /NAMES list."
            user.send_que.put((message, "mantatail"))

            if user.away:
                away_notify_msg = f"AWAY :{user.away}"
                for usr in channel.users:
                    if "away-notify" in usr.cap_list:
                        usr.send_que.put((away_notify_msg, user.get_user_mask()))

        # TODO: Forward to another channel (irc num 470) ex. #homebrew -> ##homebrew


def handle_part(state: server.State, user: server.UserConnection, args: List[str]) -> None:
    """
    Command format: "PART #foo"

    Removes user from a channel.

    Thereafter, sends a message to all users on the channel, notifying them that
    User has left the channel.
    """
    if not args:
        errors.not_enough_params(user, "PART")
        return

    channel_name = args[0]

    channel = state.find_channel(channel_name)

    if not channel:
        errors.no_such_channel(user, channel_name)
        return

    if user not in channel.users:
        errors.not_on_channel(user, channel_name)
    else:
        channel.operators.discard(user)

        part_message = f"PART {channel_name}"
        channel.queue_message_to_chan_users(part_message, user)

        channel.users.discard(user)
        if len(channel.users) == 0:
            state.delete_channel(channel_name)


def handle_mode(state: server.State, user: server.UserConnection, args: List[str]) -> None:
    """
    Command format: "MODE #channel/user.nick +/-flag <args>"

    Sets a user/channel mode.

    Ex:
        - User mode "+i" makes user invisible
        - Channel mode "+i" makes channel invite-only.
        (Note: "+i" is not yet supported by Mantatail)
    """
    if not args:
        errors.not_enough_params(user, "MODE")
        return

    if args[0].startswith("#"):
        process_channel_modes(state, user, args)
    else:
        target_usr = state.find_user(args[0])
        if not target_usr:
            errors.no_such_channel(user, args[0])
            return
        else:
            if user != target_usr:
                # TODO: The actual IRC error for this should be "502 Can't change mode for other users"
                # This will be implemented when MODE becomes more widely supported.
                # Currently not sure which modes 502 applies to.
                errors.no_such_channel(user, args[0])
                return
        process_user_modes()


def handle_nick(state: server.State, user: server.UserConnection, args: List[str]) -> None:
    """
    Sets a user's nickname if they don't already have one.
    Changes the user's nickname if they already have one.
    """
    nick_regex = r"[a-zA-Z|\\_\[\]{}^`-][a-zA-Z0-9|\\_\[\]{}^`-]{,15}"

    if not args:
        errors.no_nickname_given(user)
        return

    new_nick = args[0]
    if not re.fullmatch(nick_regex, new_nick):
        errors.erroneus_nickname(user, new_nick)
        return
    elif new_nick in state.connected_users.keys():
        errors.nick_in_use(user, new_nick)
    else:
        if user.nick == "*":
            user.nick = new_nick
            state.connected_users[user.nick.lower()] = user
        else:
            if new_nick == user.nick:
                return
            # Avoids sending NICK message to users several times if user shares more than one channel with them.
            receivers = user.get_users_sharing_channel()
            message = f"NICK :{new_nick}"

            for receiver in receivers:
                receiver.send_que.put((message, user.get_user_mask()))

            # User doesn't get NICK message if they change their nicks before sending USER command
            if user.user_message:
                user.send_que.put((message, user.get_user_mask()))

            # Not using state.delete_user() as that will delete the user from all channels as well.
            del state.connected_users[user.nick.lower()]

            user.nick = new_nick
            state.connected_users[user.nick.lower()] = user


def handle_away(state: server.State, user: server.UserConnection, args: List[str]) -> None:
    """
    Command formats:
        Set away status: "AWAY :Away message"
        Remove away status: "AWAY"

    Sets/Removes the Away status of a user. If somebody sends a PRIVMSG to a user who is Away,
    they will receive a reply with the user's away message.
    """

    receivers = user.get_users_sharing_channel()

    if not args:
        away_parameter = ""
    else:
        away_parameter = args[0]

    # args[0] == "" happens when user sends "AWAY :", which indicates they are no longer away.
    if not away_parameter:
        msg_to_self = f"305 {user.nick} :You are no longer marked as being away"
        user.away = None
    else:
        msg_to_self = f"306 {user.nick} :You have been marked as being away"
        user.away = args[0]

    user.send_que.put((msg_to_self, "mantatail"))
    away_notify_msg = f"AWAY :{away_parameter}"

    for receiver in receivers:
        if "away-notify" in receiver.cap_list:
            receiver.send_que.put((away_notify_msg, user.get_user_mask()))


def handle_topic(state: server.State, user: server.UserConnection, args: List[str]) -> None:
    """
    Command formats:
        Set new topic: "TOPIC #foo :New Topic"
        Clear topic: "TOPIC #foo :"
        Get topic: "TOPIC #foo"

    Depending on command and operator status, either sends a channel's topic to user, sets a new topic,
    or clears the current topic.
    """
    if not args:
        errors.not_enough_params(user, "TOPIC")
        return

    channel = state.find_channel(args[0])

    if not channel:
        errors.no_such_channel(user, args[0])
        return

    if len(args) == 1:
        channel.send_topic_to_user(user)
    else:
        if "t" in channel.modes and user not in channel.operators:
            errors.no_operator_privileges(user, channel)
        else:
            channel.set_topic(user, args[1])

            if not args[1]:
                topic_message = f"TOPIC {channel.name} :"
            else:
                topic_message = f"TOPIC {channel.name} :{args[1]}"

            channel.queue_message_to_chan_users(topic_message, user)


def handle_kick(state: server.State, user: server.UserConnection, args: List[str]) -> None:
    """
    Command format: "KICK #foo user_to_kick (:Reason for kicking)"

    Kicks a user from a channel. The kicker must be an operator on that channel.

    Notifies the kicked user that they have been kicked and the reason for it.
    Thereafter, sends a message to all users on the channel, notifying them
    that an operator has kicked a user.
    """
    if not args or len(args) == 1:
        errors.not_enough_params(user, "KICK")
        return

    channel = state.find_channel(args[0])
    if not channel:
        errors.no_such_channel(user, args[0])
        return

    target_usr = state.find_user(args[1])
    if not target_usr:
        errors.no_such_nick_channel(user, args[1])
        return

    if user not in channel.operators:
        errors.no_operator_privileges(user, channel)
        return

    if target_usr not in channel.users:
        errors.user_not_in_channel(user, target_usr, channel)
        return

    if len(args) == 2:
        kick_message = f"KICK {channel.name} {target_usr.nick} :{target_usr.nick}"
    elif len(args) >= 3:
        reason = args[2]
        kick_message = f"KICK {channel.name} {target_usr.nick} :{reason}"

    channel.queue_message_to_chan_users(kick_message, user)
    channel.users.discard(target_usr)
    channel.operators.discard(target_usr)

    if len(channel.users) == 0:
        state.delete_channel(channel.name)


def handle_quit(state: server.State, user: server.UserConnection, args: List[str]) -> None:
    """
    Command format: "QUIT"

    Disconnects a user from the server by putting tuple (None, disconnect_reason: str) to their send queue.
    """
    if args:
        disconnect_reason = args[0]
    else:
        disconnect_reason = "Client quit"

    user.send_que.put((None, disconnect_reason))


def handle_privmsg(state: server.State, user: server.UserConnection, args: List[str]) -> None:
    """
    Command format: "PRIVMSG #channel/user.nick :This is a message"

    Depending on the command, sends a message to all users on a channel or a private message to a user.
    """
    if not args:
        errors.no_recipient(user, "PRIVMSG")
        return
    elif len(args) == 1:
        errors.no_text_to_send(user)
        return

    (receiver, privmsg) = args[0], args[1]

    if receiver.startswith("#"):

        channel = state.find_channel(receiver)
        if not channel:
            errors.no_such_channel(user, receiver)
            return
    else:
        privmsg_to_user(state, user, receiver, privmsg)
        return

    # USER MASK:  Bob!BobUsr@127.0.0.1
    # BAN LIST:  ['Bob!*@*']

    is_banned = channel.check_if_banned(user.get_user_mask())

    if user not in channel.users:
        errors.not_on_channel(user, receiver)
    elif is_banned:
        errors.cannot_send_to_channel(user, channel.name)
    else:
        privmsg_message = f"PRIVMSG {receiver} :{privmsg}"
        channel.queue_message_to_chan_users(privmsg_message, user, send_to_self=False)


def handle_who(state: server.State, user: server.UserConnection, args: List[str]) -> None:
    # TODO: Implement error 263 (WHO sent too many times)
    if not args:
        errors.not_enough_params(user, "WHO")
        return

    if args[0].startswith("#"):
        channel = state.find_channel(args[0])

        if channel:
            for who_usr in channel.users:
                if not who_usr.away:
                    away_status = "H"
                else:
                    away_status = "G"

                # ":0" refers to "hopcount", which is not supported by Mantatail.
                # "Hopcount is the number of intermediate servers between the client issuing the WHO command
                # and the client Nickname, it might be unreliable so clients SHOULD ignore it.""
                who_message = f"352 {user.nick} {channel.name} {who_usr.user_name} {who_usr.host} Mantatail {who_usr.nick} {away_status}{who_usr.get_prefix(channel)} :0 {who_usr.real_name}"

                if user not in channel.users:
                    if "i" not in who_usr.modes:
                        user.send_que.put((who_message, "mantatail"))
                else:
                    user.send_que.put((who_message, "mantatail"))

    else:
        target_usr = state.find_user(args[0])

        if target_usr:
            if not target_usr.away:
                away_status = "H"
            else:
                away_status = "G"

            who_message = f"352 {user.nick} * {target_usr.user_name} {target_usr.host} Mantatail {target_usr.nick} {away_status} :0 {target_usr.real_name}"
            user.send_que.put((who_message, "mantatail"))

    end_of_who_message = f"315 {user.nick} {args[0]} :End of /WHO list."
    user.send_que.put((end_of_who_message, "mantatail"))


def handle_pong(state: server.State, user: server.UserConnection, args: List[str]) -> None:
    """
    Handles client's PONG response to a PING message sent from the server.

    The PONG message notifies the server that the client still has an open connection to it.

    The parameter sent in the PONG message must correspond to the parameter in the PING message.
    Ex.
        PING :This_is_a_parameter
        PONG :This_is_a_parameter
    """
    if args and args[0] == "mantatail":
        user.pong_received = True
    else:
        errors.no_origin(user)


# Private functions
def privmsg_to_user(state: server.State, sender: server.UserConnection, receiver: str, privmsg: str) -> None:
    receiver_usr = state.find_user(receiver)
    if not receiver_usr:
        errors.no_such_nick_channel(sender, receiver)
        return

    message = f"PRIVMSG {receiver_usr.nick} :{privmsg}"
    receiver_usr.send_que.put((message, sender.get_user_mask()))

    if receiver_usr.away:
        away_message = f"301 {sender.nick} {receiver_usr.nick} :{receiver_usr.away}"
        sender.send_que.put((away_message, "mantatail"))


def rpl_welcome(user: server.UserConnection) -> None:
    welcome_msg = f"001 {user.nick} :Welcome to Mantatail {user.get_user_mask()}"
    user.send_que.put((welcome_msg, "mantatail"))


def rpl_yourhost(user: server.UserConnection, state: server.State) -> None:
    yourhost_msg = f"002 {user.nick} :Your host is Mantatail[{socket.gethostname()}/{state.port}], running version {server.MANTATAIL_VERSION}"
    user.send_que.put((yourhost_msg, "mantatail"))


def rpl_created(user: server.UserConnection) -> None:
    created_msg = f"003 {user.nick} :This server was created {server.SERVER_STARTED} CET"
    user.send_que.put((created_msg, "mantatail"))


def rpl_myinfo(user: server.UserConnection, state: server.State) -> None:
    all_supported_modes_joined = "".join(
        [mode for key in state.supported_modes.keys() for mode in state.supported_modes[key]]
    )
    myinfo_msg = f"004 {user.nick} Mantatail {server.MANTATAIL_VERSION} {all_supported_modes_joined}"
    user.send_que.put((myinfo_msg, "mantatail"))


def rpl_isupport(user: server.UserConnection) -> None:
    isupport = []

    for key, value in server.ISUPPORT.items():
        isupport.append(f"{key}={value}")

    isupport_msg = f"005 {user.nick} {' '.join(isupport)} :are supported by this server"
    user.send_que.put((isupport_msg, "mantatail"))


def motd(motd_content: Optional[Dict[str, List[str]]], user: server.UserConnection) -> None:
    """
    Sends the server's Message of the Day to the user.

    This is sent to a user when they have registered a nick and a username on the server.
    """
    motd_start_and_end = {
        "start_msg": f"375 {user.nick} :- mantatail Message of the day - ",
        "end_msg": f"376 {user.nick} :End of /MOTD command",
    }

    user.send_que.put((motd_start_and_end["start_msg"], "mantatail"))

    if motd_content:
        motd = motd_content["motd"]
        for motd_line in motd:
            motd_message = f"372 {user.nick} :{motd_line.format(user_nick=user.nick)}"
            user.send_que.put((motd_message, "mantatail"))
    # If motd.json could not be found
    else:
        errors.no_motd(user)

    user.send_que.put((motd_start_and_end["end_msg"], "mantatail"))


def process_channel_modes(state: server.State, user: server.UserConnection, args: List[str]) -> None:
    """
    Given that the user has the required privileges, sets the requested channel mode.

    Ex. Make a channel invite-only, or set a channel operator.

    Finally sends a message to all users on the channel, notifying them about the new channel mode.
    """
    channel = state.find_channel(args[0])
    if not channel:
        errors.no_such_channel(user, args[0])
        return

    if len(args) == 1:
        if channel.modes:
            message = f'324 {user.nick} {channel.name} +{"".join(channel.modes)}'
        else:
            message = f"324 {user.nick} {channel.name}"
        user.send_que.put((message, "mantatail"))
    else:
        if args[1][0] not in ["+", "-"]:
            errors.unknown_mode(user, args[1][0])
            return

        supported_modes = [mode for modes in state.supported_modes.values() for mode in modes]

        for mode in args[1][1:]:
            if mode not in supported_modes or not re.fullmatch(r"[a-zA-Z]", mode):
                errors.unknown_mode(user, mode)
                return

        mode_command, flags = args[1][0], args[1][1:]
        parameters = iter(args[2:])
        for flag in flags:

            if flag == "b":
                current_param = next(parameters, None)

                process_mode_b(user, channel, mode_command, current_param)

            elif flag == "o":
                current_param = next(parameters, None)

                process_mode_o(state, user, channel, mode_command, current_param)

            elif flag == "t":
                process_mode_t(user, channel, mode_command)


def process_mode_b(
    user: server.UserConnection, channel: server.Channel, mode_command: str, ban_target: Optional[str]
) -> None:
    """Bans or unbans a user from a channel."""
    if not ban_target:
        if channel.ban_list:
            for ban_mask, banner in channel.ban_list.items():
                message = f"367 {user.nick} {channel.name} {ban_mask} {banner}"
                user.send_que.put((message, "mantatail"))

        message = f"368 {user.nick} {channel.name} :End of Channel Ban List"
        user.send_que.put((message, "mantatail"))
        return

    if user not in channel.operators:
        errors.no_operator_privileges(user, channel)
        return

    target_ban_mask = generate_ban_mask(ban_target)
    is_already_banned = channel.check_if_banned(target_ban_mask)
    mode_message = f"MODE {channel.name} {mode_command}b {target_ban_mask}"

    # Not sending message if "+b" and target usr is already banned (or vice versa)
    if mode_command == "+" and not is_already_banned:
        channel.queue_message_to_chan_users(mode_message, user)
        channel.ban_list[target_ban_mask] = user.get_user_mask()

    elif mode_command == "-" and is_already_banned:
        channel.queue_message_to_chan_users(mode_message, user)
        try:
            del channel.ban_list[target_ban_mask]
        except KeyError:
            pass


def process_mode_o(
    state: server.State,
    user: server.UserConnection,
    channel: server.Channel,
    mode_command: str,
    target_usr_nick: Optional[str],
) -> None:
    """Sets or removes channel operator"""
    if not target_usr_nick:
        errors.not_enough_params(user, "MODE")
        return

    target_usr = state.find_user(target_usr_nick)

    if not target_usr:
        errors.no_such_nick_channel(user, target_usr_nick)
        return
    if user not in channel.operators:
        errors.no_operator_privileges(user, channel)
        return
    if target_usr not in channel.users:
        errors.user_not_in_channel(user, target_usr, channel)
        return

    mode_message = f"MODE {channel.name} {mode_command}o {target_usr.nick}"

    if mode_command == "+" and target_usr not in channel.operators:
        channel.queue_message_to_chan_users(mode_message, user)
        channel.operators.add(target_usr)

    elif mode_command == "-" and target_usr in channel.operators:
        channel.queue_message_to_chan_users(mode_message, user)
        channel.operators.discard(target_usr)


def process_mode_t(user: server.UserConnection, channel: server.Channel, mode_command: str) -> None:
    if user not in channel.operators:
        errors.no_operator_privileges(user, channel)
        return

    mode_message = f"MODE {channel.name} {mode_command}t"

    if mode_command == "+" and "t" not in channel.modes:
        channel.queue_message_to_chan_users(mode_message, user)
        channel.modes.add("t")

    elif mode_command == "-" and "t" in channel.modes:
        channel.queue_message_to_chan_users(mode_message, user)
        channel.modes.discard("t")


# !Not implemented
def process_user_modes() -> None:
    # TODO: Make it possible to remove/add user mode +i
    pass


def generate_ban_mask(ban_target: str) -> str:
    """
    Generates a user mask based on the parameters given in a MODE +b command.
    Any part of the user mask not provided by the user is added as a wildcard ("*").

    >>> generate_ban_mask("Foo")
    'Foo!*@*'
    >>> generate_ban_mask("Foo!Bar")
    'Foo!Bar@*'
    >>> generate_ban_mask("Foo!Bar@Baz")
    'Foo!Bar@Baz'
    >>> generate_ban_mask("Bar@Baz")
    '*!Bar@Baz'
    >>> generate_ban_mask("@Baz")
    '*!*@Baz'
    """
    if "!" in ban_target and "@" in ban_target:
        ban_mask_regex = r"([^!]*)!(.*)@(.*)"
        ban_match = re.fullmatch(ban_mask_regex, ban_target)
        if not ban_match:
            # @ before ! (corner case)
            ban_mask_regex = r"(.*)@(.*)!(.*)"
            ban_match = re.fullmatch(ban_mask_regex, ban_target)

        assert ban_match is not None  # Keeps mypy silent
        nick, user, host = ban_match.groups()

    elif "!" in ban_target:
        nick, user = ban_target.split("!", 1)
        host = "*"

    elif "@" in ban_target:
        user, host = ban_target.split("@", 1)
        nick = "*"

    else:
        nick = ban_target
        user = "*"
        host = "*"

    if not nick:
        nick = "*"
    if not user:
        user = "*"
    if not host:
        host = "*"

    return f"{nick}!{user}@{host}"
