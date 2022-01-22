"""
Contains IRC-specific server replies that are sent to clients based on their actions.

These include:
    - Command Responses: Responses to certain commands, such as joining channel or setting channel mode.
    - Error Replies: Responses to invalid actions by the user, for example,leaving a channel that
      does not exist or not providing enough parameters in their commands.
"""


# Error Replies
ERR_NOSUCHNICK = ("401", ":No such nick/channel")
ERR_NOSUCHSERVER = ("402", ":No such server")
ERR_NOSUCHCHANNEL = ("403", ":No such channel")
ERR_CANNOTSENDTOCHAN = ("404", ":Cannot send to channel")
ERR_TOOMANYCHANNELS = ("405", ":You have joined too many channels")
ERR_NOORIGIN = ("409", ":No origin specified")
ERR_NORECIPIENT = ("411", ":No recipient given")
ERR_NOTEXTTOSEND = ("412", ":No text to send")
ERR_UNKNOWNCOMMAND = ("421", ":Unknown command")
ERR_NOMOTD = ("422", ":MOTD File is missing")
ERR_NONICKNAMEGIVEN = ("431", ":No nickname given")
ERR_ERRONEUSNICKNAME = ("432", ":Erroneous Nickname")
ERR_NICKNAMEINUSE = ("433", ":Nickname is already in use")
ERR_USERNOTINCHANNEL = ("441", ":They aren't on that channel")
ERR_NOTONCHANNEL = ("442", ":You're not on that channel")
ERR_NOTREGISTERED = ("451", ":You have not registered")
ERR_NEEDMOREPARAMS = ("461", ":Not enough parameters")
ERR_UNKNOWNMODE = ("472", ":is unknown mode char to me")
ERR_CHANOPRIVSNEEDED = ("482", ":You're not channel operator")
ERR_UMODEUNKNOWNFLAG = ("501", ":Unknown MODE flag")

# Command Responses
RPL_AWAY = "301"
RPL_CHANNELMODEIS = "324"
RPL_MOTDSTART = ("375", "Message of the day - ")
RPL_MOTD = "372"
RPL_ENDOFMOTD = ("376", ":End of /MOTD command")
