import json
import sys

try:
    # https://datatracker.ietf.org/doc/html/rfc1459#section-6.2
    with open("./resources/irc_response_nums.json", "r") as file:
        irc_response_nums = json.load(file)
except FileNotFoundError:
    sys.exit("FileNotFoundError: Missing resources/irc_response_nums.json")

try:
    with open("./resources/motd.json", "r") as file:
        motd_content = json.load(file)
except FileNotFoundError:
    sys.exit("FileNotFoundError: Missing resources/motd.json")


# =====================
#   Error Replies
# =====================


def no_such_channel(message):
    return (
        irc_response_nums["error_replies"]["ERR_NOSUCHCHANNEL"][0],
        irc_response_nums["error_replies"]["ERR_NOSUCHCHANNEL"][1].replace(
            "<channel name>", message
        ),
    )


def not_on_channel(message):
    return (
        irc_response_nums["error_replies"]["ERR_NOTONCHANNEL"][0],
        irc_response_nums["error_replies"]["ERR_NOTONCHANNEL"][1].replace(
            "<channel>", message
        ),
    )


def unknown_command(command):
    return (
        irc_response_nums["error_replies"]["ERR_UNKNOWNCOMMAND"][0],
        irc_response_nums["error_replies"]["ERR_UNKNOWNCOMMAND"][1].replace(
            "<command>", command
        ),
    )


# =====================
#   Command Responses
# =====================


def motd_start_message():
    return (
        irc_response_nums["command_responses"]["RPL_MOTDSTART"][0],
        irc_response_nums["command_responses"]["RPL_MOTDSTART"][1].replace(
            "<server>", "mantatail"
        ),
    )


def motd():
    return motd_content["motd"]


def motd_num():
    return irc_response_nums["command_responses"]["RPL_MOTD"][0]


def motd_end_message():
    return (
        irc_response_nums["command_responses"]["RPL_ENDOFMOTD"][0],
        irc_response_nums["command_responses"]["RPL_ENDOFMOTD"][1],
    )


# =====================
#   Reserved Numerics
# =====================
